#!/usr/bin/env python3
"""Validate extracted gettext alert messages and compiled EN/ES catalogs."""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

from babel.messages.catalog import Catalog
from babel.messages.extract import extract
from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src" / "swelter" / "i18n_alerts.py"
LOCALES = ROOT / "src" / "swelter" / "locales"
POT = LOCALES / "alerts.pot"
LANGUAGES = ("en", "es")
_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}", re.IGNORECASE)


def _read_catalog(path: Path, locale: str | None = None) -> Catalog:
    with path.open(encoding="utf-8") as handle:
        return read_po(handle, locale=locale, domain="alerts", abort_invalid=True)


def _ids(catalog: Catalog) -> set[str]:
    return {message.id for message in catalog if isinstance(message.id, str) and message.id}


def _extracted_ids() -> set[str]:
    with SOURCE.open("rb") as source:
        return {
            message
            for _line, message, _comments, _context in extract(
                "python", source, options={"encoding": "utf-8"}
            )
            if isinstance(message, str)
        }


def _placeholders(value: str) -> set[str]:
    return set(_PLACEHOLDER.findall(value))


def _check_translation(lang: str, template_ids: set[str]) -> list[str]:
    problems: list[str] = []
    po = LOCALES / lang / "LC_MESSAGES" / "alerts.po"
    mo = po.with_suffix(".mo")
    catalog = _read_catalog(po, locale=lang)
    catalog_ids = _ids(catalog)
    if catalog_ids != template_ids:
        problems.append(
            f"{lang} key drift: missing={sorted(template_ids - catalog_ids)}, "
            f"extra={sorted(catalog_ids - template_ids)}"
        )
    for message in catalog:
        if not isinstance(message.id, str) or not message.id:
            continue
        if not isinstance(message.string, str) or not message.string.strip():
            problems.append(f"{lang}: untranslated message {message.id!r}")
            continue
        if _placeholders(message.id) != _placeholders(message.string):
            problems.append(f"{lang}: placeholder drift in {message.id!r}")
        problems.extend(f"{lang}: {message.id!r}: {error}" for error in message.check())

    compiled = io.BytesIO()
    write_mo(compiled, catalog)
    if not mo.is_file() or mo.read_bytes() != compiled.getvalue():
        problems.append(f"{lang}: compiled alerts.mo is missing or stale")
    return problems


def main() -> int:
    problems: list[str] = []
    template_ids = _ids(_read_catalog(POT))
    extracted = _extracted_ids()
    if extracted != template_ids:
        problems.append(
            "POT extraction drift: "
            f"missing={sorted(extracted - template_ids)}, stale={sorted(template_ids - extracted)}"
        )

    for lang in LANGUAGES:
        problems.extend(_check_translation(lang, template_ids))

    if problems:
        for problem in problems:
            print(f"  [FAIL] {problem}", file=sys.stderr)
        return 1
    print(
        f"gettext: PASS ({len(template_ids)} extracted messages; "
        f"{len(LANGUAGES)} complete, compiled catalogs)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
