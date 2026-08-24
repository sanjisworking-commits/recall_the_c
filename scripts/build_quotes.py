#!/usr/bin/env python3
"""Curate civic quotes for the Recall the C interaction layer.

Filter, dedupe, normalize, and canonicalize only. Quote wording is never
paraphrased or rewritten. ``--source`` is required (no hardcoded path).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "reference" / "quotes.json"

MIN_LEN = 40
MAX_LEN = 220

# Conservative off-tone fragments — scholarly civic register only.
OFF_TONE = (
    "kiss slowly",
    "road trip",
    "hit the road",
    "best road",
    "motivate you",
    "with images",
    "stoic leadership",
    "moonlit garden",
    "hyenas of hate",
    "jackals of hypocrisy",
    "xoxoxo",
)

AUTHOR_CANON = (
    (
        re.compile(
            r"gandhi",
            re.I,
        ),
        "Mahatma Gandhi",
    ),
    (
        re.compile(r"ambedkar", re.I),
        "B. R. Ambedkar",
    ),
    (
        re.compile(r"\bobama\b", re.I),
        "Barack Obama",
    ),
)

_DATE_LIKE = re.compile(
    r"\b(?:\d{1,2}\s+)?(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|"
    r"may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)[a-z]*\.?\s+\d{4}\b"
    r"|\b(?:17|18|19|20)\d{2}\b",
    re.I,
)
_URL = re.compile(r"https?://|www\.", re.I)
_VOLUME = re.compile(r"\bvolume\b|\bvol\.?\b", re.I)
_JUNK_WORD = re.compile(
    r"\bquotes?\b|\bimages?\b|\bcollected works\b|\bmemo \d+",
    re.I,
)
_FOOTNOTE = re.compile(r"\[\d+\]|\[f\.\d+\]")
_ENDS_FUNCTION = re.compile(
    r"\b(and|or|but|the|a|an|of|to|in|for|with|that|which|who|as|"
    r"by|from|at|on|if|when|while|because|than|into|about|"
    r"has|have|had|be|been)\s*$",
    re.I,
)
_ENDS_CONNECTOR = re.compile(r"[,;:—–-]\s*$")
_TRAILING_ELLIPSIS = re.compile(r"\.\.\.\s*$")
_ENDS_STUB_SENTENCE = re.compile(r"[.!?]\s+I\s*$")
# Keep diacritics so "habría" / "für" stay one token.
_WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ']+")

# Closed-class English words — enough to tell English from Spanish/French/Hindi/etc.
_EN_STOP = frozenset(
    """
    the a an of to and in is that it for on with as was be by at or from this
    which are not have has been but they their you we i our your he she him her
    his its who what when where how if then than into about over after before
    while because would could should will can may must do does did done being
    were am upon without within among against between through during never
    always like than all no so just only even also more most such own other
    each every both few many much any some these those there here too very
    still yet already once again
    """.split()
)
# Distinctive markers that are not English closed-class words. Overlap
# tokens like "no"/"en"/"a"/"die" are omitted so English quotes survive.
_ES_MARK = frozenset(
    """
    el la los las un una es se con por para del al lo como más mas pero
    sus hay quien cuando porque también tambien está estan están son
    este esta estos estas muy ya nos le les su fue eran fueras que
    """.split()
)
_FR_MARK = frozenset(
    """
    le les des une dans pour avec cette vous nous aux qui est pas ne
    je tu elle ils elles mes tes sa ses
    autres puissent sont avons vivez vivre simplement
    """.split()
)
_IT_MARK = frozenset(
    """
    il gli dal cui suo sua suoi sue sono possono della degli nel nei
    anche più questo questa sono siamo siete loro
    """.split()
)
_DE_MARK = frozenset(
    """
    der das und den dem des ein eine einer eines nicht ich du er
    wir ihr einem einen
    """.split()
)
_ID_MARK = frozenset(
    """
    yang tidak untuk dalam adalah dengan orang pernah terlalu keinginan
    sungguh murni terkabul berputus takkan sibuk memahami asalnya iman
    tempat kekerasan senjata jiwanya lemah ada
    """.split()
)
_SL_MARK = frozenset(
    """
    nije nisu koji koja koje kada samo kao smo ste svoju svaki nekom
    nijeste dvojica kaficu oftamolog makedonski dubrovniku odnekud
    pojavi upita sede
    """.split()
)
_PT_MARK = frozenset(
    """
    não voce você pelo pela também tambem estão uma dos das são está
    """.split()
)


def _norm_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\u00a0", " ")).strip()


def _canonicalize_author(author: str) -> str:
    compact = _norm_space(author).strip('"“”\'’«»')
    for pattern, canon in AUTHOR_CANON:
        if pattern.search(compact):
            return canon
    return compact


def _is_all_caps_title(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 12:
        return False
    upper = sum(1 for c in letters if c.isupper())
    return upper / len(letters) >= 0.85


def _author_is_fragment(author: str) -> bool:
    if not author or len(author) < 2:
        return True
    if len(author) > 60:
        return True
    if re.search(r"\d", author):
        return True
    if ";" in author or ")." in author:
        return True
    if _VOLUME.search(author) or _DATE_LIKE.search(author):
        return True
    if _JUNK_WORD.search(author) or _URL.search(author):
        return True
    # Scrape leftovers sitting in the author field.
    if author[:1].islower():
        return True
    if author.startswith(("“", '"', "‘", "'")):
        return True
    if author.endswith(('."', ".”", '"', "”", "’")) and len(author.split()) >= 3:
        return True
    return False


def _letter_script_counts(text: str) -> tuple[int, int]:
    latin = other = 0
    for ch in text:
        if not ch.isalpha():
            continue
        name = unicodedata.name(ch, "")
        if "LATIN" in name:
            latin += 1
        else:
            other += 1
    return latin, other


_INDIC_ROMAN = frozenset(
    """
    hai hain hey par ki ke ko mein hum meri mujhe nahi nahin kaa bhi jo
    zindgi zindagi apne jati uthaye janaje khayenge banyenge damm tohh
    shirf kandhe jiyi
    """.split()
)


def _accented_letter_count(text: str) -> int:
    n = 0
    for ch in text:
        decomp = unicodedata.normalize("NFD", ch)
        if any(unicodedata.combining(c) for c in decomp):
            n += 1
        elif ch.lower() in "łøßæœđħ":
            n += 1
    return n


def _mark_count(tokens: list[str], marks: frozenset[str]) -> int:
    return sum(1 for w in tokens if w in marks)


def _is_non_english(text: str) -> bool:
    """Drop Hindi/Arabic/Cyrillic script and Latin-script non-English."""
    latin, other = _letter_script_counts(text)
    letters = latin + other
    if letters and other / letters >= 0.15:
        return True
    raw_tokens = _WORD.findall(text.lower())
    tokens: list[str] = []
    for word in raw_tokens:
        tokens.extend(part for part in word.split("'") if part)
    if len(tokens) < 6:
        return False
    en = sum(1 for w in tokens if w in _EN_STOP)
    es = _mark_count(tokens, _ES_MARK)
    fr = _mark_count(tokens, _FR_MARK)
    de = _mark_count(tokens, _DE_MARK)
    ident = _mark_count(tokens, _ID_MARK)
    slavic = _mark_count(tokens, _SL_MARK)
    pt = _mark_count(tokens, _PT_MARK)
    italian = _mark_count(tokens, _IT_MARK)
    if (
        es >= 3
        or fr >= 3
        or de >= 3
        or ident >= 2
        or slavic >= 2
        or pt >= 2
        or italian >= 2
    ):
        return True
    indic = sum(1 for w in tokens if w in _INDIC_ROMAN)
    if indic >= 3:
        return True
    accents = _accented_letter_count(text)
    if accents >= 3:
        return True
    ratio = en / len(tokens)
    if accents >= 1 and ratio < 0.12:
        return True
    if len(tokens) >= 8 and en == 0:
        return True
    return False


def _is_incomplete_text(text: str) -> bool:
    """Drop truncated scrapes, not merely unpunctuated aphorisms."""
    if _ENDS_CONNECTOR.search(text) or _ENDS_FUNCTION.search(text):
        return True
    if _TRAILING_ELLIPSIS.search(text):
        return True
    if _ENDS_STUB_SENTENCE.search(text):
        return True
    if _FOOTNOTE.search(text):
        return True
    if text.count("“") != text.count("”"):
        return True
    if text.count('"') % 2 == 1:
        return True
    if text[:1].islower():
        return True
    return False


def _text_is_junk(text: str) -> bool:
    if _is_all_caps_title(text):
        return True
    if _JUNK_WORD.search(text) or _URL.search(text) or _VOLUME.search(text):
        return True
    # Bibliographic date fragments ("11 April, 1910"), not years inside a sentence.
    if re.match(r"^\(?\d{1,2}\s+\w+,\s+\d{4}", text):
        return True
    lowered = text.lower()
    return any(frag in lowered for frag in OFF_TONE)


def curate(rows: list[dict]) -> tuple[list[dict[str, str]], Counter]:
    stats: Counter = Counter()
    stats["source"] = len(rows)
    kept: list[dict[str, str]] = []
    seen: set[str] = set()

    for row in rows:
        stats["seen"] += 1
        if not isinstance(row, dict):
            stats["not_object"] += 1
            continue
        text = _norm_space(str(row.get("text") or ""))
        author = _canonicalize_author(str(row.get("author") or ""))
        n = len(text)
        if n < MIN_LEN:
            stats["too_short"] += 1
            continue
        if n > MAX_LEN:
            stats["too_long"] += 1
            continue
        if _text_is_junk(text):
            stats["junk_text"] += 1
            continue
        if _is_non_english(text):
            stats["non_english"] += 1
            continue
        if _is_incomplete_text(text):
            stats["incomplete"] += 1
            continue
        if _author_is_fragment(author):
            stats["junk_author"] += 1
            continue
        key = text.casefold()
        if key in seen:
            stats["duplicate"] += 1
            continue
        seen.add(key)
        kept.append({"text": text, "author": author})

    stats["kept"] = len(kept)
    return kept, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        required=True,
        type=Path,
        help="Path to the raw civic quotes JSON array",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    source = args.source.expanduser().resolve()
    if not source.is_file():
        print(f"error: source not found: {source}", file=sys.stderr)
        return 1

    raw = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        print("error: source must be a JSON array", file=sys.stderr)
        return 1

    kept, stats = curate(raw)
    out = args.out.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(kept, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("quotes build audit")
    print(f"  source count     {stats['source']}")
    print(f"  too short (<{MIN_LEN}) {stats['too_short']}")
    print(f"  too long (>{MAX_LEN})  {stats['too_long']}")
    print(f"  junk text        {stats['junk_text']}")
    print(f"  non-English      {stats['non_english']}")
    print(f"  incomplete       {stats['incomplete']}")
    print(f"  junk author      {stats['junk_author']}")
    print(f"  duplicate        {stats['duplicate']}")
    print(f"  kept             {stats['kept']}")
    print(f"  wrote            {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
