#!/usr/bin/env python3
"""Reading-level gate for resident-facing civic UI copy (ACCESSIBILITY A11Y-23).

Runs Flesch-Kincaid grade level (via ``textstat``) over the English strings in
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
import sys
from pathlib import Path

import textstat

ROOT = Path(__file__).resolve().parent.parent
EN_CATALOG = ROOT / "web" / "i18n" / "en.json"

#: US Grade 8 is the standard's floor for resident-facing civic copy (A11Y-23).
GRADE_FLOOR = 8.0

#: Short labels/buttons aren't prose; Flesch-Kincaid needs enough words to mean anything.
MIN_WORDS_FOR_SCORING = 6


def _scorable_strings(catalog: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in catalog.items() if len(v.split()) >= MIN_WORDS_FOR_SCORING}


def main() -> int:
    catalog = json.loads(EN_CATALOG.read_text(encoding="utf-8"))
    scorable = _scorable_strings(catalog)

    over_floor: list[tuple[str, float]] = []
    for key, text in sorted(scorable.items()):
        grade = textstat.flesch_kincaid_grade(text)
        if grade > GRADE_FLOOR:
            over_floor.append((key, grade))

    corpus = " ".join(scorable.values())
    corpus_grade = textstat.flesch_kincaid_grade(corpus) if corpus else 0.0

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
