"""``swelter init`` and the next step it names, run from an installed wheel outside the repository.

Every other test here runs against the checkout, where ``uv sync`` installs the package in
editable mode and ``data/demo`` is always beside it. That is the one path no other test can see,
and it is where ``init``'s success message was wrong until 2026-09-02: it named
``swelter demo --serve`` as the next step, ``demo`` replays ``data/demo/observations.jsonl``,
which is deliberately not package data, and so every wheel-only install that followed the hint
got a ``FileNotFoundError`` traceback.

So this test builds the wheel, installs it into a fresh virtual environment, checks that the
environment imports the wheel's package rather than this checkout, runs the README's documented
``swelter init`` line from a directory that is not the repository, and then runs every command
the hint names, in that directory, from that install. A hint is a promise; this is where it is
kept. It also checks that ``swelter demo`` from that install refuses in one line rather than a
traceback.

The harness fails rather than skips when it cannot do its job: no ``uv`` on PATH, a build or
install that fails, a README that no longer documents ``init``. Each of those messages says the
wheel path was NOT examined, so it reads differently from the hint itself failing. A skipped test
here would be a green mark over the one path nobody looked at. A hinted command that serves and
waits would hit the per-command timeout and fail, which is the right outcome for a hint an
installed wheel cannot finish.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"

NOT_EXAMINED = "the installed-wheel path was NOT examined"
HARNESS_TIMEOUT_SECONDS = 600
HINT_TIMEOUT_SECONDS = 120

#: A command line in ``init``'s hint: indented, and nothing on the line but the command.
HINTED = re.compile(r"^\s+(swelter .+)$", re.MULTILINE)


def _uv() -> str:
    found = shutil.which("uv")
    if found is None:
        pytest.fail(f"uv is not on PATH; {NOT_EXAMINED}")
    return found


def _clean_env() -> dict[str, str]:
    """The environment for the build and the fresh venv: none of this checkout's."""
    dropped = {"VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "PYTHONPATH", "PYTHONHOME"}
    return {key: value for key, value in os.environ.items() if key not in dropped}


def _harness(argv: list[str], cwd: Path | None = None) -> str:
    """Run one harness step; a non-zero exit is the not-examined state."""
    result = subprocess.run(  # noqa: S603 -- argv is built here from known paths
        argv,
        cwd=cwd,
        env=_clean_env(),
        capture_output=True,
        text=True,
        timeout=HARNESS_TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(
            f"`{' '.join(argv[:2])} ...` exited {result.returncode}; {NOT_EXAMINED}\n"
            f"{result.stderr}"
        )
    return result.stdout


def documented_init_command(readme_text: str) -> list[str]:
    """The argv tail of the README's ``uv run swelter init ...`` line, minus ``uv run``."""
    for line in readme_text.splitlines():
        if line.strip().startswith("uv run swelter init "):
            return shlex.split(line, comments=True)[3:]
    pytest.fail(f"README.md no longer documents `uv run swelter init ...`; {NOT_EXAMINED}")


def hinted_commands(stderr: str) -> list[list[str]]:
    """Every ``swelter ...`` command line in ``init``'s hint, minus the program name."""
    return [shlex.split(match.group(1))[1:] for match in HINTED.finditer(stderr)]


def test_the_hint_parser_reads_command_lines_and_nothing_else() -> None:
    stderr = (
        "swelter: wrote starter network → my-network.yaml (2 nodes)\n"
        "next: edit it (see https://example.invalid/doc), then check it:\n"
        "      swelter doctor --config my-network.yaml\n"
        "      …then run the pipeline against it with --config my-network.yaml\n"
        "      the bundled demo replays recorded data that ships with the repository:\n"
        "      git clone https://example.invalid/swelter && cd swelter && make demo\n"
    )

    assert hinted_commands(stderr) == [["doctor", "--config", "my-network.yaml"]]


def test_the_readme_still_documents_init() -> None:
    argv = documented_init_command(README.read_text(encoding="utf-8"))

    assert argv[0] == "init"
    assert "--config" in argv


def _operand(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


def test_init_and_its_next_step_run_from_an_installed_wheel(tmp_path: Path) -> None:
    uv = _uv()
    dist = tmp_path / "dist"
    venv = tmp_path / "venv"
    outside = tmp_path / "outside"
    outside.mkdir()

    _harness(
        [uv, "build", "--wheel", "--out-dir", str(dist), "--python", sys.executable, str(ROOT)]
    )
    wheels = sorted(dist.glob("swelter-*.whl"))
    if len(wheels) != 1:
        pytest.fail(f"expected one wheel, found {len(wheels)}; {NOT_EXAMINED}")
    _harness([uv, "venv", "--python", sys.executable, str(venv)])
    bin_dir = venv / ("Scripts" if os.name == "nt" else "bin")
    python = bin_dir / ("python.exe" if os.name == "nt" else "python")
    _harness([uv, "pip", "install", "--python", str(python), str(wheels[0])])

    # The denominator: the interpreter about to run `init` imports the wheel's package, not this
    # checkout's, and the directory it runs in has no data/demo.
    located = Path(
        _harness(
            [str(python), "-c", "import swelter; print(swelter.__file__)"], cwd=outside
        ).strip()
    ).resolve()
    assert located.is_relative_to(venv.resolve()), (
        f"the fresh venv imported {located}, not the installed wheel; {NOT_EXAMINED}"
    )
    assert not (outside / "data" / "demo").exists()

    swelter = bin_dir / ("swelter.exe" if os.name == "nt" else "swelter")
    init_argv = documented_init_command(README.read_text(encoding="utf-8"))
    init = subprocess.run(  # noqa: S603 -- argv comes from the README line
        [str(swelter), *init_argv],
        cwd=outside,
        env=_clean_env(),
        capture_output=True,
        text=True,
        timeout=HINT_TIMEOUT_SECONDS,
        check=False,
    )
    assert init.returncode == 0, (
        f"`swelter {' '.join(init_argv)}` exited {init.returncode} from an installed wheel, "
        f"outside the repository:\n{init.stderr}"
    )
    assert (outside / _operand(init_argv, "--config")).is_file()

    hinted = hinted_commands(init.stderr)
    assert hinted, f"init's hint names no command to run next:\n{init.stderr}"
    for argv in hinted:
        result = subprocess.run(  # noqa: S603 -- argv comes from init's own hint
            [str(swelter), *argv],
            cwd=outside,
            env=_clean_env(),
            capture_output=True,
            text=True,
            timeout=HINT_TIMEOUT_SECONDS,
            check=False,
        )
        assert result.returncode == 0, (
            f"init hinted `swelter {' '.join(argv)}`, which exited {result.returncode} from the "
            f"same installed wheel, in the same directory:\n{result.stderr}"
        )

    # And the demo, which the hint must not name here, refuses in one line rather than a traceback.
    demo = subprocess.run(  # noqa: S603 -- fixed argv
        [str(swelter), "demo"],
        cwd=outside,
        env=_clean_env(),
        capture_output=True,
        text=True,
        timeout=HINT_TIMEOUT_SECONDS,
        check=False,
    )
    assert demo.returncode == 1, demo.stderr
    assert "swelter demo: no recorded data at data/demo" in demo.stderr
    assert "Traceback" not in demo.stderr
