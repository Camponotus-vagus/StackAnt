"""Start StackAnt from a self-repairing virtualenv.

A venv hard-codes the absolute path of the Python that created it, so a
`.venv` copied or synced from another machine, or orphaned by a Homebrew /
python.org upgrade, stops working. This launcher recreates `.venv` whenever
it no longer runs, reinstalls dependencies whenever requirements.txt
changes, then starts the app.

    python3 run.py          (Windows: py run.py)
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
STAMP = VENV / ".requirements.sha256"


def venv_python() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def runs(python: Path) -> bool:
    try:
        return subprocess.run(
            [str(python), "-c", "import sys"], capture_output=True, check=False
        ).returncode == 0
    except OSError:
        return False


def ensure_venv() -> Path:
    python = venv_python()
    if VENV.exists() and not runs(python):
        print("StackAnt: .venv is broken (made by a Python that is gone); recreating it…")
        shutil.rmtree(VENV)
    if not VENV.exists():
        print(f"StackAnt: creating .venv with Python {sys.version.split()[0]}…")
        venv.create(VENV, with_pip=True)

    digest = hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()
    if not STAMP.exists() or STAMP.read_text().strip() != digest:
        print("StackAnt: installing dependencies…")
        subprocess.run(
            [str(python), "-m", "pip", "install", "-r", str(REQUIREMENTS)], check=True
        )
        STAMP.write_text(digest)
    return python


_NEWER_PYTHONS = ("python3.13", "python3.12", "python3.11", "python3.10")
# Where Homebrew (Apple silicon, Intel) and the python.org installer put
# Python on macOS; the first two are often missing from a GUI-launched PATH.
_EXTRA_DIRS = (
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/Library/Frameworks/Python.framework/Versions/Current/bin",
)


def find_newer_python() -> str | None:
    for name in _NEWER_PYTHONS:
        found = shutil.which(name)
        if found:
            return found
        for folder in _EXTRA_DIRS:
            candidate = Path(folder) / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    return None


def main() -> None:
    # run.py is the one file an older system Python may execute: macOS's
    # /usr/bin/python3 is 3.9. Hand over to a newer one if it is installed.
    if sys.version_info < (3, 10):  # noqa: UP036
        newer = find_newer_python()
        if newer and os.name != "nt":
            os.execv(newer, [newer, str(Path(__file__).resolve()), *sys.argv[1:]])
        sys.exit(
            f"StackAnt needs Python 3.10 or newer (this is {sys.version.split()[0]}).\n"
            "macOS: brew install python@3.12   (or the installer from python.org)\n"
            "Then run this again: python3 run.py"
        )
    python = ensure_venv()
    args = [str(python), str(ROOT / "main.py"), *sys.argv[1:]]
    if os.name == "nt":
        sys.exit(subprocess.call(args))
    os.execv(str(python), args)


if __name__ == "__main__":
    main()
