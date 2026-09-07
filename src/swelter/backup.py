"""``swelter backup`` / ``swelter restore`` — rehearse recovery, and keep the receipt.

The store is "one copyable directory" and the operations runbook says to copy it. Nothing
checked that the copy was complete, that it restored, or that the archive's rights, licence and
integrity evidence survived the trip. A collective that has never restored its own store does not
know whether it has a backup; it knows it has a file.

So this module is deliberately not a `tar` wrapper. Two rules shape everything in it.

**A check that could not run is not a check that passed.** A restore verification reports three
outcomes, not two: ``PASS``, ``FAIL``, and ``NOT_APPLICABLE``. The last one is counted and printed
on its own line and never folded into the pass tally, because "there were no corrections to
compare" and "the corrections compared clean" are different sentences and only one of them is
evidence. The verdict is ``verified`` only when every *required* check ran and passed — so a
verification that silently skipped a step reads as ``incomplete``, not as success.

**An empty archive is not a small archive.** ``verify-archive`` returns 0 over a store with no
rows: nothing mismatched, so nothing failed. That is the correct answer to the question it asks
and the wrong answer to "did my backup work". A backup of a store with no observations is refused
here, and a chain head is recorded as ``null`` rather than as the empty string a zero-row fold
produces, so no later comparison can succeed by matching one absence against another.

Everything else follows from being fail-closed: the target store is written only after every
check has passed, from a staging directory; archives are extracted member by member with no call
to :meth:`tarfile.TarFile.extractall`, so a traversal or link member is a refusal rather than a
write outside the target; and ``--prune`` refuses to delete anything at all while any archive in
the directory cannot be verified, because deleting on the strength of a listing you could not
read is a decision made out of absence.

Archives are byte-reproducible: members are sorted, ownership and modification times are
normalised, and nothing records a wall clock. Two backups of an unchanged store are the same
bytes, so an operator can tell "the store changed" from "the backup ran again".
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import tarfile
import tempfile
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from .dictionary import DATA_SCHEMA_VERSION
from .integrity import daily_digests, verify_rows
from .snapshot import (
    SOURCE_LICENSE_LEDGER_FILENAME,
    SOURCE_METADATA_FILENAME,
    _swelter_version,
)
from .store import open_store, store_paths

__all__ = [
    "BACKUP_SCHEMA_VERSION",
    "DEFAULT_KEEP",
    "MANIFEST_MEMBER",
    "RECEIPT_SCHEMA_VERSION",
    "REQUIRED_CHECKS",
    "STORE_MEMBER_PREFIX",
    "BackupError",
    "BackupFile",
    "BackupManifest",
    "Check",
    "PrunePlan",
    "Receipt",
    "build_manifest",
    "plan_prune",
    "read_manifest",
    "restore_archive",
    "write_backup",
]

BACKUP_SCHEMA_VERSION = "1.0"
RECEIPT_SCHEMA_VERSION = "1.0"

#: The manifest is a member of the archive, not a sidecar file: a manifest that can be separated
#: from the bytes it describes is a manifest that can be lost, and a lost manifest turns a failed
#: restore into an unexplained one.
MANIFEST_MEMBER = "BACKUP-MANIFEST.json"

#: Every store file lives under this prefix, so the archive can grow a sibling section later
#: without a member name ever being ambiguous about which directory it restores into.
STORE_MEMBER_PREFIX = "store/"

#: How many archives ``--prune`` keeps when the operator does not say. Four is a quarter of
#: quarterly drills; it is a default, not a policy, and the runbook says so.
DEFAULT_KEEP = 4

CHECK_OK = "PASS"
CHECK_FAIL = "FAIL"
CHECK_NA = "NOT_APPLICABLE"

#: Checks that must have run *and* passed for a restore to be called ``verified``. Listing them
#: here rather than counting failures is the difference between "nothing went wrong" and "every
#: question was asked": a check that never ran cannot fail, and must not be able to pass either.
REQUIRED_CHECKS: tuple[str, ...] = (
    "manifest",
    "members",
    "file_digests",
    "row_count",
    "row_hashes",
    "digest_chain",
)

#: SQLite writes these beside the database while a transaction is open. Their presence means the
#: store is mid-write and a byte copy would capture a torn state, so a backup refuses rather than
#: archiving something that restores into a database nobody has verified.
_HOT_SIDECAR_SUFFIXES: tuple[str, ...] = ("-journal", "-wal", "-shm")

#: The store's own filenames, taken from :func:`~swelter.store.store_paths` so this module can
#: never drift from the layout it is archiving.
_REGISTRY_NAME = store_paths(".")["registry"].name
_DIGESTS_NAME = store_paths(".")["digests"].name

_TAR_MTIME = 0
_TAR_MODE = 0o644
_READ_CHUNK = 1 << 20


class BackupError(Exception):
    """A refusal: the archive, the store, or the target is not in a state worth writing."""


@dataclass(frozen=True)
class BackupFile:
    """One file inside the archive, as recorded in ``BACKUP-MANIFEST.json``."""

    name: str
    sha256: str
    bytes: int

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "sha256": self.sha256, "bytes": self.bytes}

    @staticmethod
    def from_dict(doc: Any) -> BackupFile:
        if not isinstance(doc, dict):
            raise BackupError("manifest: each entry in 'files' must be an object")
        name, digest, size = doc.get("name"), doc.get("sha256"), doc.get("bytes")
        if not isinstance(name, str) or not name:
            raise BackupError("manifest: a file entry has no 'name'")
        if not isinstance(digest, str) or len(digest) != 64:
            raise BackupError(f"manifest: {name} has no usable 'sha256'")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise BackupError(f"manifest: {name} has no usable 'bytes'")
        return BackupFile(name=name, sha256=digest, bytes=size)


@dataclass(frozen=True)
class BackupManifest:
    """What the archive claims about itself, and what a restore is checked against.

    ``digest_head`` is the chained daily digest of the *rows*, recomputed from the data at backup
    time rather than read from a published ``digests.jsonl``: reading the published head would
    only prove that a file was copied, which the per-file digests already prove. It is ``None``
    for a store with no rows and never the empty string that folding zero days produces.
    """

    schema_version: str
    swelter_version: str
    data_schema_version: int
    row_count: int
    node_count: int
    observation_window: tuple[str, str] | None
    digest_head: str | None
    digest_days: int
    rights: dict[str, str] | None
    files: tuple[BackupFile, ...]

    def to_dict(self) -> dict[str, object]:
        window: dict[str, str] | None = None
        if self.observation_window is not None:
            window = {"start": self.observation_window[0], "end": self.observation_window[1]}
        return {
            "schema_version": self.schema_version,
            "swelter_version": self.swelter_version,
            "data_schema_version": self.data_schema_version,
            "row_count": self.row_count,
            "node_count": self.node_count,
            "observation_window": window,
            "digest_head": self.digest_head,
            "digest_days": self.digest_days,
            "rights": dict(self.rights) if self.rights is not None else None,
            "files": [f.to_dict() for f in self.files],
        }

    def to_json(self) -> bytes:
        """Canonical manifest bytes: sorted keys, two-space indent, one trailing newline."""
        return (json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n").encode("utf-8")

    def store_file(self, name: str) -> BackupFile | None:
        return next((f for f in self.files if f.name == name), None)

    @staticmethod
    def from_bytes(raw: bytes) -> BackupManifest:
        try:
            doc = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BackupError(f"{MANIFEST_MEMBER} is not readable JSON: {exc}") from exc
        if not isinstance(doc, dict):
            raise BackupError(f"{MANIFEST_MEMBER} is not a JSON object")
        version = doc.get("schema_version")
        if version != BACKUP_SCHEMA_VERSION:
            raise BackupError(
                f"{MANIFEST_MEMBER}: schema_version {version!r} is not "
                f"{BACKUP_SCHEMA_VERSION!r} — this archive was written by a different swelter"
            )
        window_doc = doc.get("observation_window")
        window: tuple[str, str] | None = None
        if isinstance(window_doc, dict):
            start, end = window_doc.get("start"), window_doc.get("end")
            if isinstance(start, str) and isinstance(end, str):
                window = (start, end)
        files = doc.get("files")
        if not isinstance(files, list) or not files:
            raise BackupError(f"{MANIFEST_MEMBER}: 'files' is missing or empty")
        rights = doc.get("rights")
        return BackupManifest(
            schema_version=BACKUP_SCHEMA_VERSION,
            swelter_version=_require_str(doc, "swelter_version"),
            data_schema_version=_require_int(doc, "data_schema_version"),
            row_count=_require_int(doc, "row_count"),
            node_count=_require_int(doc, "node_count"),
            observation_window=window,
            digest_head=head if isinstance(head := doc.get("digest_head"), str) else None,
            digest_days=_require_int(doc, "digest_days"),
            rights=(
                {str(k): str(v) for k, v in rights.items()} if isinstance(rights, dict) else None
            ),
            files=tuple(BackupFile.from_dict(entry) for entry in files),
        )


def _require_str(doc: dict[str, Any], key: str) -> str:
    value = doc.get(key)
    if not isinstance(value, str) or not value:
        raise BackupError(f"{MANIFEST_MEMBER}: {key!r} is missing or not a string")
    return value


def _require_int(doc: dict[str, Any], key: str) -> int:
    value = doc.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise BackupError(f"{MANIFEST_MEMBER}: {key!r} is missing or not an integer")
    return value


@dataclass(frozen=True)
class Check:
    """One verification question, its answer, and why that is the answer."""

    name: str
    status: str
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


@dataclass(frozen=True)
class Receipt:
    """The artifact an operator keeps after a drill: what was checked, and what the answer was."""

    archive: str
    target: str | None
    checks: tuple[Check, ...]
    manifest: BackupManifest | None
    restored: bool

    @property
    def failed(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if c.status == CHECK_FAIL)

    @property
    def not_applicable(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if c.status == CHECK_NA)

    @property
    def passed(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if c.status == CHECK_OK)

    @property
    def verdict(self) -> str:
        """``verified`` only when every required check ran and passed.

        Deliberately not ``"no failures"``: a verification that never asked a question has not
        answered it, and a missing check is exactly what a silently broken restore looks like.
        """
        by_name = {c.name: c.status for c in self.checks}
        if any(by_name.get(name) != CHECK_OK for name in REQUIRED_CHECKS):
            return "incomplete"
        return "incomplete" if self.failed else "verified"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "archive": self.archive,
            "target": self.target,
            "verdict": self.verdict,
            "restored": self.restored,
            "summary": {
                "passed": len(self.passed),
                "failed": len(self.failed),
                "not_applicable": len(self.not_applicable),
                "required": list(REQUIRED_CHECKS),
            },
            "checks": [c.to_dict() for c in self.checks],
            "manifest": self.manifest.to_dict() if self.manifest is not None else None,
        }

    def to_json(self) -> bytes:
        return (json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n").encode("utf-8")


@dataclass(frozen=True)
class PrunePlan:
    """Which archives ``--prune`` would keep and which it would delete, and why it refuses."""

    keep: int
    kept: tuple[str, ...]
    deleted: tuple[str, ...]
    unverifiable: tuple[tuple[str, str], ...]

    @property
    def refused(self) -> bool:
        return bool(self.unverifiable)

    def to_dict(self) -> dict[str, object]:
        return {
            "keep": self.keep,
            "refused": self.refused,
            "kept": list(self.kept),
            "deleted": list(self.deleted),
            "unverifiable": [{"archive": name, "reason": why} for name, why in self.unverifiable],
        }


# -- building an archive -------------------------------------------------------------------


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_READ_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _store_files(store_dir: Path) -> list[Path]:
    """Every regular file under the store directory, in one deterministic order.

    The whole directory is archived rather than the handful of names ``store_paths`` knows,
    because "one copyable directory" is the promise and a backup that copies only the files this
    version happens to recognise would silently drop whatever a later one adds.
    """
    files = sorted(p for p in store_dir.rglob("*") if p.is_file() and not p.is_symlink())
    strays = sorted(p.name for p in store_dir.rglob("*") if p.is_symlink())
    if strays:
        raise BackupError(
            f"{store_dir} contains symlink(s) ({', '.join(strays)}); a backup archives regular "
            "files only, so their targets would be silently omitted — resolve or remove them"
        )
    return files


def _refuse_hot_store(store_dir: Path, files: Sequence[Path]) -> None:
    hot = sorted(p.name for p in files if p.name.endswith(_HOT_SIDECAR_SUFFIXES))
    if hot:
        raise BackupError(
            f"{store_dir} has an open SQLite journal ({', '.join(hot)}); a write is in flight and "
            "a byte copy would capture a torn database — close the store and run this again"
        )


def _rights_block(store_dir: Path) -> dict[str, str] | None:
    """Read the store's recorded source terms, if it has any, and refuse a corrupt one.

    A store fetched from a third-party source records who it came from and under what terms. If
    that record exists but cannot be read, the archive must not be written: a backup that quietly
    drops the rights envelope produces a restored store that looks unencumbered.
    """
    path = store_dir / SOURCE_METADATA_FILENAME
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, OSError) as exc:
        raise BackupError(
            f"{path} is present but unreadable ({exc}); refusing to archive it"
        ) from exc
    if not isinstance(doc, dict):
        raise BackupError(f"{path} is present but is not a JSON object; refusing to archive it")
    block = {
        key: str(doc[key])
        for key in ("source", "license", "attribution")
        if isinstance(doc.get(key), str)
    }
    if len(block) != 3:
        raise BackupError(
            f"{path} does not record source, license and attribution; refusing to archive a "
            "store whose rights envelope is incomplete"
        )
    return block


def _observation_facts(store_dir: Path) -> tuple[int, int, tuple[str, str] | None, str | None, int]:
    """Row count, node count, observation window, chain head, and day count for the store."""
    db = store_paths(store_dir)["db"]
    if not db.is_file():
        raise BackupError(f"{db} does not exist; there is no store here to back up")
    with open_store(store_dir) as store:
        nodes: set[str] = set()
        first: str | None = None
        last: str | None = None
        rows = 0
        for observation, _ in store.iter_rows():
            rows += 1
            nodes.add(observation.node_id)
            stamp = observation.timestamp
            if first is None or stamp < first:
                first = stamp
            if last is None or stamp > last:
                last = stamp
        digests = daily_digests(store)
    if rows == 0:
        raise BackupError(
            f"{db} holds no observations; a backup of an empty store would verify clean against "
            "itself forever and prove nothing — ingest first, then back up"
        )
    window = (first, last) if first is not None and last is not None else None
    return rows, len(nodes), window, digests[-1].chain if digests else None, len(digests)


def build_manifest(store_dir: str | Path) -> BackupManifest:
    """Describe a store precisely enough that a restore of it can be checked, not assumed."""
    base = Path(store_dir)
    if not base.is_dir():
        raise BackupError(f"{base} is not a directory")
    files = _store_files(base)
    _refuse_hot_store(base, files)
    rows, nodes, window, head, days = _observation_facts(base)
    return BackupManifest(
        schema_version=BACKUP_SCHEMA_VERSION,
        swelter_version=_swelter_version(),
        data_schema_version=DATA_SCHEMA_VERSION,
        row_count=rows,
        node_count=nodes,
        observation_window=window,
        digest_head=head,
        digest_days=days,
        rights=_rights_block(base),
        files=tuple(
            BackupFile(
                name=path.relative_to(base).as_posix(),
                sha256=_sha256_path(path),
                bytes=path.stat().st_size,
            )
            for path in files
        ),
    )


def _tarinfo(name: str, size: int) -> tarfile.TarInfo:
    """A member header with every host-specific field normalised away.

    Ownership, permissions and modification time are properties of the machine that ran the
    backup, not of the data, and leaving them in would make two archives of identical bytes
    differ — which is precisely the signal an operator uses to tell "the store changed" from
    "the backup ran again".
    """
    info = tarfile.TarInfo(name)
    info.size = size
    info.mtime = _TAR_MTIME
    info.mode = _TAR_MODE
    info.type = tarfile.REGTYPE
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    return info


def write_backup(store_dir: str | Path, out_path: str | Path) -> BackupManifest:
    """Write a byte-reproducible archive of ``store_dir`` at ``out_path``, and return its
    manifest."""
    base = Path(store_dir)
    destination = Path(out_path)
    if destination.is_dir():
        raise BackupError(f"{destination} is a directory; name the archive file to write")
    manifest = build_manifest(base)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staged = destination.with_name(destination.name + ".partial")
    try:
        with tarfile.open(staged, "w", format=tarfile.PAX_FORMAT) as tar:
            payload = manifest.to_json()
            tar.addfile(_tarinfo(MANIFEST_MEMBER, len(payload)), io.BytesIO(payload))
            for entry in manifest.files:
                source = base / entry.name
                with source.open("rb") as handle:
                    tar.addfile(_tarinfo(STORE_MEMBER_PREFIX + entry.name, entry.bytes), handle)
        staged.replace(destination)
    finally:
        staged.unlink(missing_ok=True)
    return manifest


# -- reading an archive --------------------------------------------------------------------


def _member_target(member: tarfile.TarInfo) -> str | None:
    """The store-relative path this member restores to, or ``None`` if it is not a store file.

    Refuses anything that is not a plain regular file under the store prefix: an absolute name, a
    ``..`` segment, a symlink, a hardlink, a device node or a directory entry. This is why nothing
    in this module calls ``extractall`` — a member that cannot be named safely is a refusal, and
    a refusal has to happen before any byte is written.
    """
    name = member.name
    if name == MANIFEST_MEMBER:
        return None
    if not name.startswith(STORE_MEMBER_PREFIX):
        raise BackupError(f"archive member {name!r} is outside {STORE_MEMBER_PREFIX!r}")
    if not member.isreg():
        raise BackupError(f"archive member {name!r} is not a regular file")
    relative = name[len(STORE_MEMBER_PREFIX) :]
    parts = Path(relative).parts
    if not relative or relative.startswith("/") or ".." in parts or Path(relative).is_absolute():
        raise BackupError(f"archive member {name!r} does not name a path inside the store")
    return relative


def read_manifest(archive: str | Path) -> BackupManifest:
    """Read and validate ``BACKUP-MANIFEST.json`` without extracting anything."""
    path = Path(archive)
    if not path.is_file():
        raise BackupError(f"{path} does not exist")
    try:
        with tarfile.open(path, "r:") as tar:
            handle = tar.extractfile(MANIFEST_MEMBER)
            if handle is None:
                raise BackupError(f"{path} contains no {MANIFEST_MEMBER}")
            return BackupManifest.from_bytes(handle.read())
    except KeyError as exc:
        raise BackupError(f"{path} contains no {MANIFEST_MEMBER}") from exc
    except tarfile.TarError as exc:
        raise BackupError(f"{path} is not a readable tar archive: {exc}") from exc


def _extract_store(archive: Path, into: Path) -> list[str]:
    """Extract every store member into ``into``, one at a time, and return their relative names."""
    written: list[str] = []
    with tarfile.open(archive, "r:") as tar:
        for member in tar.getmembers():
            relative = _member_target(member)
            if relative is None:
                continue
            handle = tar.extractfile(member)
            if handle is None:
                raise BackupError(f"archive member {member.name!r} has no readable content")
            out = into / relative
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open("wb") as sink:
                shutil.copyfileobj(handle, sink)
            written.append(relative)
    return written


# -- verifying a restore -------------------------------------------------------------------


def _check_members(manifest: BackupManifest, written: Sequence[str]) -> Check:
    recorded = {f.name for f in manifest.files}
    present = set(written)
    missing = sorted(recorded - present)
    extra = sorted(present - recorded)
    if missing or extra:
        parts = []
        if missing:
            parts.append(f"missing {', '.join(missing)}")
        if extra:
            parts.append(f"unrecorded {', '.join(extra)}")
        return Check("members", CHECK_FAIL, "; ".join(parts))
    return Check("members", CHECK_OK, f"{len(recorded)} file(s) restored, none missing, none extra")


def _check_file_digests(manifest: BackupManifest, target: Path) -> Check:
    bad: list[str] = []
    for entry in manifest.files:
        path = target / entry.name
        if not path.is_file():
            bad.append(f"{entry.name} (absent)")
            continue
        if path.stat().st_size != entry.bytes or _sha256_path(path) != entry.sha256:
            bad.append(f"{entry.name} (digest)")
    if bad:
        return Check("file_digests", CHECK_FAIL, f"{len(bad)} file(s) differ: {', '.join(bad)}")
    return Check(
        "file_digests", CHECK_OK, f"{len(manifest.files)} file(s) match their recorded digest"
    )


def _check_rows(manifest: BackupManifest, target: Path) -> list[Check]:
    """Re-open the restored store and ask the archive's own three questions of the data.

    ``open_store`` creates a database when none exists, so the file is checked first: opening a
    missing store would manufacture an empty one, and an empty store passes ``verify_rows`` and
    folds to an empty chain — three green checks over nothing.
    """
    db = store_paths(target)["db"]
    if not db.is_file():
        absent = f"{db.name} is not in the archive"
        return [
            Check("row_count", CHECK_FAIL, absent),
            Check("row_hashes", CHECK_FAIL, absent),
            Check("digest_chain", CHECK_FAIL, absent),
        ]
    with open_store(target) as store:
        rows = store.count()
        mismatches = verify_rows(store)
        digests = daily_digests(store)
    head = digests[-1].chain if digests else None
    checks: list[Check] = []
    if rows == manifest.row_count:
        checks.append(Check("row_count", CHECK_OK, f"{rows} row(s), as recorded"))
    else:
        checks.append(
            Check(
                "row_count",
                CHECK_FAIL,
                f"{rows} row(s) restored, the manifest records {manifest.row_count}",
            )
        )
    if mismatches:
        checks.append(
            Check(
                "row_hashes",
                CHECK_FAIL,
                f"{len(mismatches)} row(s) no longer hash to what was stored",
            )
        )
    else:
        checks.append(
            Check("row_hashes", CHECK_OK, f"{rows} row(s) match their stored content hash")
        )
    checks.append(_chain_check(head, manifest.digest_head, len(digests)))
    return checks


def _chain_check(head: str | None, recorded: str | None, days: int) -> Check:
    """Compare the recomputed chain head with the recorded one — and never match two absences.

    A store with no rows folds to no chain at all. If both sides of this comparison were allowed
    to be "nothing", an archive of an empty store would agree with an empty restore of it and the
    check would report success over a store containing no data whatsoever.
    """
    if recorded is None:
        return Check(
            "digest_chain", CHECK_FAIL, "the manifest records no chain head to compare against"
        )
    if head is None:
        return Check(
            "digest_chain", CHECK_FAIL, "the restored store has no rows, so it folds to no chain"
        )
    if head != recorded:
        return Check(
            "digest_chain",
            CHECK_FAIL,
            f"head {head[:12]}… does not match the recorded {recorded[:12]}…",
        )
    return Check("digest_chain", CHECK_OK, f"head {recorded[:12]}… over {days} day(s)")


def _conditional_file_check(
    name: str, filename: str, manifest: BackupManifest, target: Path
) -> Check:
    """Check a file the archive may or may not have carried — and say which case this is.

    The ``NOT_APPLICABLE`` branch is the whole point. A store that never had a correction
    registry has nothing to lose, and reporting that as a pass would make an archive of a
    never-calibrated store look exactly like an archive whose registry survived.
    """
    recorded = manifest.store_file(filename)
    if recorded is None:
        return Check(name, CHECK_NA, f"the store had no {filename} when it was archived")
    path = target / filename
    if not path.is_file():
        return Check(name, CHECK_FAIL, f"{filename} was archived but is not in the restored store")
    if path.stat().st_size == 0 and recorded.bytes > 0:
        return Check(
            name, CHECK_FAIL, f"{filename} restored empty; {recorded.bytes} byte(s) were archived"
        )
    return Check(name, CHECK_OK, f"{filename} restored, {recorded.bytes} byte(s)")


def _check_rights(manifest: BackupManifest, target: Path) -> list[Check]:
    checks = [_conditional_file_check("rights", SOURCE_METADATA_FILENAME, manifest, target)]
    if manifest.rights is None:
        checks.append(
            Check(
                "license_ledger",
                CHECK_NA,
                "the store recorded no third-party source terms, so it carries no ledger",
            )
        )
    else:
        checks.append(
            _conditional_file_check(
                "license_ledger", SOURCE_LICENSE_LEDGER_FILENAME, manifest, target
            )
        )
    return checks


def _verify_restored(manifest: BackupManifest, target: Path, written: Sequence[str]) -> list[Check]:
    checks = [
        Check(
            "manifest",
            CHECK_OK,
            f"schema {manifest.schema_version}, written by swelter {manifest.swelter_version}",
        ),
        _check_members(manifest, written),
        _check_file_digests(manifest, target),
    ]
    checks.extend(_check_rows(manifest, target))
    checks.append(_conditional_file_check("corrections", _REGISTRY_NAME, manifest, target))
    checks.append(_conditional_file_check("digests_file", _DIGESTS_NAME, manifest, target))
    checks.extend(_check_rights(manifest, target))
    return checks


def restore_archive(
    archive: str | Path, target: str | Path | None, *, force: bool = False
) -> Receipt:
    """Restore an archive into ``target``, but only after every check on it has passed.

    Extraction happens into a staging directory that is never the operator's store. The staged
    copy is verified there, and moved into place only on a ``verified`` verdict, so a failed drill
    leaves the target exactly as it was — including not existing. Pass ``target=None`` to run the
    drill and throw the restored copy away, which is the form a scheduled rehearsal wants.
    """
    source = Path(archive)
    destination = Path(target) if target is not None else None
    if destination is not None and destination.exists():
        if not destination.is_dir():
            raise BackupError(f"{destination} exists and is not a directory")
        if any(destination.iterdir()) and not force:
            raise BackupError(
                f"{destination} is not empty; restoring would mix two stores — remove it, name an "
                "empty directory, or pass --force to overwrite it"
            )
    manifest = read_manifest(source)
    staging = Path(tempfile.mkdtemp(prefix="swelter-restore-"))
    try:
        written = _extract_store(source, staging)
        checks = _verify_restored(manifest, staging, written)
        receipt = Receipt(
            archive=str(source),
            target=str(destination) if destination is not None else None,
            checks=tuple(checks),
            manifest=manifest,
            restored=False,
        )
        if receipt.verdict != "verified" or destination is None:
            return receipt
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staging), str(destination))
        staging = destination  # moved; nothing left to clean up
        return Receipt(
            archive=str(source),
            target=str(destination),
            checks=tuple(checks),
            manifest=manifest,
            restored=True,
        )
    finally:
        if staging.exists() and staging != destination:
            shutil.rmtree(staging, ignore_errors=True)


# -- retention -----------------------------------------------------------------------------


def _archives(directory: Path) -> list[Path]:
    """Archives newest-first. Ties break by name so the order is total, never arbitrary."""
    return sorted(
        (p for p in directory.glob("*.tar") if p.is_file()),
        key=lambda p: (-p.stat().st_mtime, p.name),
    )


def _measure(handle: IO[bytes]) -> tuple[int, str]:
    """Size and SHA-256 of a stream, read in chunks so a large database is never held in memory."""
    digest = hashlib.sha256()
    size = 0
    while True:
        chunk = handle.read(_READ_CHUNK)
        if not chunk:
            break
        digest.update(chunk)
        size += len(chunk)
    return size, digest.hexdigest()


def _measure_members(path: Path) -> dict[str, tuple[int, str]]:
    measured: dict[str, tuple[int, str]] = {}
    with tarfile.open(path, "r:") as tar:
        for member in tar.getmembers():
            relative = _member_target(member)
            if relative is None:
                continue
            handle = tar.extractfile(member)
            if handle is None:
                raise BackupError(f"member {member.name!r} has no readable content")
            measured[relative] = _measure(handle)
    return measured


def _verify_archive_bytes(path: Path) -> str | None:
    """``None`` when the archive verifies against its own manifest, else the reason it does not."""
    try:
        manifest = read_manifest(path)
        measured = _measure_members(path)
    except BackupError as exc:
        return str(exc)
    except (tarfile.TarError, OSError) as exc:
        return f"unreadable: {exc}"
    recorded = {f.name: (f.bytes, f.sha256) for f in manifest.files}
    missing = sorted(set(recorded) - set(measured))
    if missing:
        return f"missing {', '.join(missing)}"
    extra = sorted(set(measured) - set(recorded))
    if extra:
        return f"unrecorded {', '.join(extra)}"
    bad = sorted(name for name, seen in measured.items() if seen != recorded[name])
    if bad:
        return f"digest mismatch: {', '.join(bad)}"
    return None


def plan_prune(directory: str | Path, keep: int) -> PrunePlan:
    """Decide which archives to keep — and refuse the whole plan if any cannot be verified.

    Two rules, both about not acting on absence. A directory holding an archive that cannot be
    read is a directory nobody can reason about, so nothing is deleted from it at all. And
    ``keep`` is clamped to at least one: a retention policy that can empty the shelf is not a
    retention policy, and "keep 0" is a request nobody who is rehearsing recovery means.
    """
    base = Path(directory)
    if not base.is_dir():
        raise BackupError(f"{base} is not a directory")
    effective = max(1, keep)
    found = _archives(base)
    unverifiable: list[tuple[str, str]] = []
    for path in found:
        reason = _verify_archive_bytes(path)
        if reason is not None:
            unverifiable.append((path.name, reason))
    if unverifiable:
        return PrunePlan(
            keep=effective,
            kept=tuple(p.name for p in found),
            deleted=(),
            unverifiable=tuple(unverifiable),
        )
    return PrunePlan(
        keep=effective,
        kept=tuple(p.name for p in found[:effective]),
        deleted=tuple(p.name for p in found[effective:]),
        unverifiable=(),
    )


def apply_prune(directory: str | Path, plan: PrunePlan) -> None:
    """Delete exactly what ``plan`` names, and nothing when the plan is a refusal."""
    if plan.refused:
        raise BackupError(
            "refusing to prune: " + "; ".join(f"{name} ({why})" for name, why in plan.unverifiable)
        )
    base = Path(directory)
    for name in plan.deleted:
        (base / name).unlink(missing_ok=True)


# -- rendering -----------------------------------------------------------------------------


def render_receipt(receipt: Receipt) -> Iterator[str]:
    """Human-readable receipt lines. ``NOT_APPLICABLE`` gets its own tally, never the pass one."""
    yield f"swelter: restore {receipt.verdict.upper()} — {receipt.archive}"
    for check in receipt.checks:
        yield f"  {check.status:<15} {check.name:<15} {check.detail}"
    yield (
        f"  {len(receipt.passed)} passed, {len(receipt.failed)} failed, "
        f"{len(receipt.not_applicable)} not applicable (not counted as passing)"
    )
    if receipt.target is None:
        yield "  no store written (verification run only)"
    elif receipt.restored:
        yield f"  restored to {receipt.target}"
    else:
        yield f"  {receipt.target} left unwritten — a failed verification restores nothing"


def render_manifest(manifest: BackupManifest, archive: Path) -> Iterator[str]:
    """Human-readable summary of what was just written."""
    yield f"swelter: wrote {archive}"
    yield f"  {manifest.row_count} row(s) from {manifest.node_count} node(s)"
    if manifest.observation_window is not None:
        yield f"  window      {manifest.observation_window[0]} → {manifest.observation_window[1]}"
    yield f"  chain head  {manifest.digest_head} ({manifest.digest_days} day(s))"
    yield f"  files       {len(manifest.files)}"
    if manifest.rights is not None:
        yield f"  rights      {manifest.rights['source']} — {manifest.rights['license']}"


def render_prune(plan: PrunePlan, directory: Path) -> Iterator[str]:
    if plan.refused:
        yield f"swelter: prune REFUSED in {directory} — nothing was deleted"
        for name, why in plan.unverifiable:
            yield f"  UNVERIFIABLE  {name}: {why}"
        return
    yield f"swelter: prune {directory} — keeping {len(plan.kept)}, deleting {len(plan.deleted)}"
    for name in plan.kept:
        yield f"  keep    {name}"
    for name in plan.deleted:
        yield f"  delete  {name}"
