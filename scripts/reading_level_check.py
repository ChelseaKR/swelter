#!/usr/bin/env python3
"""Reading-level gate for resident-facing civic UI copy (ACCESSIBILITY A11Y-23).

Runs a deterministic Flesch-Kincaid grade level calculation over the English strings in
``web/i18n/en.json`` — the source catalog the Spanish translation is keyed against — and fails
if the reading level is above US Grade 8. Heat and air-quality guidance has to be usable by the
residents it is written for, not just the people who wrote it.

Short UI labels ("Units", "Language", a single word or two) are not prose and the Flesch-Kincaid
formula is not meaningful on them, so this only scores values with at least
``MIN_WORDS_FOR_SCORING`` words — the sentence- and paragraph-length copy (trust notes, alert
explanations, guidance text) where reading level actually matters.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EN_CATALOG = ROOT / "web" / "i18n" / "en.json"

#: US Grade 8 is the standard's floor for resident-facing civic copy (A11Y-23).
GRADE_FLOOR = 8.0

#: Short labels/buttons aren't prose; Flesch-Kincaid needs enough words to mean anything.
MIN_WORDS_FOR_SCORING = 6

_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
_SENTENCE_END = re.compile(r"[.!?]+(?:\s|$)")
_VOWELS = frozenset("aeiouy")
_MF2_DECLARATION = re.compile(r"(?m)^\.(?:input|match)\b[^\n]*$")
_MF2_VARIANT = re.compile(r"(?m)^(?:one|\*)\s+\{\{")
_MF2_EXPRESSION = re.compile(r"\{\$[A-Za-z][A-Za-z0-9_-]*(?:\s+:[^}]*)?\}")


def _readable_text(message: str) -> str:
    """Remove MF2 control syntax while retaining every resident-visible branch as prose."""
    text = _MF2_DECLARATION.sub("", message)
    text = _MF2_VARIANT.sub("", text).replace("}}", "")
    # A one-syllable token preserves the value's word position without scoring identifier names.
    return _MF2_EXPRESSION.sub("one", text)


def _syllables(word: str) -> int:
    """Return a stable English syllable estimate suitable for a lint gate.

    This deliberately avoids a corpus-backed NLP dependency: resident copy is linted from
    committed text only, and the algorithm must behave the same offline and in release CI.
    """
    cleaned = re.sub(r"[^a-z]", "", word.lower())
    if not cleaned:
        return 0
    groups = 0
    previous_vowel = False
    for char in cleaned:
        is_vowel = char in _VOWELS
        if is_vowel and not previous_vowel:
            groups += 1
        previous_vowel = is_vowel
    if cleaned.endswith("e") and not cleaned.endswith(("le", "ye")) and groups > 1:
        groups -= 1
    if cleaned.endswith("es") and len(cleaned) > 3 and cleaned[-3] not in _VOWELS and groups > 1:
        groups -= 1
    return max(1, groups)


def flesch_kincaid_grade(text: str) -> float:
    """Compute Flesch-Kincaid grade with a deterministic, dependency-free tokenizer."""
    words = _WORD.findall(text)
    if not words:
        return 0.0
    sentences = max(1, len(_SENTENCE_END.findall(text)))
    syllables = sum(_syllables(word) for word in words)
    return 0.39 * (len(words) / sentences) + 11.8 * (syllables / len(words)) - 15.59


def _scorable_strings(catalog: dict[str, str]) -> dict[str, str]:
    plain = {key: _readable_text(value) for key, value in catalog.items()}
    return {k: v for k, v in plain.items() if len(v.split()) >= MIN_WORDS_FOR_SCORING}


def main() -> int:
    catalog = json.loads(EN_CATALOG.read_text(encoding="utf-8"))
    scorable = _scorable_strings(catalog)

    over_floor: list[tuple[str, float]] = []
    for key, text in sorted(scorable.items()):
        grade = flesch_kincaid_grade(text)
        if grade > GRADE_FLOOR:
            over_floor.append((key, grade))

    corpus = " ".join(scorable.values())
    corpus_grade = flesch_kincaid_grade(corpus) if corpus else 0.0

    if over_floor:
        print(
            f"  [FAIL] {len(over_floor)}/{len(scorable)} scored strings exceed "
            f"grade {GRADE_FLOOR:.0f} (corpus average: grade {corpus_grade:.1f})"
        )
        for key, grade in over_floor:
            print(f"           - {key!r}: grade {grade:.1f}")
        print("reading-level: simplify the strings above to US Grade 8 or lower", file=sys.stderr)
        return 1

    print(
        f"  [PASS] all {len(scorable)} scored strings are at or below grade {GRADE_FLOOR:.0f} "
        f"(corpus average: grade {corpus_grade:.1f})"
    )
    print("reading-level: en.json civic copy is at or below US Grade 8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
