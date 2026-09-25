"""Deterministic Playground Test quizzes from canonical section text.

Independent of ``LearningUnit``. Keyword fill is always available for a
non-empty body. MCQ is added only when the same section yields enough
safe distractors. Never hydrates another Act. Never stores answer keys.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from hashlib import sha256

MIN_KEYWORD_LETTERS = 6
FALLBACK_KEYWORD_LETTERS = 4
CONTEXT_WORDS = 8
DEFAULT_QUESTION_COUNT = 5
MCQ_DISTRACTORS = 3

_KIND_MCQ = "mcq"
_KIND_FILL = "fill"
_NON_ALNUM = re.compile(r"[^a-z0-9]")
_LETTERS = re.compile(r"[^A-Za-z]")
_TRIM = re.compile(r"^\W+|\W+$")


def normalize_answer(text: object) -> str:
    return _NON_ALNUM.sub("", str(text).lower())


def quiz_seed(
    law_id: str,
    source_locator: str,
    cycle: int,
    *,
    source_hash: str = "",
    rung_days: int | None = None,
) -> int:
    if rung_days:
        payload = f"{law_id}:{source_locator}:{int(cycle)}:{int(rung_days)}:{source_hash}"
    else:
        payload = f"{law_id}:{source_locator}:{int(cycle)}:{source_hash}"
    digest = sha256(payload.encode()).digest()
    return int.from_bytes(digest[:8], "big")


@dataclass(frozen=True)
class PlaygroundQuizQuestion:
    kind: str
    prompt: str
    options: tuple[str, ...] = ()
    answer_index: int = -1
    answer_text: str = ""

    def public_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "prompt": self.prompt,
            "options": list(self.options),
        }


@dataclass(frozen=True)
class _KeywordCandidate:
    index: int
    surface: str
    window: tuple[str, ...]


def _letter_len(word: str) -> int:
    return len(_LETTERS.sub("", word))


def _clean_word(word: str) -> str:
    return _TRIM.sub("", word)


def _keyword_candidates(text: str, *, min_letters: int) -> list[_KeywordCandidate]:
    words = text.split()
    candidates: list[_KeywordCandidate] = []
    for i, raw in enumerate(words):
        clean = _clean_word(raw)
        if _letter_len(clean) < min_letters:
            continue
        lo = max(0, i - CONTEXT_WORDS)
        hi = min(len(words), i + CONTEXT_WORDS + 1)
        norm = normalize_answer(clean)
        if any(
            j != i and normalize_answer(_clean_word(words[j])) == norm
            for j in range(lo, hi)
        ):
            continue
        window = tuple("____" if j == i else words[j] for j in range(lo, hi))
        prefix = ("…",) if lo > 0 else ()
        suffix = ("…",) if hi < len(words) else ()
        candidates.append(
            _KeywordCandidate(index=i, surface=clean, window=prefix + window + suffix)
        )
    return candidates


def _fallback_first_word(text: str) -> list[_KeywordCandidate]:
    words = text.split()
    if not words:
        return []
    clean = _clean_word(words[0]) or words[0]
    window = ("____",) + tuple(words[1: CONTEXT_WORDS + 1])
    suffix = ("…",) if len(words) > CONTEXT_WORDS + 1 else ()
    return [_KeywordCandidate(index=0, surface=clean, window=window + suffix)]


def keyword_candidates_for_body(text: str) -> list[_KeywordCandidate]:
    body = (text or "").strip()
    if not body:
        return []
    for min_letters in (MIN_KEYWORD_LETTERS, FALLBACK_KEYWORD_LETTERS):
        found = _keyword_candidates(body, min_letters=min_letters)
        if found:
            return found
    return _fallback_first_word(body)


def _dedupe_normalized(values: list[str], *, exclude: str) -> list[str]:
    excluded = normalize_answer(exclude)
    seen: set[str] = set()
    kept: list[str] = []
    for value in values:
        norm = normalize_answer(value)
        if not norm or norm == excluded or norm in seen:
            continue
        seen.add(norm)
        kept.append(value)
    return kept


def _same_section_distractors(text: str, *, exclude: str) -> list[str]:
    pool: list[str] = []
    for word in text.split():
        clean = _clean_word(word)
        if _letter_len(clean) >= FALLBACK_KEYWORD_LETTERS:
            pool.append(clean)
    return _dedupe_normalized(pool, exclude=exclude)


def _make_mcq(
    prompt: str, answer: str, distractors: list[str], rng: random.Random
) -> PlaygroundQuizQuestion | None:
    if len(distractors) < MCQ_DISTRACTORS:
        return None
    options = [answer] + rng.sample(distractors, MCQ_DISTRACTORS)
    rng.shuffle(options)
    return PlaygroundQuizQuestion(
        kind=_KIND_MCQ,
        prompt=prompt,
        options=tuple(options),
        answer_index=options.index(answer),
    )


def _keyword_fill(candidate: _KeywordCandidate) -> PlaygroundQuizQuestion:
    return PlaygroundQuizQuestion(
        kind=_KIND_FILL,
        prompt="Fill in the missing word: “" + " ".join(candidate.window) + "”",
        answer_text=candidate.surface,
    )


def build_section_quiz(
    *,
    law_id: str,
    source_locator: str,
    canonical_body: str,
    cycle: int,
    source_hash: str = "",
    count: int = DEFAULT_QUESTION_COUNT,
    rung_days: int | None = None,
) -> list[PlaygroundQuizQuestion]:
    body = (canonical_body or "").strip()
    keywords = keyword_candidates_for_body(body)
    if not keywords:
        return []
    rng = random.Random(
        quiz_seed(
            law_id,
            source_locator,
            cycle,
            source_hash=source_hash,
            rung_days=rung_days,
        )
    )
    needed = min(len(keywords), max(1, count))
    selected = rng.sample(keywords, needed)
    questions: list[PlaygroundQuizQuestion] = []
    mcq_budget = (len(selected) + 1) // 2
    for candidate in selected:
        made = None
        if mcq_budget > 0:
            made = _make_mcq(
                "Which word completes: “" + " ".join(candidate.window) + "”?",
                candidate.surface,
                _same_section_distractors(body, exclude=candidate.surface),
                rng,
            )
        if made is not None:
            questions.append(made)
            mcq_budget -= 1
        else:
            questions.append(_keyword_fill(candidate))
    rng.shuffle(questions)
    return questions


def has_section_quiz(canonical_body: str) -> bool:
    return bool(keyword_candidates_for_body(canonical_body or ""))


def coerce_quiz_answers(raw: object, count: int) -> list[object] | None:
    if not isinstance(raw, list) or len(raw) != count:
        return None
    answers: list[object] = []
    for item in raw:
        if isinstance(item, bool):
            return None
        if isinstance(item, int):
            answers.append(item)
        elif isinstance(item, str):
            answers.append(item)
        elif item is None:
            answers.append("")
        else:
            return None
    return answers


def grade_section_quiz(
    questions: list[PlaygroundQuizQuestion] | tuple[PlaygroundQuizQuestion, ...],
    answers: list[object] | tuple[object, ...],
) -> dict[str, object]:
    results: list[dict[str, object]] = []
    correct = 0
    for question, answer in zip(questions, answers):
        if question.kind == _KIND_MCQ:
            ok = isinstance(answer, int) and answer == question.answer_index
            expected = (
                question.options[question.answer_index]
                if 0 <= question.answer_index < len(question.options)
                else ""
            )
        else:
            ok = (
                isinstance(answer, str)
                and normalize_answer(answer) != ""
                and normalize_answer(answer) == normalize_answer(question.answer_text)
            )
            expected = question.answer_text
        results.append({"correct": bool(ok), "expected": expected})
        if ok:
            correct += 1
    return {
        "correct": correct,
        "total": len(questions),
        "results": results,
    }
