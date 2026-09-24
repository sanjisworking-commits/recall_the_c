"""Playground mode-progress read models. No revision scheduling."""

from __future__ import annotations

from dataclasses import dataclass

from constitution_memorizer.playground.learning.modes import (
    PLAYGROUND_LEARN_MODES,
    TOTAL_PLAYGROUND_MODES,
    next_learn_mode,
)

MODE_STATUS_IN_PROGRESS = "in_progress"
MODE_STATUS_COMPLETED = "completed"


@dataclass(frozen=True)
class ModeProgressRow:
    source_locator: str
    mode: str
    status: str
    attempt_count: int
    first_started_at: str | None
    last_attempt_at: str | None
    completed_at: str | None
    source_version: str
    source_hash: str


@dataclass(frozen=True)
class ProvisionModeProgress:
    """Section-level six-mode fact. Not a Learned / Day-1 trigger."""

    source_locator: str
    completed_modes: tuple[str, ...]
    in_progress_modes: tuple[str, ...]
    completed_count: int
    total_modes: int
    next_mode: str | None
    source_outdated: bool

    @property
    def all_methods_complete(self) -> bool:
        return self.completed_count >= self.total_modes


def empty_provision_mode_progress(source_locator: str) -> ProvisionModeProgress:
    return ProvisionModeProgress(
        source_locator=source_locator,
        completed_modes=(),
        in_progress_modes=(),
        completed_count=0,
        total_modes=TOTAL_PLAYGROUND_MODES,
        next_mode=PLAYGROUND_LEARN_MODES[0],
        source_outdated=False,
    )


def build_provision_mode_progress(
    source_locator: str,
    rows: list[ModeProgressRow] | tuple[ModeProgressRow, ...],
    *,
    live_hash: str = "",
) -> ProvisionModeProgress:
    completed: list[str] = []
    in_progress: list[str] = []
    outdated = False
    seen: dict[str, ModeProgressRow] = {}
    for row in rows:
        if row.source_locator != source_locator:
            continue
        seen[row.mode] = row
        if live_hash and row.source_hash != live_hash:
            outdated = True
    for mode in PLAYGROUND_LEARN_MODES:
        row = seen.get(mode)
        if row is None:
            continue
        if row.status == MODE_STATUS_COMPLETED:
            completed.append(mode)
        elif row.status == MODE_STATUS_IN_PROGRESS:
            in_progress.append(mode)
    completed_t = tuple(completed)
    return ProvisionModeProgress(
        source_locator=source_locator,
        completed_modes=completed_t,
        in_progress_modes=tuple(in_progress),
        completed_count=len(completed_t),
        total_modes=TOTAL_PLAYGROUND_MODES,
        next_mode=next_learn_mode(completed_t),
        source_outdated=outdated,
    )


def group_provision_mode_progress(
    rows: list[ModeProgressRow] | tuple[ModeProgressRow, ...],
    locators: list[str] | tuple[str, ...] | None = None,
    *,
    live_hashes: dict[str, str] | None = None,
) -> dict[str, ProvisionModeProgress]:
    """One pass over law-scoped rows. No per-mode SQL."""

    by_locator: dict[str, list[ModeProgressRow]] = {}
    for row in rows:
        by_locator.setdefault(row.source_locator, []).append(row)
    keys = list(locators) if locators is not None else list(by_locator)
    hashes = live_hashes or {}
    return {
        locator: build_provision_mode_progress(
            locator,
            by_locator.get(locator, ()),
            live_hash=hashes.get(locator, ""),
        )
        for locator in keys
    }
