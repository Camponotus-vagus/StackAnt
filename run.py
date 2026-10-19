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


def main() -> None:
    # run.py is the one file an older system Python may execute.
    if sys.version_info < (3, 10):  # noqa: UP036
        sys.exit(f"StackAnt needs Python 3.10 or newer (this is {sys.version.split()[0]}).")
    python = ensure_venv()
    args = [str(python), str(ROOT / "main.py"), *sys.argv[1:]]
    if os.name == "nt":
        sys.exit(subprocess.call(args))
    os.execv(str(python), args)


if __name__ == "__main__":
    main()
