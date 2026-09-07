"""Backup and restore: a rehearsable recovery drill, and a receipt that cannot lie about itself.

Covers: archives are byte-reproducible; a store with no rows is refused rather than archived into
a verification that would always pass; every way an archive can be damaged (a dropped member,
altered bytes, a tampered row, a missing database, a traversal or link member) produces a named
failure and leaves the target store unwritten; a check that could not run is counted as
``NOT_APPLICABLE`` and never as a pass; and ``--prune`` refuses to delete anything while any
archive in the directory cannot be verified.

The sabotage in each negative control is asserted to have landed in the archive before the
verdict is read, because a control that silently no-ops reads exactly like a passing gate.
"""

from __future__ import annotations

import io
import json
import os
import sqlite3
import tarfile
from pathlib import Path

import pytest

from swelter import backup
from swelter.cli import main
from swelter.store import open_store, store_paths

from .conftest import DEMO, make_obs

# -- fixtures ------------------------------------------------------------------------------


def _seed(store_dir: Path) -> None:
    """A store with three rows across two days and two nodes — enough for a real chain."""
    with open_store(store_dir) as store:
        store.write(
            [
                make_obs(node_id="node-01", timestamp="2026-06-01T00:00:00Z", value=25.0),
                make_obs(node_id="node-01", timestamp="2026-06-01T01:00:00Z", value=26.0),
                make_obs(node_id="node-02", timestamp="2026-06-02T00:00:00Z", value=27.0),
            ]
        )


@pytest.fixture
def store_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "store"
    _seed(directory)
    (directory / "corrections.yaml").write_text("version: 1\n", encoding="utf-8")
    return directory


def _members(archive: Path) -> list[str]:
    with tarfile.open(archive, "r:") as tar:
        return [member.name for member in tar.getmembers()]


def _member_bytes(archive: Path, name: str) -> bytes:
    with tarfile.open(archive, "r:") as tar:
        handle = tar.extractfile(name)
        assert handle is not None
        return handle.read()


def _rewrite(
    source: Path,
    destination: Path,
    *,
    drop: str | None = None,
    replace: tuple[str, bytes] | None = None,
    rename: tuple[str, str] | None = None,
    as_symlink: str | None = None,
) -> None:
    """Rebuild an archive with one deliberate defect, so a control can plant exactly one fault."""
    with (
        tarfile.open(source, "r:") as reader,
        tarfile.open(destination, "w", format=tarfile.PAX_FORMAT) as writer,
    ):
        for member in reader.getmembers():
            if member.name == drop:
                continue
            handle = reader.extractfile(member)
            assert handle is not None
            payload = handle.read()
            name = member.name
            if replace is not None and name == replace[0]:
                payload = replace[1]
            if rename is not None and name == rename[0]:
                name = rename[1]
            if as_symlink is not None and name == as_symlink:
                link = tarfile.TarInfo(name)
                link.type = tarfile.SYMTYPE
                link.linkname = "/etc/passwd"
                writer.addfile(link)
                continue
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mtime = 0
            info.mode = 0o644
            writer.addfile(info, io.BytesIO(payload))


# -- building an archive -------------------------------------------------------------------


def test_two_backups_of_an_unchanged_store_are_byte_identical(
    store_dir: Path, tmp_path: Path
) -> None:
    first = tmp_path / "one.tar"
    second = tmp_path / "two.tar"
    backup.write_backup(store_dir, first)
    backup.write_backup(store_dir, second)
    assert first.read_bytes() == second.read_bytes()


def test_the_manifest_records_what_a_restore_will_be_checked_against(
    store_dir: Path, tmp_path: Path
) -> None:
    manifest = backup.write_backup(store_dir, tmp_path / "a.tar")
    assert manifest.row_count == 3
    assert manifest.node_count == 2
    assert manifest.observation_window == ("2026-06-01T00:00:00Z", "2026-06-02T00:00:00Z")
    assert manifest.digest_days == 2
    assert manifest.digest_head is not None and len(manifest.digest_head) == 64
    assert sorted(f.name for f in manifest.files) == ["corrections.yaml", "observations.db"]


def test_the_manifest_is_a_member_of_the_archive_not_a_sidecar(
    store_dir: Path, tmp_path: Path
) -> None:
    archive = tmp_path / "a.tar"
    backup.write_backup(store_dir, archive)
    assert _members(archive)[0] == "BACKUP-MANIFEST.json"
    assert all(
        name == "BACKUP-MANIFEST.json" or name.startswith("store/") for name in _members(archive)
    )


def test_an_empty_store_is_refused_rather_than_archived(tmp_path: Path) -> None:
    """The control the whole module exists for.

    ``verify-archive`` exits 0 over a store with no rows, so an archive of one would verify
    clean against itself forever. Refusing at write time is the only place that can be caught.
    """
    empty = tmp_path / "empty"
    with open_store(empty):
        pass
    assert (empty / "observations.db").is_file()

    with pytest.raises(backup.BackupError, match="holds no observations"):
        backup.write_backup(empty, tmp_path / "a.tar")
    assert not (tmp_path / "a.tar").exists()


def test_a_store_with_no_database_at_all_is_refused(tmp_path: Path) -> None:
    directory = tmp_path / "not-a-store"
    directory.mkdir()
    (directory / "corrections.yaml").write_text("version: 1\n", encoding="utf-8")
    with pytest.raises(backup.BackupError, match="no store here"):
        backup.write_backup(directory, tmp_path / "a.tar")


def test_an_open_sqlite_journal_refuses_the_backup(store_dir: Path, tmp_path: Path) -> None:
    (store_dir / "observations.db-journal").write_bytes(b"in flight")
    with pytest.raises(backup.BackupError, match="open SQLite journal"):
        backup.write_backup(store_dir, tmp_path / "a.tar")


def test_a_symlink_in_the_store_refuses_the_backup(store_dir: Path, tmp_path: Path) -> None:
    (store_dir / "elsewhere.yaml").symlink_to(tmp_path / "outside.yaml")
    with pytest.raises(backup.BackupError, match="symlink"):
        backup.write_backup(store_dir, tmp_path / "a.tar")


def test_writing_over_a_directory_is_refused(store_dir: Path, tmp_path: Path) -> None:
    target = tmp_path / "somewhere"
    target.mkdir()
    with pytest.raises(backup.BackupError, match="name the archive file"):
        backup.write_backup(store_dir, target)


# -- the rights envelope -------------------------------------------------------------------


def test_recorded_source_terms_travel_into_the_manifest(store_dir: Path, tmp_path: Path) -> None:
    (store_dir / "source-metadata.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": "OpenAQ",
                "license": "Provider-specific; see the ledger",
                "attribution": "OpenAQ contributors",
                "recorded_at": "2026-06-03T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    manifest = backup.write_backup(store_dir, tmp_path / "a.tar")
    assert manifest.rights == {
        "source": "OpenAQ",
        "license": "Provider-specific; see the ledger",
        "attribution": "OpenAQ contributors",
    }


def test_an_unreadable_rights_record_refuses_the_backup(store_dir: Path, tmp_path: Path) -> None:
    """A rights envelope that is present but broken must not be silently dropped.

    Dropping it would produce a restored store that looks unencumbered, which is a licensing
    claim nobody made.
    """
    (store_dir / "source-metadata.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(backup.BackupError, match="unreadable"):
        backup.write_backup(store_dir, tmp_path / "a.tar")


def test_an_incomplete_rights_record_refuses_the_backup(store_dir: Path, tmp_path: Path) -> None:
    (store_dir / "source-metadata.json").write_text(
        json.dumps({"schema_version": 1, "source": "OpenAQ"}), encoding="utf-8"
    )
    with pytest.raises(backup.BackupError, match="rights envelope is incomplete"):
        backup.write_backup(store_dir, tmp_path / "a.tar")


# -- restoring -----------------------------------------------------------------------------


def test_a_clean_archive_restores_byte_identically_and_verifies(
    store_dir: Path, tmp_path: Path
) -> None:
    archive = tmp_path / "a.tar"
    backup.write_backup(store_dir, archive)
    receipt = backup.restore_archive(archive, tmp_path / "restored")

    assert receipt.verdict == "verified"
    assert receipt.restored is True
    for name in ("observations.db", "corrections.yaml"):
        assert (tmp_path / "restored" / name).read_bytes() == (store_dir / name).read_bytes()
    assert [c.status for c in receipt.checks if c.name == "row_hashes"] == ["PASS"]


def test_the_receipt_is_byte_identical_across_two_runs(store_dir: Path, tmp_path: Path) -> None:
    archive = tmp_path / "a.tar"
    backup.write_backup(store_dir, archive)
    first = backup.restore_archive(archive, None).to_json()
    second = backup.restore_archive(archive, None).to_json()
    assert first == second


def test_verify_only_writes_no_store(store_dir: Path, tmp_path: Path) -> None:
    archive = tmp_path / "a.tar"
    backup.write_backup(store_dir, archive)
    receipt = backup.restore_archive(archive, None)
    assert receipt.verdict == "verified"
    assert receipt.restored is False
    assert receipt.target is None
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.tar", "store"]


def test_a_dropped_member_fails_by_name_and_leaves_the_target_unwritten(
    store_dir: Path, tmp_path: Path
) -> None:
    archive = tmp_path / "a.tar"
    backup.write_backup(store_dir, archive)
    damaged = tmp_path / "damaged.tar"
    _rewrite(archive, damaged, drop="store/corrections.yaml")

    # The sabotage must actually be in the file, or a green verdict below would mean nothing.
    assert "store/corrections.yaml" not in _members(damaged)
    assert "store/observations.db" in _members(damaged)

    target = tmp_path / "restored"
    receipt = backup.restore_archive(damaged, target)
    assert receipt.verdict == "incomplete"
    assert receipt.restored is False
    assert not target.exists()
    failed = {c.name: c.detail for c in receipt.checks if c.status == "FAIL"}
    assert "members" in failed
    assert "corrections.yaml" in failed["members"]


def test_altered_bytes_fail_the_file_digest_check(store_dir: Path, tmp_path: Path) -> None:
    archive = tmp_path / "a.tar"
    backup.write_backup(store_dir, archive)
    original = _member_bytes(archive, "store/corrections.yaml")
    damaged = tmp_path / "damaged.tar"
    _rewrite(archive, damaged, replace=("store/corrections.yaml", b"version: 2\n"))

    assert _member_bytes(damaged, "store/corrections.yaml") != original

    receipt = backup.restore_archive(damaged, tmp_path / "restored")
    assert receipt.verdict == "incomplete"
    assert [c.name for c in receipt.checks if c.status == "FAIL"] == ["file_digests"]
    assert not (tmp_path / "restored").exists()


def test_a_row_tampered_with_before_the_backup_fails_the_row_hash_check(
    store_dir: Path, tmp_path: Path
) -> None:
    """The complementary half of the digest check.

    File digests prove the archive carries what it says it carries. They cannot notice that what
    it carries was already mutated outside the append-only write path, which is what this asks.
    """
    connection = sqlite3.connect(str(store_paths(store_dir)["db"]))
    connection.execute("UPDATE observations SET value = 999.0 WHERE node_id = 'node-01'")
    connection.commit()
    connection.close()

    archive = tmp_path / "a.tar"
    backup.write_backup(store_dir, archive)
    receipt = backup.restore_archive(archive, tmp_path / "restored")

    assert receipt.verdict == "incomplete"
    failed = [c.name for c in receipt.checks if c.status == "FAIL"]
    assert failed == ["row_hashes"]
    assert not (tmp_path / "restored").exists()


def test_an_archive_with_no_database_does_not_manufacture_an_empty_one(
    store_dir: Path, tmp_path: Path
) -> None:
    """``open_store`` creates a database when none exists, and an empty one passes every row
    check and folds to no chain — three green checks over nothing. The database file is
    therefore checked before the store is opened."""
    archive = tmp_path / "a.tar"
    backup.write_backup(store_dir, archive)
    damaged = tmp_path / "damaged.tar"
    _rewrite(archive, damaged, drop="store/observations.db")

    assert "store/observations.db" not in _members(damaged)

    receipt = backup.restore_archive(damaged, tmp_path / "restored")
    failed = [c.name for c in receipt.checks if c.status == "FAIL"]
    assert "row_count" in failed
    assert "row_hashes" in failed
    assert "digest_chain" in failed
    assert receipt.verdict == "incomplete"


def test_a_traversal_member_is_refused_before_anything_is_written(
    store_dir: Path, tmp_path: Path
) -> None:
    archive = tmp_path / "a.tar"
    backup.write_backup(store_dir, archive)
    hostile = tmp_path / "hostile.tar"
    _rewrite(archive, hostile, rename=("store/corrections.yaml", "store/../escaped.yaml"))

    assert "store/../escaped.yaml" in _members(hostile)

    with pytest.raises(backup.BackupError, match="inside the store"):
        backup.restore_archive(hostile, tmp_path / "restored")
    assert not (tmp_path / "escaped.yaml").exists()
    assert not (tmp_path / "restored").exists()


def test_a_member_outside_the_store_prefix_is_refused(store_dir: Path, tmp_path: Path) -> None:
    archive = tmp_path / "a.tar"
    backup.write_backup(store_dir, archive)
    hostile = tmp_path / "hostile.tar"
    _rewrite(archive, hostile, rename=("store/corrections.yaml", "elsewhere/corrections.yaml"))

    assert "elsewhere/corrections.yaml" in _members(hostile)

    with pytest.raises(backup.BackupError, match="outside"):
        backup.restore_archive(hostile, tmp_path / "restored")


def test_a_symlink_member_is_refused(store_dir: Path, tmp_path: Path) -> None:
    archive = tmp_path / "a.tar"
    backup.write_backup(store_dir, archive)
    hostile = tmp_path / "hostile.tar"
    _rewrite(archive, hostile, as_symlink="store/corrections.yaml")

    with tarfile.open(hostile, "r:") as tar:
        assert tar.getmember("store/corrections.yaml").issym()

    with pytest.raises(backup.BackupError, match="not a regular file"):
        backup.restore_archive(hostile, tmp_path / "restored")


def test_an_archive_with_no_manifest_is_refused(store_dir: Path, tmp_path: Path) -> None:
    archive = tmp_path / "a.tar"
    backup.write_backup(store_dir, archive)
    stripped = tmp_path / "stripped.tar"
    _rewrite(archive, stripped, drop="BACKUP-MANIFEST.json")

    assert "BACKUP-MANIFEST.json" not in _members(stripped)

    with pytest.raises(backup.BackupError, match=r"contains no BACKUP\-MANIFEST\.json"):
        backup.read_manifest(stripped)


def test_a_manifest_from_another_schema_version_is_refused(store_dir: Path, tmp_path: Path) -> None:
    archive = tmp_path / "a.tar"
    backup.write_backup(store_dir, archive)
    doc = json.loads(_member_bytes(archive, "BACKUP-MANIFEST.json"))
    doc["schema_version"] = "9.9"
    future = tmp_path / "future.tar"
    _rewrite(archive, future, replace=("BACKUP-MANIFEST.json", json.dumps(doc).encode("utf-8")))

    assert json.loads(_member_bytes(future, "BACKUP-MANIFEST.json"))["schema_version"] == "9.9"

    with pytest.raises(backup.BackupError, match="different swelter"):
        backup.read_manifest(future)


def test_a_manifest_recording_no_files_is_refused(store_dir: Path, tmp_path: Path) -> None:
    archive = tmp_path / "a.tar"
    backup.write_backup(store_dir, archive)
    doc = json.loads(_member_bytes(archive, "BACKUP-MANIFEST.json"))
    doc["files"] = []
    empty = tmp_path / "empty-manifest.tar"
    _rewrite(archive, empty, replace=("BACKUP-MANIFEST.json", json.dumps(doc).encode("utf-8")))

    with pytest.raises(backup.BackupError, match="'files' is missing or empty"):
        backup.read_manifest(empty)


def test_a_non_empty_target_is_refused_unless_forced(store_dir: Path, tmp_path: Path) -> None:
    archive = tmp_path / "a.tar"
    backup.write_backup(store_dir, archive)
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "someone-elses.db").write_bytes(b"do not clobber me")

    with pytest.raises(backup.BackupError, match="not empty"):
        backup.restore_archive(archive, occupied)
    assert (occupied / "someone-elses.db").read_bytes() == b"do not clobber me"

    receipt = backup.restore_archive(archive, occupied, force=True)
    assert receipt.verdict == "verified"
    assert not (occupied / "someone-elses.db").exists()
    assert (occupied / "observations.db").is_file()


# -- the three-outcome receipt -------------------------------------------------------------


def test_not_applicable_is_reported_separately_and_never_counted_as_a_pass(
    tmp_path: Path,
) -> None:
    """A store that never had corrections must not look like one whose corrections survived."""
    bare = tmp_path / "bare"
    _seed(bare)
    archive = tmp_path / "a.tar"
    backup.write_backup(bare, archive)
    receipt = backup.restore_archive(archive, tmp_path / "restored")

    statuses = {c.name: c.status for c in receipt.checks}
    assert statuses["corrections"] == "NOT_APPLICABLE"
    assert statuses["rights"] == "NOT_APPLICABLE"
    assert statuses["license_ledger"] == "NOT_APPLICABLE"
    assert len(receipt.not_applicable) == 4
    assert all(c.status != "NOT_APPLICABLE" for c in receipt.passed)
    assert receipt.to_dict()["summary"] == {
        "passed": 6,
        "failed": 0,
        "not_applicable": 4,
        "required": [
            "manifest",
            "members",
            "file_digests",
            "row_count",
            "row_hashes",
            "digest_chain",
        ],
    }


def test_a_verdict_needs_every_required_check_to_have_run_not_merely_no_failures() -> None:
    """A check that never ran cannot fail — so a verdict counting failures would call an
    empty verification a success. This asserts the verdict is built the other way round."""
    everything_passed = backup.Receipt(
        archive="a.tar",
        target=None,
        checks=tuple(
            backup.Check(name, "PASS", "")
            for name in (
                "manifest",
                "members",
                "file_digests",
                "row_count",
                "row_hashes",
                "digest_chain",
            )
        ),
        manifest=None,
        restored=False,
    )
    assert everything_passed.verdict == "verified"

    one_never_ran = backup.Receipt(
        archive="a.tar",
        target=None,
        checks=tuple(c for c in everything_passed.checks if c.name != "digest_chain"),
        manifest=None,
        restored=False,
    )
    assert not one_never_ran.failed
    assert one_never_ran.verdict == "incomplete"

    reported_not_applicable = backup.Receipt(
        archive="a.tar",
        target=None,
        checks=tuple(
            backup.Check(c.name, "NOT_APPLICABLE" if c.name == "row_hashes" else "PASS", "")
            for c in everything_passed.checks
        ),
        manifest=None,
        restored=False,
    )
    assert not reported_not_applicable.failed
    assert reported_not_applicable.verdict == "incomplete"


# -- retention -----------------------------------------------------------------------------


def _archives(store_dir: Path, directory: Path, count: int) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    made: list[Path] = []
    for index in range(count):
        path = directory / f"backup-{index:02d}.tar"
        backup.write_backup(store_dir, path)
        # Distinct mtimes so "newest" is a fact about the shelf, not about filesystem timing.
        os.utime(path, (1_700_000_000 + index, 1_700_000_000 + index))
        made.append(path)
    return made


def test_prune_keeps_the_newest_and_deletes_the_rest(store_dir: Path, tmp_path: Path) -> None:
    directory = tmp_path / "backups"
    _archives(store_dir, directory, 5)
    plan = backup.plan_prune(directory, 2)
    assert plan.kept == ("backup-04.tar", "backup-03.tar")
    assert plan.deleted == ("backup-02.tar", "backup-01.tar", "backup-00.tar")
    backup.apply_prune(directory, plan)
    assert sorted(p.name for p in directory.iterdir()) == ["backup-03.tar", "backup-04.tar"]


def test_prune_never_empties_the_shelf(store_dir: Path, tmp_path: Path) -> None:
    directory = tmp_path / "backups"
    _archives(store_dir, directory, 3)
    plan = backup.plan_prune(directory, 0)
    assert plan.keep == 1
    assert plan.kept == ("backup-02.tar",)
    backup.apply_prune(directory, plan)
    assert [p.name for p in directory.iterdir()] == ["backup-02.tar"]


def test_prune_refuses_the_whole_directory_when_one_archive_cannot_be_verified(
    store_dir: Path, tmp_path: Path
) -> None:
    directory = tmp_path / "backups"
    made = _archives(store_dir, directory, 3)
    damaged = made[0]
    _rewrite(made[1], damaged, replace=("store/corrections.yaml", b"tampered\n"))

    assert _member_bytes(damaged, "store/corrections.yaml") == b"tampered\n"

    plan = backup.plan_prune(directory, 1)
    assert plan.refused is True
    assert plan.deleted == ()
    assert [name for name, _ in plan.unverifiable] == ["backup-00.tar"]
    with pytest.raises(backup.BackupError, match="refusing to prune"):
        backup.apply_prune(directory, plan)
    assert len(list(directory.glob("*.tar"))) == 3


def test_prune_refuses_a_file_that_is_not_an_archive_at_all(
    store_dir: Path, tmp_path: Path
) -> None:
    directory = tmp_path / "backups"
    _archives(store_dir, directory, 2)
    (directory / "not-really.tar").write_bytes(b"this is not a tar file")
    plan = backup.plan_prune(directory, 1)
    assert plan.refused is True
    assert [name for name, _ in plan.unverifiable] == ["not-really.tar"]


def test_prune_needs_a_directory(tmp_path: Path) -> None:
    with pytest.raises(backup.BackupError, match="not a directory"):
        backup.plan_prune(tmp_path / "nowhere", 2)


# -- the CLI -------------------------------------------------------------------------------


def test_cli_round_trip_exits_zero_and_writes_a_receipt(store_dir: Path, tmp_path: Path) -> None:
    archive = tmp_path / "a.tar"
    receipt_path = tmp_path / "receipt.json"
    assert main(["backup", "--store", str(store_dir), "--out", str(archive)]) == 0
    assert (
        main(
            [
                "restore",
                str(archive),
                "--store",
                str(tmp_path / "restored"),
                "--verify",
                "--receipt",
                str(receipt_path),
            ]
        )
        == 0
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["verdict"] == "verified"
    assert receipt["restored"] is True
    assert receipt["summary"]["not_applicable"] == 3


def test_cli_restore_exits_nonzero_on_a_damaged_archive(store_dir: Path, tmp_path: Path) -> None:
    archive = tmp_path / "a.tar"
    backup.write_backup(store_dir, archive)
    damaged = tmp_path / "damaged.tar"
    _rewrite(archive, damaged, drop="store/observations.db")

    assert "store/observations.db" not in _members(damaged)
    assert main(["restore", str(damaged), "--store", str(tmp_path / "restored")]) == 1
    assert not (tmp_path / "restored").exists()


def test_cli_backup_of_an_empty_store_exits_nonzero(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    with open_store(empty):
        pass
    assert main(["backup", "--store", str(empty), "--out", str(tmp_path / "a.tar")]) == 1
    assert not (tmp_path / "a.tar").exists()


def test_cli_backup_needs_a_destination(store_dir: Path) -> None:
    assert main(["backup", "--store", str(store_dir)]) == 1


def test_cli_restore_needs_a_target_or_verify_only(store_dir: Path, tmp_path: Path) -> None:
    archive = tmp_path / "a.tar"
    backup.write_backup(store_dir, archive)
    assert main(["restore", str(archive)]) == 1
    assert main(["restore", str(archive), "--store", str(tmp_path / "x"), "--verify-only"]) == 1
    assert main(["restore", str(archive), "--verify-only"]) == 0


def test_cli_prune_dry_run_deletes_nothing(store_dir: Path, tmp_path: Path) -> None:
    directory = tmp_path / "backups"
    _archives(store_dir, directory, 3)
    assert main(["backup", "--prune", str(directory), "--keep", "1", "--dry-run"]) == 0
    assert len(list(directory.glob("*.tar"))) == 3
    assert main(["backup", "--prune", str(directory), "--keep", "1"]) == 0
    assert len(list(directory.glob("*.tar"))) == 1


def test_cli_prune_exits_nonzero_when_it_refuses(store_dir: Path, tmp_path: Path) -> None:
    directory = tmp_path / "backups"
    _archives(store_dir, directory, 2)
    (directory / "broken.tar").write_bytes(b"not a tar")
    assert main(["backup", "--prune", str(directory), "--keep", "1"]) == 1
    assert len(list(directory.glob("*.tar"))) == 3


def test_cli_json_output_carries_the_manifest_and_the_plan(
    store_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    archive = tmp_path / "a.tar"
    assert main(["backup", "--store", str(store_dir), "--out", str(archive), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["row_count"] == 3
    assert payload["archive"] == str(archive)

    assert main(["restore", str(archive), "--verify-only", "--json"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["verdict"] == "verified"
    assert receipt["target"] is None

    directory = tmp_path / "backups"
    _archives(store_dir, directory, 2)
    assert main(["backup", "--prune", str(directory), "--keep", "1", "--json"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["applied"] is True
    assert plan["kept"] == ["backup-01.tar"]


# -- against the committed demo ------------------------------------------------------------


@pytest.mark.skipif(not DEMO.is_dir(), reason="demo fixture is not packaged with the wheel")
def test_the_demo_store_round_trips_and_still_passes_verify_archive(tmp_path: Path) -> None:
    """The drill an operator is asked to rehearse, run end to end on the committed fixture."""
    store = tmp_path / "store"
    assert main(["ingest", str(DEMO / "observations.jsonl"), "--store", str(store)]) == 0
    assert main(["verify-archive", "--store", str(store), "--write"]) == 0

    archive = tmp_path / "demo.tar"
    assert main(["backup", "--store", str(store), "--out", str(archive)]) == 0
    restored = tmp_path / "restored"
    assert main(["restore", str(archive), "--store", str(restored), "--verify"]) == 0

    assert (restored / "observations.db").read_bytes() == (store / "observations.db").read_bytes()
    assert (restored / "digests.jsonl").read_text(encoding="utf-8") == (
        store / "digests.jsonl"
    ).read_text(encoding="utf-8")
    assert main(["verify-archive", "--store", str(restored)]) == 0


# -- manifest validation -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        ({"row_count": "three"}, "'row_count' is missing or not an integer"),
        ({"row_count": True}, "'row_count' is missing or not an integer"),
        ({"swelter_version": None}, "'swelter_version' is missing or not a string"),
        ({"files": [{"sha256": "x" * 64, "bytes": 1}]}, "has no 'name'"),
        ({"files": [{"name": "a", "sha256": "short", "bytes": 1}]}, "no usable 'sha256'"),
        ({"files": [{"name": "a", "sha256": "x" * 64, "bytes": -1}]}, "no usable 'bytes'"),
        ({"files": ["a string"]}, "must be an object"),
    ],
)
def test_a_manifest_that_does_not_say_what_it_must_is_refused(
    store_dir: Path, tmp_path: Path, mutate: dict[str, object], expected: str
) -> None:
    archive = tmp_path / "a.tar"
    backup.write_backup(store_dir, archive)
    doc = json.loads(_member_bytes(archive, "BACKUP-MANIFEST.json"))
    doc.update(mutate)
    broken = tmp_path / "broken.tar"
    _rewrite(archive, broken, replace=("BACKUP-MANIFEST.json", json.dumps(doc).encode("utf-8")))

    assert json.loads(_member_bytes(broken, "BACKUP-MANIFEST.json")) == doc

    with pytest.raises(backup.BackupError, match=expected):
        backup.read_manifest(broken)


def test_a_manifest_that_is_not_json_is_refused(store_dir: Path, tmp_path: Path) -> None:
    archive = tmp_path / "a.tar"
    backup.write_backup(store_dir, archive)
    for payload, expected in (
        (b"{not json", "not readable JSON"),
        (b"[1, 2]", "not a JSON object"),
    ):
        broken = tmp_path / "broken.tar"
        _rewrite(archive, broken, replace=("BACKUP-MANIFEST.json", payload))
        assert _member_bytes(broken, "BACKUP-MANIFEST.json") == payload
        with pytest.raises(backup.BackupError, match=expected):
            backup.read_manifest(broken)
        broken.unlink()


def test_reading_a_manifest_from_a_missing_or_unreadable_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(backup.BackupError, match="does not exist"):
        backup.read_manifest(tmp_path / "nothing.tar")
    (tmp_path / "junk.tar").write_bytes(b"not a tar file at all")
    with pytest.raises(backup.BackupError, match="not a readable tar archive"):
        backup.read_manifest(tmp_path / "junk.tar")


# -- the chain-head comparison -------------------------------------------------------------


def test_a_manifest_with_no_recorded_chain_head_cannot_match_an_absent_one(
    store_dir: Path, tmp_path: Path
) -> None:
    """Two absences must not agree with each other.

    If ``digest_head: null`` compared equal to a restored store that folds to no chain, an
    archive of an empty store would verify against an empty restore of it, and the check would
    report success over no data at all.
    """
    archive = tmp_path / "a.tar"
    backup.write_backup(store_dir, archive)
    doc = json.loads(_member_bytes(archive, "BACKUP-MANIFEST.json"))
    doc["digest_head"] = None
    headless = tmp_path / "headless.tar"
    _rewrite(archive, headless, replace=("BACKUP-MANIFEST.json", json.dumps(doc).encode("utf-8")))

    assert json.loads(_member_bytes(headless, "BACKUP-MANIFEST.json"))["digest_head"] is None

    receipt = backup.restore_archive(headless, tmp_path / "restored")
    chain = next(c for c in receipt.checks if c.name == "digest_chain")
    assert chain.status == "FAIL"
    assert "records no chain head" in chain.detail
    assert receipt.verdict == "incomplete"


def test_a_chain_head_that_moved_is_named_on_both_sides(store_dir: Path, tmp_path: Path) -> None:
    archive = tmp_path / "a.tar"
    backup.write_backup(store_dir, archive)
    doc = json.loads(_member_bytes(archive, "BACKUP-MANIFEST.json"))
    doc["digest_head"] = "0" * 64
    moved = tmp_path / "moved.tar"
    _rewrite(archive, moved, replace=("BACKUP-MANIFEST.json", json.dumps(doc).encode("utf-8")))

    assert json.loads(_member_bytes(moved, "BACKUP-MANIFEST.json"))["digest_head"] == "0" * 64

    receipt = backup.restore_archive(moved, tmp_path / "restored")
    chain = next(c for c in receipt.checks if c.name == "digest_chain")
    assert chain.status == "FAIL"
    assert "does not match the recorded 000000000000" in chain.detail


def test_a_conditional_file_that_restores_empty_is_a_failure_not_a_pass(
    store_dir: Path, tmp_path: Path
) -> None:
    archive = tmp_path / "a.tar"
    backup.write_backup(store_dir, archive)
    hollow = tmp_path / "hollow.tar"
    _rewrite(archive, hollow, replace=("store/corrections.yaml", b""))

    assert _member_bytes(hollow, "store/corrections.yaml") == b""

    receipt = backup.restore_archive(hollow, tmp_path / "restored")
    corrections = next(c for c in receipt.checks if c.name == "corrections")
    assert corrections.status == "FAIL"
    assert "restored empty" in corrections.detail


# -- targets and rendering -----------------------------------------------------------------


def test_restoring_onto_a_file_is_refused(store_dir: Path, tmp_path: Path) -> None:
    archive = tmp_path / "a.tar"
    backup.write_backup(store_dir, archive)
    occupied = tmp_path / "already-a-file"
    occupied.write_text("mine", encoding="utf-8")
    with pytest.raises(backup.BackupError, match="not a directory"):
        backup.restore_archive(archive, occupied)
    assert occupied.read_text(encoding="utf-8") == "mine"


def test_the_rendered_receipt_tallies_not_applicable_on_its_own(
    store_dir: Path, tmp_path: Path
) -> None:
    archive = tmp_path / "a.tar"
    backup.write_backup(store_dir, archive)
    lines = list(backup.render_receipt(backup.restore_archive(archive, None)))
    assert lines[0].endswith("VERIFIED — " + str(archive))
    assert any("not applicable (not counted as passing)" in line for line in lines)
    assert any("no store written (verification run only)" in line for line in lines)


def test_the_rendered_prune_says_what_it_refused_and_why(store_dir: Path, tmp_path: Path) -> None:
    directory = tmp_path / "backups"
    _archives(store_dir, directory, 2)
    (directory / "broken.tar").write_bytes(b"not a tar")
    plan = backup.plan_prune(directory, 1)
    lines = list(backup.render_prune(plan, directory))
    assert "REFUSED" in lines[0]
    assert any(line.startswith("  UNVERIFIABLE  broken.tar") for line in lines)


def test_the_rendered_manifest_names_the_rights_it_carries(store_dir: Path, tmp_path: Path) -> None:
    (store_dir / "source-metadata.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": "OpenAQ",
                "license": "Provider-specific",
                "attribution": "OpenAQ contributors",
            }
        ),
        encoding="utf-8",
    )
    archive = tmp_path / "a.tar"
    manifest = backup.write_backup(store_dir, archive)
    lines = list(backup.render_manifest(manifest, archive))
    assert any("OpenAQ — Provider-specific" in line for line in lines)
    assert any("window      2026-06-01T00:00:00Z" in line for line in lines)
