"""Command-line interface for the Constitution Memorizer PDF-to-JSON pipeline."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Sequence

from constitution_memorizer import __version__
from constitution_memorizer.config import PipelineConfig, load_config
from constitution_memorizer.exceptions import (
    ConstitutionMemorizerError,
    OverwriteRefusedError,
)
from constitution_memorizer.extraction.docling_extractor import extract_pdf
from constitution_memorizer.normalization.line_normalizer import lines_to_serializable
from constitution_memorizer.normalization.repetition_detector import normalize_document
from constitution_memorizer.parsing.constitution_parser import parse_lines
from constitution_memorizer.schemas import DocumentMetadata, ConstitutionDocument
from constitution_memorizer.utils.json_io import (
    model_to_dict,
    read_json,
    read_text,
    write_json,
)
from constitution_memorizer.validation.report_builder import (
    build_report,
    format_report_summary,
)

logger = logging.getLogger("constitution_memorizer")


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def _add_shared_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data"),
        help="Root data directory (default: data)",
    )
    parser.add_argument(
        "--force",
        "--overwrite",
        dest="force",
        action="store_true",
        help="Overwrite existing output files",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Optional JSON configuration file",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argparse parser."""
    parser = argparse.ArgumentParser(
        prog="constitution_memorizer",
        description=(
            "Extract and parse the Constitution of India Bare Act PDF into "
            "structured JSON. Phase 1: PDF-to-JSON pipeline only."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    extract_p = sub.add_parser("extract", help="Extract PDF with Docling")
    extract_p.add_argument("--pdf", type=Path, required=True, help="Path to Bare Act PDF")
    _add_shared_flags(extract_p)

    normalize_p = sub.add_parser("normalize", help="Normalize extracted Markdown")
    normalize_p.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Markdown input (default: <output-dir>/intermediate/constitution.md)",
    )
    _add_shared_flags(normalize_p)

    parse_p = sub.add_parser("parse", help="Parse normalized text into constitution JSON")
    parse_p.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Markdown or normalized_lines.json input",
    )
    _add_shared_flags(parse_p)

    validate_p = sub.add_parser("validate", help="Validate constitution JSON and write report")
    validate_p.add_argument(
        "--input",
        type=Path,
        default=None,
        help="constitution.json path (default: <output-dir>/output/constitution.json)",
    )
    _add_shared_flags(validate_p)

    correct_p = sub.add_parser(
        "correct",
        help="Apply corrections.json overlay to produce constitution.reviewed.json",
    )
    correct_p.add_argument(
        "--input",
        type=Path,
        default=None,
        help="constitution.json path (default: <output-dir>/output/constitution.json)",
    )
    correct_p.add_argument(
        "--corrections",
        type=Path,
        default=Path("data/corrections/corrections.json"),
        help="Corrections overlay JSON",
    )
    _add_shared_flags(correct_p)

    review_p = sub.add_parser(
        "review-report",
        help="Write corpus_review_report.json for human review",
    )
    review_p.add_argument(
        "--input",
        type=Path,
        default=None,
        help="constitution.json path (default: <output-dir>/output/constitution.json)",
    )
    _add_shared_flags(review_p)

    pipeline_p = sub.add_parser(
        "pipeline",
        help="Run extract → normalize → parse → validate → report",
    )
    pipeline_p.add_argument("--pdf", type=Path, required=True, help="Path to Bare Act PDF")
    _add_shared_flags(pipeline_p)

    units_p = sub.add_parser(
        "generate-units",
        help="Generate learning_units.json from constitution.reviewed.json",
    )
    units_p.add_argument(
        "--input",
        type=Path,
        default=None,
        help=(
            "Reviewed constitution JSON "
            "(default: <output-dir>/output/constitution.reviewed.json)"
        ),
    )
    units_p.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Output path for learning units "
            "(default: <output-dir>/output/learning_units.json)"
        ),
    )
    _add_shared_flags(units_p)

    serve_p = sub.add_parser(
        "serve",
        help="Run the learning web UI (FastAPI)",
    )
    serve_p.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host (default: 127.0.0.1)",
    )
    serve_p.add_argument(
        "--port",
        type=int,
        default=None,
        help="Bind port (default: PORT env, else 8000; multi-user launcher uses 8010)",
    )
    serve_p.add_argument(
        "--units",
        type=Path,
        default=None,
        help="learning_units.json path (default: <output-dir>/output/learning_units.json)",
    )
    serve_p.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite progress DB (default: <output-dir>/progress/progress.db)",
    )
    serve_p.add_argument(
        "--reviewed",
        type=Path,
        default=None,
        help=(
            "Reviewed Bare Act JSON for Browse "
            "(default: <output-dir>/output/constitution.reviewed.json)"
        ),
    )
    _add_shared_flags(serve_p)

    remind_p = sub.add_parser(
        "send-reminders",
        help="Send today's study reminder (Constitution + Memory) via console, ntfy, or macos",
    )
    remind_p.add_argument(
        "--channel",
        choices=("console", "ntfy", "macos"),
        default="console",
        help="Delivery channel (default: console)",
    )
    remind_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print digest to stdout without calling the transport",
    )
    remind_p.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="Override today's date (YYYY-MM-DD) for tests",
    )
    remind_p.add_argument(
        "--at",
        type=str,
        default=None,
        help="Override local datetime for schedule gate (YYYY-MM-DDTHH:MM)",
    )
    remind_p.add_argument(
        "--host-url",
        default=None,
        help="Base URL in the message (default: REMINDER_BASE_URL or http://127.0.0.1:8001)",
    )
    remind_p.add_argument(
        "--units",
        type=Path,
        default=None,
        help="learning_units.json path (default: <output-dir>/output/learning_units.json)",
    )
    remind_p.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite progress DB (default: <output-dir>/progress/progress.db)",
    )
    remind_p.add_argument(
        "--include-continue",
        action="store_true",
        help="Mention continue unit when the due list is empty (still skips send by default)",
    )
    remind_p.add_argument(
        "--notify-empty",
        action="store_true",
        help="Send a notification even when nothing is due",
    )
    _add_shared_flags(remind_p)

    return parser


def cmd_extract(args: argparse.Namespace, config: PipelineConfig) -> int:
    """Run the Docling extraction stage."""
    metadata = extract_pdf(args.pdf, args.output_dir, force=args.force)
    print(
        f"Extracted {metadata.source_filename} "
        f"(pages={metadata.page_count}, sha256={metadata.source_sha256[:12]}…)"
    )
    for key, path in metadata.output_paths.items():
        print(f"  {key}: {path}")
    if metadata.warnings:
        print(f"  warnings: {len(metadata.warnings)}")
    return 0


def cmd_normalize(args: argparse.Namespace, config: PipelineConfig) -> int:
    """Run normalization on Markdown and write intermediate JSON."""
    output_dir: Path = args.output_dir
    input_path: Path = args.input or (output_dir / "intermediate" / "constitution.md")
    if not input_path.exists():
        raise ConstitutionMemorizerError(f"Normalize input not found: {input_path}")

    text = read_text(input_path)
    page_count = None
    meta_path = output_dir / "raw" / "extraction_metadata.json"
    if meta_path.exists():
        meta = read_json(meta_path)
        page_count = meta.get("page_count")

    lines, events, stats = normalize_document(
        text,
        config,
        estimated_page_count=page_count,
    )

    normalized_path = output_dir / "intermediate" / "normalized_lines.json"
    events_path = output_dir / "intermediate" / "parsing_events.json"

    payload = {
        "source": str(input_path),
        "line_count": len(lines),
        "stats": stats,
        "lines": lines_to_serializable(lines),
    }
    write_json(normalized_path, payload, force=args.force)
    write_json(
        events_path,
        [e.model_dump(mode="json") for e in events],
        force=args.force,
    )
    print(
        f"Normalized {len(lines)} lines "
        f"(headers_removed={stats['repeated_headers_removed']}, "
        f"duplicates_removed={stats['duplicate_blocks_removed']}, "
        f"page_numbers_removed={stats['page_numbers_removed']})"
    )
    print(f"  {normalized_path}")
    print(f"  {events_path}")
    return 0


def _load_lines_for_parse(input_path: Path) -> tuple[list, DocumentMetadata | None]:
    """Load either Markdown or normalized_lines.json for parsing."""
    metadata = None
    if input_path.suffix.lower() == ".json":
        data = read_json(input_path)
        from constitution_memorizer.normalization.line_normalizer import NormalizedLine

        lines = [
            NormalizedLine(
                index=item.get("index", i),
                text=item.get("text", ""),
                page_number=item.get("page_number"),
                original_text=item.get("original_text"),
                kept=item.get("kept", True),
                removal_reason=item.get("removal_reason"),
            )
            for i, item in enumerate(data.get("lines", []))
        ]
        return lines, metadata

    text = read_text(input_path)
    from constitution_memorizer.normalization.line_normalizer import NormalizedLine

    lines = [
        NormalizedLine(index=i, text=line)
        for i, line in enumerate(text.splitlines())
    ]
    return lines, metadata


def cmd_parse(args: argparse.Namespace, config: PipelineConfig) -> int:
    """Parse normalized content into constitution JSON."""
    output_dir: Path = args.output_dir
    input_path: Path
    if args.input is not None:
        input_path = args.input
    else:
        normalized = output_dir / "intermediate" / "normalized_lines.json"
        markdown = output_dir / "intermediate" / "constitution.md"
        input_path = normalized if normalized.exists() else markdown

    if not input_path.exists():
        raise ConstitutionMemorizerError(f"Parse input not found: {input_path}")

    lines, _ = _load_lines_for_parse(input_path)

    # Prefer running normalization if raw markdown was given without normalized lines.
    if input_path.suffix.lower() != ".json":
        lines, norm_events, stats = normalize_document(
            "\n".join(ln.text for ln in lines),
            config,
        )
    else:
        norm_events = []
        stats = {
            "repeated_headers_removed": 0,
            "duplicate_blocks_removed": 0,
            "page_numbers_removed": 0,
        }

    metadata = DocumentMetadata(schema_version=config.schema_version)
    meta_path = output_dir / "raw" / "extraction_metadata.json"
    if meta_path.exists():
        meta = read_json(meta_path)
        metadata = DocumentMetadata(
            title="The Constitution of India",
            source_filename=meta.get("source_filename", ""),
            source_path=meta.get("source_path"),
            source_sha256=meta.get("source_sha256", ""),
            page_count=meta.get("page_count"),
            extracted_at=meta.get("extracted_at", ""),
            schema_version=config.schema_version,
            file_size_bytes=meta.get("file_size_bytes"),
            docling_version=meta.get("docling_version"),
            ocr_used=meta.get("ocr_used"),
        )

    document, parse_events = parse_lines(lines, metadata=metadata)

    out_json = output_dir / "output" / "constitution.json"
    out_min = output_dir / "output" / "constitution.min.json"
    rejected = output_dir / "rejected" / "unclassified_text.json"
    events_path = output_dir / "intermediate" / "parsing_events.json"

    doc_dict = model_to_dict(document)
    write_json(out_json, doc_dict, force=args.force, indent=2)
    write_json(out_min, doc_dict, force=args.force, minified=True)
    write_json(
        rejected,
        [u.model_dump(mode="json") for u in document.unclassified_content],
        force=args.force,
    )

    all_events = [
        *[e.model_dump(mode="json") for e in norm_events],
        *[e.model_dump(mode="json") for e in parse_events],
    ]
    # Merge with existing events if present.
    if events_path.exists() and not args.force:
        # Append-safe path: read existing then rewrite with force for merge.
        existing = read_json(events_path)
        if isinstance(existing, list):
            all_events = existing + all_events
        write_json(events_path, all_events, force=True)
    else:
        write_json(events_path, all_events, force=args.force)

    # Also refresh normalized_lines if we normalized inline.
    if input_path.suffix.lower() != ".json":
        write_json(
            output_dir / "intermediate" / "normalized_lines.json",
            {
                "source": str(input_path),
                "line_count": len(lines),
                "stats": stats,
                "lines": lines_to_serializable(lines),
            },
            force=True,
        )

    summary = document.extraction_summary
    print(
        f"Parsed parts={summary.parts_found} articles={summary.articles_found} "
        f"schedules={summary.schedules_found} footnotes={summary.footnotes_found} "
        f"unclassified={summary.unclassified_blocks}"
    )
    print(f"  {out_json}")
    print(f"  {out_min}")
    print(f"  {rejected}")
    return 0


def cmd_validate(args: argparse.Namespace, config: PipelineConfig) -> int:
    """Validate constitution JSON and write extraction_report.json."""
    output_dir: Path = args.output_dir
    input_path: Path = args.input or (output_dir / "output" / "constitution.json")
    if not input_path.exists():
        raise ConstitutionMemorizerError(f"Validate input not found: {input_path}")

    data = read_json(input_path)
    try:
        doc = ConstitutionDocument.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        raise ConstitutionMemorizerError(f"Schema validation failed: {exc}") from exc

    stats = {"duplicate_blocks_removed": 0, "repeated_headers_removed": 0}
    norm_path = output_dir / "intermediate" / "normalized_lines.json"
    if norm_path.exists():
        norm = read_json(norm_path)
        stats.update(norm.get("stats") or {})

    report = build_report(
        doc,
        source_file=doc.document.source_filename or str(input_path),
        page_count=doc.document.page_count,
        duplicate_blocks_removed=int(stats.get("duplicate_blocks_removed", 0)),
        repeated_headers_removed=int(stats.get("repeated_headers_removed", 0)),
    )
    report_path = output_dir / "output" / "extraction_report.json"
    write_json(report_path, report.model_dump(mode="json"), force=args.force)
    print(format_report_summary(report))
    print(f"Report written to {report_path}")
    # Warnings do not fail; schema/structural errors set failed status but still exit 0
    # unless the document could not be loaded. Unrecoverable issues already raised.
    return 0


def cmd_correct(args: argparse.Namespace, config: PipelineConfig) -> int:
    """Apply correction overlay and write constitution.reviewed.json."""
    from constitution_memorizer.corrections.apply_corrections import (
        apply_corrections,
        load_corrections,
    )

    output_dir: Path = args.output_dir
    input_path: Path = args.input or (output_dir / "output" / "constitution.json")
    if not input_path.exists():
        raise ConstitutionMemorizerError(f"Correct input not found: {input_path}")

    doc = ConstitutionDocument.model_validate(read_json(input_path))
    corrections = load_corrections(args.corrections)
    reviewed, changes = apply_corrections(doc, corrections)
    out_path = output_dir / "output" / "constitution.reviewed.json"
    write_json(out_path, model_to_dict(reviewed), force=args.force)
    print(f"Applied corrections from {args.corrections}")
    for change in changes[:30]:
        print(f"  - {change}")
    if len(changes) > 30:
        print(f"  ... and {len(changes) - 30} more")
    print(f"Reviewed JSON: {out_path}")
    return 0


def cmd_review_report(args: argparse.Namespace, config: PipelineConfig) -> int:
    """Write corpus_review_report.json summarizing uncertain parse areas."""
    from constitution_memorizer.validation.review_report import build_corpus_review_report

    output_dir: Path = args.output_dir
    input_path: Path = args.input or (output_dir / "output" / "constitution.json")
    if not input_path.exists():
        raise ConstitutionMemorizerError(f"Review input not found: {input_path}")

    doc = ConstitutionDocument.model_validate(read_json(input_path))
    report = build_corpus_review_report(doc)
    out_path = output_dir / "output" / "corpus_review_report.json"
    write_json(out_path, report, force=args.force)
    print(
        f"Corpus review: unique_articles={report['unique_article_numbers']} "
        f"dup_candidates={len(report['duplicate_article_candidates'])} "
        f"missing_schedules={report['missing_schedules']}"
    )
    print(f"Report written to {out_path}")
    return 0


def cmd_pipeline(args: argparse.Namespace, config: PipelineConfig) -> int:
    """Run the full extract → normalize → parse → validate pipeline."""
    print("=== extract ===")
    rc = cmd_extract(args, config)
    if rc != 0:
        return rc

    # Reuse namespace with defaults for subsequent stages.
    args.input = None
    print("=== normalize ===")
    rc = cmd_normalize(args, config)
    if rc != 0:
        return rc

    print("=== parse ===")
    # Prefer normalized_lines.json
    args.input = args.output_dir / "intermediate" / "normalized_lines.json"
    rc = cmd_parse(args, config)
    if rc != 0:
        return rc

    print("=== validate ===")
    args.input = args.output_dir / "output" / "constitution.json"
    rc = cmd_validate(args, config)
    return rc


def cmd_generate_units(args: argparse.Namespace, config: PipelineConfig) -> int:
    """Generate learning units from the reviewed Bare Act JSON (Sprint 1)."""
    from constitution_memorizer.learning.learning_unit_generator import (
        generate_learning_units_from_path,
        summarize_units,
    )

    output_dir: Path = args.output_dir
    input_path: Path = args.input or (
        output_dir / "output" / "constitution.reviewed.json"
    )
    output_path: Path = args.output or (output_dir / "output" / "learning_units.json")

    result = generate_learning_units_from_path(
        input_path,
        output_path,
        force=args.force,
    )
    stats = summarize_units(result)
    print(
        f"Generated {stats['unit_count']} learning units "
        f"(avg_chars={stats['avg_chars']}, "
        f"min={stats['min_chars']}, max={stats['max_chars']}, "
        f"split_capable={stats.get('allows_letter_split', 0)})"
    )
    for unit_type, count in sorted(stats["by_type"].items()):
        print(f"  {unit_type}: {count}")
    print(f"Wrote {output_path}")
    return 0


def cmd_serve(args: argparse.Namespace, config: PipelineConfig) -> int:
    """Run the FastAPI learning UI with uvicorn."""
    import os

    import uvicorn

    from constitution_memorizer.multiuser.settings import (
        clear_settings_cache,
        load_env_file,
    )
    from constitution_memorizer.web.app import create_app

    env_path = load_env_file()
    clear_settings_cache()
    if env_path is not None:
        print(f"Loaded environment from {env_path}")

    output_dir: Path = args.output_dir
    units_path = args.units or (output_dir / "output" / "learning_units.json")
    db_path = args.db or (output_dir / "progress" / "progress.db")
    reviewed_path = args.reviewed or (
        output_dir / "output" / "constitution.reviewed.json"
    )
    port = args.port
    if port is None:
        port = int(os.environ.get("PORT", "8000"))
    multiuser = os.environ.get("MULTIUSER_ENABLED", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    # Railway injects RAILWAY_ENVIRONMENT. Use the boot-safe ASGI wrapper so
    # /healthz is reachable even if this process was started via `cli serve`.
    if os.environ.get("RAILWAY_ENVIRONMENT"):
        from constitution_memorizer.asgi import app as hosted_app

        print(f"Serving hosted UI on http://{args.host}:{port}")
        uvicorn.run(hosted_app, host=args.host, port=port, log_level="info")
        return 0
    app = create_app(
        units_path=units_path,
        db_path=db_path,
        reviewed_path=reviewed_path,
        multiuser=multiuser,
    )
    print(f"Serving learning UI on http://{args.host}:{port}")
    print(f"  units={units_path}")
    print(f"  db={db_path}")
    print(f"  reviewed={reviewed_path}")
    print(f"  multiuser={multiuser}")
    uvicorn.run(app, host=args.host, port=port, log_level="info")
    return 0


def cmd_send_reminders(args: argparse.Namespace, config: PipelineConfig) -> int:
    """Build today's due digest and send via the selected notifier."""
    import os
    from datetime import date, datetime

    from constitution_memorizer.notifications import build_study_digest, get_notifier
    from constitution_memorizer.notifications.schedule import should_notify
    from constitution_memorizer.progress.memory import MemoryEngine
    from constitution_memorizer.progress.scheduler import ReminderEngine

    output_dir: Path = args.output_dir
    units_path = args.units or (output_dir / "output" / "learning_units.json")
    db_path = args.db or (output_dir / "progress" / "progress.db")
    if not units_path.exists():
        raise ConstitutionMemorizerError(f"learning units not found: {units_path}")

    now = datetime.now().astimezone().replace(second=0, microsecond=0)
    if args.at:
        raw = args.at.strip()
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise ConstitutionMemorizerError(
                f"Invalid --at datetime (use YYYY-MM-DDTHH:MM): {args.at}"
            ) from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=now.tzinfo)
        now = parsed.replace(second=0, microsecond=0)

    as_of = date.fromisoformat(args.as_of) if args.as_of else now.date()
    base_url = (
        args.host_url
        or os.environ.get("REMINDER_BASE_URL")
        or "http://127.0.0.1:8001/"
    )
    engine = ReminderEngine.from_paths(db_path, units_path)
    memory = MemoryEngine.from_db_path(db_path)
    digest = build_study_digest(
        engine,
        as_of=as_of,
        base_url=base_url,
        include_continue=bool(args.include_continue or args.notify_empty),
        memory=memory,
    )

    if digest.is_empty and not args.notify_empty:
        print(f"{as_of.isoformat()}: nothing due — skip send")
        if args.include_continue and digest.continue_title:
            print(f"  continue: {digest.continue_title}")
        return 0

    frequency = engine.get_notification_frequency()
    last_slot = engine.repo.get_notification_last_slot(engine.user_id)
    # --notify-empty bypasses cadence so tests/manual pings still work.
    if not args.notify_empty:
        decision = should_notify(
            frequency=frequency,
            now=now,
            due_count=digest.due_count,
            last_slot=last_slot,
        )
        if not decision.should_send:
            print(
                f"{as_of.isoformat()} {now.strftime('%H:%M')} "
                f"({frequency}): skip — {decision.reason}"
            )
            return 0

    title = digest.notification_title()
    body = digest.notification_body()
    channel = "console" if args.dry_run else args.channel
    notifier = get_notifier(channel)
    notifier.send(title, body)
    engine.repo.set_notification_last_slot(engine.user_id, now)
    print(
        f"Sent via {channel}: {digest.due_count} due "
        f"({as_of.isoformat()} {now.strftime('%H:%M')}, {frequency})"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(getattr(args, "verbose", False))

    try:
        config = load_config(getattr(args, "config", None))
        command = args.command
        if command == "extract":
            return cmd_extract(args, config)
        if command == "normalize":
            return cmd_normalize(args, config)
        if command == "parse":
            return cmd_parse(args, config)
        if command == "validate":
            return cmd_validate(args, config)
        if command == "correct":
            return cmd_correct(args, config)
        if command == "review-report":
            return cmd_review_report(args, config)
        if command == "pipeline":
            return cmd_pipeline(args, config)
        if command == "generate-units":
            return cmd_generate_units(args, config)
        if command == "serve":
            return cmd_serve(args, config)
        if command == "send-reminders":
            return cmd_send_reminders(args, config)
        parser.error(f"Unknown command: {command}")
        return 2
    except OverwriteRefusedError as exc:
        logger.error("%s", exc)
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ConstitutionMemorizerError as exc:
        logger.error("%s", exc)
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
