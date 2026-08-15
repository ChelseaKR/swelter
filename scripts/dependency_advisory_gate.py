#!/usr/bin/env python3
"""Adjudicate dependency advisories against the committed waiver registry.

Two scanners in this repository see the same npm dependency graph: `npm audit`
(``make security-node``) and OSV-Scanner (``make security-osv``). Neither one
can be told to accept a single reviewed advisory without also weakening what it
reports about everything else -- `npm audit` offers only ``--audit-level``, and
an OSV ignore list that nothing validates is an allowlist waiting to grow. So
both route through waivers.yml, which is the single dated, owned, expiring
record of what has been accepted, and this script is what makes the record
binding rather than decorative.

Two subcommands, each its own merge-blocking gate:

``npm-audit``
    Reads an ``npm audit --json`` report (stdin or ``--report``) and fails on
    every HIGH/CRITICAL advisory that is not matched, exactly, by a live
    waiver -- exact advisory id, exact package, exact severity. A new advisory
    fails. A second advisory in the same package fails. The waived advisory
    escalated to CRITICAL fails. An expired or malformed waiver accepts
    nothing, so the registry cannot rot quietly.

``osv-config``
    Proves osv-scanner.toml and waivers.yml still say the same thing: every
    ``[[IgnoredVulns]]`` entry has a live waiver with the same expiry, and
    every waiver claiming OSV coverage is present in the config. Adding an id
    to the scanner's ignore list without a waiver fails this gate.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
WAIVERS_PATH = ROOT / "waivers.yml"
OSV_CONFIG_PATH = ROOT / "osv-scanner.toml"

#: Severities the Node dependency gate blocks on; the `npm audit
#: --audit-level=high` floor this replaces, unchanged.
BLOCKING = frozenset({"high", "critical"})

#: The waiver kind these gates honour. Waivers of any other kind are ignored
#: here, so a semgrep waiver can never accept a dependency advisory.
KIND = "dependency-advisory"

REQUIRED_FIELDS = (
    "id",
    "control",
    "repo",
    "kind",
    "reason",
    "owner",
    "granted",
    "expires",
    "advisory",
    "package",
    "severity",
    "scanners",
)

# `  - key: value` opens a waiver, `    key: value` adds a field, and anything
# indented further continues the field above it -- so folded prose inside
# `reason:` is never mistaken for a field, whatever it says.
_ENTRY_RE = re.compile(r"^  - ([a-z_]+):[ \t]*(.*)$")
_FIELD_RE = re.compile(r"^    ([a-z_]+):[ \t]*(.*)$")
_FOLD_RE = re.compile(r"^ {6,}(\S.*)$")
_BLOCK_INDICATORS = frozenset({">", ">-", ">+", "|", "|-", "|+"})
_ADVISORY_RE = re.compile(r"(GHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4})", re.IGNORECASE)

_OSV_ENTRY_RE = re.compile(r"^\s*\[\[IgnoredVulns\]\]\s*$")
_OSV_ID_RE = re.compile(r'^\s*id\s*=\s*"([^"]+)"\s*$')
_OSV_UNTIL_RE = re.compile(r"^\s*ignoreUntil\s*=\s*(\d{4}-\d{2}-\d{2})\s*$")


def parse_waivers(text: str) -> list[dict[str, str]]:
    """Return every waiver entry in the registry as a field mapping.

    A deliberately small YAML subset, so a security gate needs no third-party
    parser to decide whether a finding has been accepted.
    """

    waivers: list[dict[str, str]] = []
    field_name = ""
    for line in text.splitlines():
        entry = _ENTRY_RE.match(line)
        field = entry or _FIELD_RE.match(line)
        if field is not None:
            if entry is not None:
                waivers.append({})
            field_name = field.group(1)
            value = field.group(2).strip()
            waivers[-1][field_name] = "" if value in _BLOCK_INDICATORS else value
            continue
        folded = _FOLD_RE.match(line)
        if folded is not None and waivers and field_name:
            existing = waivers[-1].get(field_name, "")
            waivers[-1][field_name] = f"{existing} {folded.group(1).strip()}".strip()
            continue
        if line.strip():
            field_name = ""
    return waivers


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def live_waivers(text: str, repo: str, today: date) -> tuple[dict[str, dict[str, str]], list[str]]:
    """Return usable dependency waivers by advisory id, plus every problem found.

    A waiver that fails validation is not returned. Malformed and expired
    entries therefore accept nothing at all: both gates fail closed.
    """

    problems: list[str] = []
    usable: dict[str, dict[str, str]] = {}
    for waiver in parse_waivers(text):
        if waiver.get("kind") != KIND:
            continue
        waiver_id = waiver.get("id") or "<missing id>"
        missing = [field for field in REQUIRED_FIELDS if not waiver.get(field)]
        if missing:
            problems.append(f"{waiver_id}: missing required field(s): {', '.join(missing)}")
            continue
        if waiver["repo"] != repo:
            problems.append(f"{waiver_id}: repo is {waiver['repo']}, not {repo}")
            continue
        granted = _parse_date(waiver["granted"])
        expires = _parse_date(waiver["expires"])
        if granted is None or expires is None:
            problems.append(f"{waiver_id}: granted and expires must be ISO dates")
            continue
        if expires < granted:
            problems.append(f"{waiver_id}: expiry precedes granted date")
            continue
        if expires < today:
            problems.append(
                f"{waiver_id}: expired on {waiver['expires']}; re-review the advisory or "
                f"let the gate block"
            )
            continue
        if waiver["severity"] not in BLOCKING:
            problems.append(
                f"{waiver_id}: severity {waiver['severity']!r} is not one these gates block on"
            )
            continue
        advisory = waiver["advisory"].upper()
        if advisory in usable:
            problems.append(f"{waiver_id}: duplicate waiver for {advisory}")
            continue
        usable[advisory] = waiver
    return usable, problems


def advisory_id(via: dict[str, Any]) -> str:
    """Return the GHSA id an npm advisory object carries, or its numeric source."""

    match = _ADVISORY_RE.search(str(via.get("url", "")))
    if match is not None:
        return match.group(1).upper()
    return f"npm-source-{via.get('source', 'unknown')}"


def report_advisories(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the distinct advisories an `npm audit --json` report names.

    npm lists one entry per affected package. The packages carrying the
    advisory have object-shaped `via` entries; everything downstream just names
    the package it inherited the problem from, so adjudicating the advisory
    objects covers the whole propagated set.
    """

    seen: dict[tuple[str, str, str], dict[str, Any]] = {}
    vulnerabilities = report.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        return []
    for entry in vulnerabilities.values():
        if not isinstance(entry, dict):
            continue
        for via in entry.get("via", []):
            if not isinstance(via, dict):
                continue
            key = (advisory_id(via), str(via.get("name", "")), str(via.get("severity", "")).lower())
            seen.setdefault(key, via)
    return [
        {"id": key[0], "package": key[1], "severity": key[2], "via": via}
        for key, via in seen.items()
    ]


def blocking_total(report: dict[str, Any]) -> int:
    """Return the HIGH + CRITICAL count npm itself reports."""

    metadata = report.get("metadata")
    counts = metadata.get("vulnerabilities") if isinstance(metadata, dict) else None
    if not isinstance(counts, dict):
        return 0
    total = 0
    for severity in sorted(BLOCKING):
        try:
            total += int(counts.get(severity, 0))
        except (TypeError, ValueError):
            return 0
    return total


def adjudicate(
    report: dict[str, Any], waivers: dict[str, dict[str, str]]
) -> tuple[list[str], list[str]]:
    """Return (failures, accepted) for one npm audit report."""

    failures: list[str] = []
    accepted: list[str] = []
    advisories = report_advisories(report)
    blocking = [item for item in advisories if item["severity"] in BLOCKING]

    if blocking_total(report) > 0 and not blocking:
        failures.append(
            "npm reports HIGH/CRITICAL findings but no advisory objects could be read from "
            "the report; refusing to pass a report this gate does not understand"
        )

    for item in blocking:
        waiver = waivers.get(str(item["id"]))
        if waiver is None:
            title = item["via"].get("title", "no title")
            failures.append(
                f"{item['id']} ({item['severity']}) in {item['package']}: no waiver. {title}"
            )
            continue
        if waiver["package"] != item["package"]:
            failures.append(
                f"{item['id']}: waiver {waiver['id']} covers {waiver['package']}, but the "
                f"advisory is reported against {item['package']}"
            )
            continue
        if waiver["severity"] != item["severity"]:
            failures.append(
                f"{item['id']}: waiver {waiver['id']} accepts severity {waiver['severity']}, "
                f"but npm now reports {item['severity']}"
            )
            continue
        accepted.append(
            f"{item['id']} ({item['severity']}) in {item['package']}: accepted by "
            f"{waiver['id']}, expires {waiver['expires']}"
        )
    return failures, accepted


def parse_osv_config(text: str) -> list[dict[str, str]]:
    """Return the `[[IgnoredVulns]]` entries in an osv-scanner.toml."""

    entries: list[dict[str, str]] = []
    for line in text.splitlines():
        if _OSV_ENTRY_RE.match(line):
            entries.append({})
            continue
        if not entries:
            continue
        identifier = _OSV_ID_RE.match(line)
        if identifier is not None:
            entries[-1]["id"] = identifier.group(1).upper()
            continue
        until = _OSV_UNTIL_RE.match(line)
        if until is not None:
            entries[-1]["ignoreUntil"] = until.group(1)
    return entries


def osv_config_failures(
    config_text: str, waivers: dict[str, dict[str, str]], required: set[str]
) -> list[str]:
    """Return every disagreement between osv-scanner.toml and the waiver registry."""

    failures: list[str] = []
    seen: set[str] = set()
    for entry in parse_osv_config(config_text):
        identifier = entry.get("id", "")
        if not identifier:
            failures.append("osv-scanner.toml has an [[IgnoredVulns]] entry with no id")
            continue
        seen.add(identifier)
        waiver = waivers.get(identifier)
        if waiver is None:
            failures.append(
                f"osv-scanner.toml ignores {identifier} with no live waiver in waivers.yml"
            )
            continue
        until = entry.get("ignoreUntil", "")
        if until != waiver["expires"]:
            failures.append(
                f"osv-scanner.toml ignores {identifier} until {until or '<never>'}, but waiver "
                f"{waiver['id']} expires {waiver['expires']}"
            )
    for identifier in sorted(required - seen):
        failures.append(
            f"waivers.yml claims osv-scanner coverage for {identifier}, but osv-scanner.toml "
            f"does not ignore it"
        )
    return failures


def _load_report(path: Path | None) -> tuple[dict[str, Any] | None, str]:
    raw = path.read_text(encoding="utf-8") if path is not None else sys.stdin.read()
    source = str(path) if path is not None else "stdin"
    if not raw.strip():
        return None, f"no npm audit report on {source}; the audit did not run"
    try:
        report = json.loads(raw)
    except json.JSONDecodeError:
        return None, f"the npm audit report on {source} is not JSON:\n{raw[:2000]}"
    if not isinstance(report, dict) or "vulnerabilities" not in report:
        return None, f"the npm audit report on {source} carries no vulnerability section"
    if report.get("error"):
        return None, f"npm audit reported an error: {report['error']}"
    return report, ""


def _fail(problems: list[str], advice: str) -> int:
    print("dependency advisory gate failed:", file=sys.stderr)
    for problem in problems:
        print(f"- {problem}", file=sys.stderr)
    print(f"\n{advice}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("npm-audit", "osv-config"))
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--waivers", type=Path, default=WAIVERS_PATH)
    parser.add_argument("--osv-config", type=Path, default=OSV_CONFIG_PATH)
    parser.add_argument("--repo", default="swelter")
    parser.add_argument("--today", default=None)
    args = parser.parse_args(argv)

    today = _parse_date(args.today) if args.today else date.today()
    if today is None:
        print(f"--today is not an ISO date: {args.today}", file=sys.stderr)
        return 2
    if not args.waivers.exists():
        print(f"waiver registry not found: {args.waivers}", file=sys.stderr)
        return 1

    waivers, problems = live_waivers(args.waivers.read_text(encoding="utf-8"), args.repo, today)

    if args.command == "osv-config":
        if not args.osv_config.exists():
            return _fail(
                [*problems, f"osv-scanner ignore config not found: {args.osv_config}"],
                "Every OSV id the scanner ignores must have a live waiver.",
            )
        required = {
            advisory
            for advisory, waiver in waivers.items()
            if "osv-scanner" in waiver["scanners"].split()
        }
        problems += osv_config_failures(
            args.osv_config.read_text(encoding="utf-8"), waivers, required
        )
        if problems:
            return _fail(
                problems,
                "osv-scanner.toml and waivers.yml must agree. An ignored id with no waiver is\n"
                "an allowlist, not an exception.",
            )
        print(f"osv-scanner ignore config: {len(required)} entry/entries, each with a live waiver")
        return 0

    report, error = _load_report(args.report)
    if report is None:
        return _fail([*problems, error], "The gate cannot pass an audit it could not read.")

    failures, accepted = adjudicate(report, waivers)
    for line in accepted:
        print(f"npm audit: {line}")
    if problems or failures:
        return _fail(
            problems + failures,
            "A HIGH or CRITICAL advisory blocks merge. Fix it, or record a dated, narrowly\n"
            "scoped waiver in waivers.yml naming the advisory, the package, the severity, an\n"
            "owner, and an expiry.",
        )
    print(f"npm audit: no unwaived HIGH/CRITICAL advisories ({len(accepted)} waived)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
