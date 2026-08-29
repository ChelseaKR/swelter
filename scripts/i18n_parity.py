#!/usr/bin/env python3
"""EN/ES locale key-parity gate — a merge-blocking i18n check.

The dashboard ships two catalogs, ``web/i18n/en.json`` and ``web/i18n/es.json``, and the
language switch is a WCAG gate: a string that exists in one locale but not the other, or a
Spanish value left empty, is a hole a Spanish-speaking reader falls through at runtime. This
check holds the floor the a11y gate assumes — that the two catalogs describe the *same* set of
strings — so it cannot regress in a quiet PR.

The neighborhood-alerts feed uses compiled gettext catalogs. Its extraction, key/placeholder
parity, translation completeness, PO validation, and MO freshness are enforced separately by
``scripts/gettext_catalog_check.py``; this script owns the dashboard MF2 resource parity.

It is pure standard library, offline, and deterministic: it loads each catalog pair, flattens them
to dotted leaf keys (so nested groups are compared recursively, not by top-level object), and
compares the key sets. It fails, listing the offenders in sorted order, when a key is present
in one locale but missing from the other, or when a Spanish value is empty or whitespace.

Exit status is 0 when every catalog pair is at parity and 1 otherwise, with a per-check report.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
I18N = ROOT / "web" / "i18n"
EN = I18N / "en.json"
ES = I18N / "es.json"


def _flatten(obj: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten a (possibly nested) locale catalog to dotted leaf keys."""
    flat: dict[str, Any] = {}
    for key, value in obj.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(_flatten(value, path))
        else:
            flat[path] = value
    return flat


def _load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return _flatten(data)


def _check_catalog(label: str, en: dict[str, Any], es: dict[str, Any]) -> int:
    """Run the EN/ES parity checks for one catalog pair; print a report; return the failure
    count."""
    missing_in_es = sorted(set(en) - set(es))
    missing_in_en = sorted(set(es) - set(en))
    empty_es = sorted(
        key
        for key, value in es.items()
        if key in en and isinstance(value, str) and not value.strip()
    )

    checks: list[tuple[bool, str, list[str]]] = [
        # Two empty catalogs satisfy every set comparison below, so an emptied or truncated
        # en.json read as "EN/ES at key parity (0 keys)". Parity over nothing is not parity,
        # and this gate is the floor the accessibility gate assumes.
        (
            bool(en),
            f"the EN catalog has strings to compare ({len(en)} keys)",
            [] if en else ["the EN catalog flattened to zero keys"],
        ),
        (
            not missing_in_es,
            f"every EN key exists in ES ({len(missing_in_es)} missing)",
            missing_in_es,
        ),
        (
            not missing_in_en,
            f"every ES key exists in EN ({len(missing_in_en)} extra)",
            missing_in_en,
        ),
        (not empty_es, f"no empty ES values ({len(empty_es)} empty)", empty_es),
    ]

    print(f"{label}:")
    failed = 0
    for ok, message, offenders in checks:
        marker = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"  [{marker}] {message}")
        for key in offenders:
            print(f"           - {key}")

    total = len(checks)
    if failed:
        print(f"  {label}: {total - failed}/{total} parity checks passed", file=sys.stderr)
    else:
        print(f"  {label}: EN/ES at key parity ({len(en)} keys)")
    return failed


def main() -> int:
    for path in (EN, ES):
        if not path.is_file():
            print(f"i18n: {path} not found", file=sys.stderr)
            return 1

    failed = _check_catalog("web/i18n (dashboard)", _load(EN), _load(ES))

    if failed:
        print(f"i18n: {failed} parity check(s) failed", file=sys.stderr)
        return 1
    print("i18n: dashboard catalogs at EN/ES key parity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
