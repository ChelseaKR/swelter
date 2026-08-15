"""The dependency-advisory waiver is bounded to one advisory, and provably so.

waivers.yml accepts GHSA-jmr9-qjv8-65gv, an unpatched symlink path-traversal
issue in extract-zip that reaches this repository only as a transitive
development dependency of the dashboard accessibility toolchain. An exception
mechanism nobody has tested is worse than no exception at all, so these pin
what it will *not* accept: a different advisory, a second advisory in the same
package, the waived advisory on another package or at a higher severity, an
expired or malformed waiver, and an OSV ignore list that has drifted away from
the registry all still fail.

The npm reports here are recorded `npm audit --json` shapes, so nothing here
needs a network call or an installed node_modules tree.
"""

from __future__ import annotations

import importlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scripts import dependency_advisory_gate as gate
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    gate = importlib.import_module("scripts.dependency_advisory_gate")

ROOT = Path(__file__).resolve().parent.parent
WAIVERS = ROOT / "waivers.yml"
OSV_CONFIG = ROOT / "osv-scanner.toml"

WAIVED_ADVISORY = "GHSA-jmr9-qjv8-65gv"
WAIVED_PACKAGE = "extract-zip"


def _advisory(
    advisory: str, package: str, severity: str = "high", source: int = 1139346
) -> dict[str, Any]:
    return {
        "source": source,
        "name": package,
        "dependency": package,
        "title": f"{package} test advisory",
        "url": f"https://github.com/advisories/{advisory}",
        "severity": severity,
        "range": "*",
    }


def _report(*advisories: dict[str, Any]) -> dict[str, Any]:
    """Build an `npm audit --json` report carrying the given advisories.

    Mirrors npm's real shape: the package carrying the advisory has an
    object-shaped `via`, and a downstream package just names its parent.
    """

    vulnerabilities: dict[str, Any] = {}
    counts = {"info": 0, "low": 0, "moderate": 0, "high": 0, "critical": 0}
    for via in advisories:
        package = str(via["name"])
        vulnerabilities[package] = {
            "name": package,
            "severity": via["severity"],
            "via": [via],
            "effects": [f"depends-on-{package}"],
            "range": "*",
            "nodes": [f"node_modules/{package}"],
        }
        vulnerabilities[f"depends-on-{package}"] = {
            "name": f"depends-on-{package}",
            "severity": via["severity"],
            "via": [package],
            "effects": [],
            "range": "*",
            "nodes": [f"node_modules/depends-on-{package}"],
        }
        counts[str(via["severity"])] += 2
    return {
        "auditReportVersion": 2,
        "vulnerabilities": vulnerabilities,
        "metadata": {"vulnerabilities": {**counts, "total": sum(counts.values())}},
    }


def _npm_gate(tmp_path: Path, report: dict[str, Any], waivers: Path = WAIVERS) -> int:
    path = tmp_path / "audit.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return gate.main(["npm-audit", "--report", str(path), "--waivers", str(waivers)])


def _osv_gate(waivers: Path = WAIVERS, config: Path = OSV_CONFIG) -> int:
    return gate.main(["osv-config", "--waivers", str(waivers), "--osv-config", str(config)])


def test_the_committed_waiver_accepts_the_advisory_it_names(tmp_path: Path) -> None:
    assert _npm_gate(tmp_path, _report(_advisory(WAIVED_ADVISORY, WAIVED_PACKAGE))) == 0


def test_a_different_high_advisory_still_fails(tmp_path: Path) -> None:
    """The point of the whole exercise: the waiver is not an allowlist."""

    assert _npm_gate(tmp_path, _report(_advisory("GHSA-aaaa-bbbb-cccc", "tar-fs"))) == 1


def test_a_different_advisory_alongside_the_waived_one_still_fails(tmp_path: Path) -> None:
    report = _report(
        _advisory(WAIVED_ADVISORY, WAIVED_PACKAGE),
        _advisory("GHSA-aaaa-bbbb-cccc", "tar-fs", source=222222),
    )
    assert _npm_gate(tmp_path, report) == 1


def test_a_second_advisory_in_the_same_package_still_fails(tmp_path: Path) -> None:
    """Scoped to the advisory, not to extract-zip."""

    assert _npm_gate(tmp_path, _report(_advisory("GHSA-dddd-eeee-ffff", WAIVED_PACKAGE))) == 1


def test_the_waived_advisory_on_another_package_still_fails(tmp_path: Path) -> None:
    assert _npm_gate(tmp_path, _report(_advisory(WAIVED_ADVISORY, "some-other-package"))) == 1


def test_the_waived_advisory_escalated_to_critical_still_fails(tmp_path: Path) -> None:
    report = _report(_advisory(WAIVED_ADVISORY, WAIVED_PACKAGE, severity="critical"))
    assert _npm_gate(tmp_path, report) == 1


def test_a_moderate_advisory_does_not_fail_the_high_floor(tmp_path: Path) -> None:
    report = _report(_advisory("GHSA-aaaa-bbbb-cccc", "tar-fs", severity="moderate"))
    assert _npm_gate(tmp_path, report) == 0


def test_an_expired_waiver_accepts_nothing(tmp_path: Path) -> None:
    stale = tmp_path / "waivers.yml"
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    stale.write_text(
        WAIVERS.read_text(encoding="utf-8").replace("expires: 2026-11-15", f"expires: {yesterday}"),
        encoding="utf-8",
    )
    report = _report(_advisory(WAIVED_ADVISORY, WAIVED_PACKAGE))
    assert _npm_gate(tmp_path, report, waivers=stale) == 1


def test_a_waiver_missing_a_required_field_accepts_nothing(tmp_path: Path) -> None:
    broken = tmp_path / "waivers.yml"
    broken.write_text(
        WAIVERS.read_text(encoding="utf-8").replace("    owner: chelseakr\n", ""), encoding="utf-8"
    )
    report = _report(_advisory(WAIVED_ADVISORY, WAIVED_PACKAGE))
    assert _npm_gate(tmp_path, report, waivers=broken) == 1


def test_an_empty_audit_report_fails_closed(tmp_path: Path) -> None:
    """An audit that did not produce a report is not an audit that passed."""

    empty = tmp_path / "audit.json"
    empty.write_text("", encoding="utf-8")
    assert gate.main(["npm-audit", "--report", str(empty), "--waivers", str(WAIVERS)]) == 1


def test_a_report_shape_the_gate_cannot_read_fails_closed(tmp_path: Path) -> None:
    report = _report(_advisory(WAIVED_ADVISORY, WAIVED_PACKAGE))
    report["vulnerabilities"] = {"opaque": {"severity": "high", "via": ["something"]}}
    assert _npm_gate(tmp_path, report) == 1


def test_the_committed_osv_ignore_list_matches_the_registry() -> None:
    assert _osv_gate() == 0


def test_an_osv_ignore_with_no_waiver_fails(tmp_path: Path) -> None:
    """Adding an id to the scanner's ignore list does not silence it."""

    config = tmp_path / "osv-scanner.toml"
    config.write_text(
        OSV_CONFIG.read_text(encoding="utf-8")
        + '\n[[IgnoredVulns]]\nid = "GHSA-aaaa-bbbb-cccc"\nignoreUntil = 2027-01-01\n',
        encoding="utf-8",
    )
    assert _osv_gate(config=config) == 1


def test_an_osv_ignore_outliving_its_waiver_fails(tmp_path: Path) -> None:
    config = tmp_path / "osv-scanner.toml"
    config.write_text(
        OSV_CONFIG.read_text(encoding="utf-8").replace("2026-11-15", "2027-11-15", 1),
        encoding="utf-8",
    )
    assert _osv_gate(config=config) == 1


def test_a_waiver_claiming_osv_coverage_must_appear_in_the_config(tmp_path: Path) -> None:
    config = tmp_path / "osv-scanner.toml"
    config.write_text("# nothing ignored\n", encoding="utf-8")
    assert _osv_gate(config=config) == 1


def test_the_committed_registry_is_well_formed() -> None:
    waivers, problems = gate.live_waivers(
        WAIVERS.read_text(encoding="utf-8"), "swelter", date.today()
    )
    assert problems == []
    assert set(waivers) == {WAIVED_ADVISORY.upper()}
    waiver = waivers[WAIVED_ADVISORY.upper()]
    assert waiver["package"] == WAIVED_PACKAGE
    assert waiver["severity"] == "high"
    assert "osv-scanner" in waiver["scanners"].split()
    # The record has to carry the facts the acceptance rests on, not just an id.
    evidence = waiver["reason"] + waiver["version"] + waiver["dependency_path"]
    for claim in ("2.0.1", "pa11y", "2026-08-15", "devDependency"):
        assert claim in evidence
