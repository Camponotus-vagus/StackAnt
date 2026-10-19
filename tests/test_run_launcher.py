"""run.py must hand over from an old system Python (macOS ships 3.9)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_run():
    spec = importlib.util.spec_from_file_location("stackant_run", ROOT / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.skipif(sys.platform == "win32", reason="execv hand-over is POSIX only")
def test_old_python_reexecs_with_newer_one(monkeypatch, tmp_path):
    run = _load_run()
    fake = tmp_path / "python3.12"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(run, "_EXTRA_DIRS", ())
    monkeypatch.setattr(run.sys, "version_info", (3, 9, 6))
    calls = []

    def fake_execv(path, args):
        calls.append((path, args))
        raise SystemExit(0)

    monkeypatch.setattr(run.os, "execv", fake_execv)
    monkeypatch.setattr(run, "ensure_venv", lambda: pytest.fail("must not build a venv on 3.9"))
    with pytest.raises(SystemExit):
        run.main()
    assert calls[0][0] == str(fake)
    assert calls[0][1][1] == str(ROOT / "run.py")


def test_old_python_without_newer_one_explains_how_to_fix(monkeypatch, tmp_path):
    run = _load_run()
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(run, "_EXTRA_DIRS", ())
    monkeypatch.setattr(run.sys, "version_info", (3, 9, 6))
    with pytest.raises(SystemExit) as exc:
        run.main()
    assert "brew install python" in str(exc.value)
