#!/usr/bin/env python3
"""G12 CLDR/ICU freshness pin — merge-blocking guard (INTERNATIONALIZATION-STANDARD §4).

If a repo *bundles* CLDR/ICU locale data — via ``babel``/``pyicu`` on the Python side or a
CLDR-bearing package on the JS side — that data must be pinned to a fresh floor (``babel>=2.16``,
CLDR/ICU ``>= 48.2``) so residents never read stale place, number, or date formatting.

swelter pins Babel for gettext catalog construction, so the Python-side floor is enforced here.
The browser's MessageFormat 2 runtime delegates plural, number, and date locale behavior to native
``Intl``; it does not bundle a CLDR data snapshot. The browser's CLDR/ICU is kept fresh by the
vendor and is not pinnable in this repository.

This script is the guard that makes that state durable rather than assumed: it scans
``pyproject.toml`` and ``web/package.json`` for a CLDR/ICU-bearing
dependency and, the moment one appears, enforces the version floor. Pure standard library
(``tomllib``); exit status 0 when every bundled-data pin invariant holds and 1 otherwise.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
PACKAGE_JSON = ROOT / "web" / "package.json"

#: package name -> (floor, human note). A bundled CLDR/ICU dependency must meet its floor.
PY_FLOORS = {
    "babel": ((2, 16), "CLDR-backed formatting; standard floor babel>=2.16"),
    "pyicu": ((2, 12), "ICU bindings; keep ICU >= 48.2 via a fresh pyicu"),
    "tzdata": ((2026, 1), "IANA tz database; standard floor tzdata>=2026a"),
}
JS_FLOORS = {
    "full-icu": ((1, 5), "bundled ICU data; keep ICU >= 48.2"),
    "@formatjs/intl": ((2, 0), "CLDR-backed formatting"),
    "cldr-data": ((48, 2), "raw CLDR data; keep >= 48.2"),
}

_VER = re.compile(r"(\d+)(?:\.(\d+))?")


def _floor_version(spec: str) -> tuple[int, int] | None:
    """Extract the (major, minor) floor from a version constraint like '>=2.16,<3' or '^2.0'."""
    for piece in re.split(r"[,\s]+", spec):
        if ">=" in piece or "==" in piece or piece.startswith(("^", "~", "=")):
            m = _VER.search(piece)
            if m:
                return int(m.group(1)), int(m.group(2) or 0)
    m = _VER.search(spec)
    return (int(m.group(1)), int(m.group(2) or 0)) if m else None


def _py_deps() -> dict[str, str]:
    """Map dependency name -> version spec across runtime deps and every dependency group."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    specs: list[str] = list(data.get("project", {}).get("dependencies", []))
    for group in data.get("dependency-groups", {}).values():
        specs.extend(s for s in group if isinstance(s, str))
    for extra in data.get("project", {}).get("optional-dependencies", {}).values():
        specs.extend(extra)
    deps: dict[str, str] = {}
    for spec in specs:
        name = re.split(r"[<>=!~\[ ]", spec, maxsplit=1)[0].strip().lower()
        if name:
            deps[name] = spec
    return deps


def _js_deps() -> dict[str, str]:
    if not PACKAGE_JSON.is_file():
        return {}
    data = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    deps: dict[str, str] = {}
    for section in ("dependencies", "devDependencies"):
        deps.update({k.lower(): str(v) for k, v in data.get(section, {}).items()})
    return deps


def _check(deps: dict[str, str], floors: dict[str, tuple[tuple[int, int], str]]) -> list[str]:
    """Return a failure message for every bundled CLDR/ICU dep below its floor or missing a pin."""
    problems: list[str] = []
    for name, (floor, note) in floors.items():
        if name not in deps:
            continue
        spec = deps[name]
        got = _floor_version(spec)
        if got is None:
            problems.append(
                f"{name} is present but not pinned ({spec!r}); needs >= {floor} — {note}"
            )
        elif got < floor:
            problems.append(f"{name} {spec!r} is below the floor {floor} — {note}")
    return problems


def main() -> int:
    py = _py_deps()
    js = _js_deps()
    bundled = [n for n in PY_FLOORS if n in py] + [n for n in JS_FLOORS if n in js]
    problems = _check(py, PY_FLOORS) + _check(js, JS_FLOORS)

    ok = not problems
    marker = "PASS" if ok else "FAIL"
    if bundled:
        print(f"  [{marker}] bundled CLDR/ICU deps meet the freshness floor ({', '.join(bundled)})")
    else:
        print(f"  [{marker}] no bundled CLDR/ICU dependency to pin (G12 N/A-until-used)")
    for problem in problems:
        print(f"           - {problem}")

    if problems:
        print("i18n-cldr-pin: stale or unpinned CLDR/ICU dependency", file=sys.stderr)
        return 1
    if bundled:
        print("i18n-cldr-pin: all bundled CLDR/ICU dependencies meet the floor")
    else:
        print(
            "i18n-cldr-pin: formatting delegates to browser Intl; nothing to pin (N/A-until-used)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
