#!/usr/bin/env python3
"""Demo-artifact gate: committed demo web artifacts must equal what the pipeline computes.

``web/sample-surface.json`` is a committed file, served by ``web/app.js`` as the
dashboard's offline fallback and cached by ``web/sw.js``. It is also a generated file:
``swelter demo`` rebuilds it deterministically from the committed recorded week in
``data/demo/``. Nothing held those two facts together. When #142 corrected the derived
heat-index uncertainty (scaling by the local |dHI/dT|), the pipeline's output changed and
the committed artifact did not: eleven single-member ``heat_index_c`` cells kept their
pre-fix error bars, each smaller than what the current code computes. The schema contract
test could not notice, because the stale file and the fresh file both satisfy the schema.
A committed artifact standing in for a computation needs a gate that re-runs the
computation.

This gate replays the committed demo into a throwaway store and web directory, then
byte-compares every file the replay wrote that is also tracked in git under ``web/``.
Three failure modes are refused explicitly rather than passed silently:

- any compared file differing from its committed copy (the drift this gate exists for);
- a comparison set that is empty or missing ``web/sample-surface.json`` (a renamed
  artifact or changed writer must not turn this into a gate that compares nothing,
  the same failure shape as a coverage glob matching no files);
- the replay itself failing.

The fix for a red run is never to hand-edit the committed values: regenerate with
``uv run swelter demo``, review the diff, and commit it, with a changelog line naming
what moved and why.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SENTINEL = "web/sample-surface.json"


def tracked_web_files(root: Path) -> set[str]:
    """Repo-relative paths of every git-tracked file under web/."""
    # Fixed argv, no shell, no user input -- a dev-time/CI gate script.
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("demo-artifacts gate requires git on PATH")
    proc = subprocess.run(  # noqa: S603 (#107)
        [git, "ls-files", "--", "web"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def replay_demo(root: Path, tmp: Path) -> subprocess.CompletedProcess[str]:
    """Run the demo replay into a throwaway store and web directory, touching nothing tracked."""
    web_dir = tmp / "web"
    web_dir.mkdir(parents=True)
    return subprocess.run(  # noqa: S603 (#107)
        [
            sys.executable,
            "-m",
            "swelter",
            "demo",
            "--store",
            str(tmp / "store"),
            "--web",
            str(web_dir),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def compare_generated(root: Path, tmp_web: Path, tracked: set[str]) -> tuple[list[str], list[str]]:
    """Byte-compare each regenerated file that is tracked under web/.

    Returns ``(compared, drifted)`` as repo-relative path lists.
    """
    compared: list[str] = []
    drifted: list[str] = []
    for generated in sorted(p for p in tmp_web.rglob("*") if p.is_file()):
        rel = f"web/{generated.relative_to(tmp_web).as_posix()}"
        if rel not in tracked:
            continue
        compared.append(rel)
        committed = root / rel
        if not committed.is_file() or committed.read_bytes() != generated.read_bytes():
            drifted.append(rel)
    return compared, drifted


def main() -> int:
    tracked = tracked_web_files(ROOT)
    with tempfile.TemporaryDirectory(prefix="swelter-demo-artifact-") as tmpdir:
        tmp = Path(tmpdir)
        proc = replay_demo(ROOT, tmp)
        if proc.returncode != 0:
            print("demo-artifacts: the demo replay itself failed, so nothing was compared")
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return 1
        compared, drifted = compare_generated(ROOT, tmp / "web", tracked)

    if not compared or SENTINEL not in compared:
        print(
            "demo-artifacts: the comparison set is empty or no longer includes "
            f"{SENTINEL}; a gate that compares nothing must not pass "
            f"(compared: {compared or 'nothing'})"
        )
        return 1

    for rel in compared:
        marker = "DRIFT" if rel in drifted else "ok"
        print(f"  [{marker:>5}] {rel}")
    if drifted:
        print(
            f"demo-artifacts: {len(drifted)} committed artifact(s) no longer match what "
            "the pipeline computes from data/demo/. Do not hand-edit the values: run "
            "`uv run swelter demo`, review the diff, and commit it with a changelog "
            "line naming what moved."
        )
        return 1
    print(f"demo-artifacts: {len(compared)} committed artifact(s) match a fresh replay")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
