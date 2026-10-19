"""Verify external tools (ffmpeg, focus-stack) are installed.

Runs at startup before the main window appears. Version probing uses blocking
subprocess.run here because each call is a one-shot that completes in <100ms;
QProcess is reserved for the long-running workflow calls.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass

REQUIRED_TOOLS: tuple[str, ...] = ("ffmpeg", "focus-stack")
_ALLOW_MISSING_ENV = "STACKANT_ALLOW_MISSING"
# Where tools usually land outside a GUI-launched PATH: a self-built
# focus-stack copied to ~/.local/bin, Homebrew on Apple silicon and Intel.
_EXTRA_TOOL_DIRS: tuple[str, ...] = ("~/.local/bin", "/opt/homebrew/bin", "/usr/local/bin")


@dataclass(frozen=True)
class ToolStatus:
    name: str
    path: str | None
    version: str | None

    @property
    def present(self) -> bool:
        return self.path is not None


def _probe_version(path: str) -> str | None:
    try:
        result = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    raw = (result.stdout or result.stderr or "").strip()
    return raw.splitlines()[0] if raw else None


def augment_path(env=None) -> list[str]:
    """Append existing well-known tool dirs missing from PATH; return those added.

    Appended, not prepended, so the user's own PATH order still wins. Both the
    check below and every QProcess launch resolve tools through this PATH.
    """
    if os.name == "nt":
        return []
    env = os.environ if env is None else env
    current = env.get("PATH", "")
    parts = [p for p in current.split(os.pathsep) if p]
    added = []
    for raw in _EXTRA_TOOL_DIRS:
        folder = os.path.expanduser(raw)
        if folder not in parts and os.path.isdir(folder):
            parts.append(folder)
            added.append(folder)
    if added:
        env["PATH"] = os.pathsep.join(parts)
    return added


def check() -> list[ToolStatus]:
    statuses: list[ToolStatus] = []
    for name in REQUIRED_TOOLS:
        path = shutil.which(name)
        version = _probe_version(path) if path else None
        statuses.append(ToolStatus(name=name, path=path, version=version))
    return statuses


def _install_hint(tool: str, system: str) -> str:
    if tool == "ffmpeg":
        if system == "Linux":
            return "  • ffmpeg:\n      sudo apt install ffmpeg"
        if system == "Windows":
            return (
                "  • ffmpeg: download a static build from\n"
                "      https://www.gyan.dev/ffmpeg/builds/\n"
                "    and add the bin/ folder to PATH."
            )
        return "  • ffmpeg: install via your package manager."
    if tool == "focus-stack":
        if system == "Linux":
            return (
                "  • focus-stack: build from source (PetteriAimonen/focus-stack):\n"
                "      git clone https://github.com/PetteriAimonen/focus-stack\n"
                "      cd focus-stack && make\n"
                "      sudo cp focus-stack /usr/local/bin/"
            )
        if system == "Windows":
            return (
                "  • focus-stack: download a release binary from\n"
                "      https://github.com/PetteriAimonen/focus-stack/releases\n"
                "    and place it in a folder on PATH."
            )
        return "  • focus-stack: build from https://github.com/PetteriAimonen/focus-stack"
    return f"  • {tool}: install and add to PATH."


def _allowed_missing() -> set[str]:
    raw = os.environ.get(_ALLOW_MISSING_ENV, "")
    return {s.strip() for s in raw.split(",") if s.strip()}


def missing_deps_message(statuses: Iterable[ToolStatus]) -> str | None:
    allowed = _allowed_missing()
    missing = [s.name for s in statuses if not s.present and s.name not in allowed]
    if not missing:
        return None
    system = platform.system()
    bullet_list = "\n".join(f"  ✗ {name}" for name in missing)
    hints = "\n".join(_install_hint(tool, system) for tool in missing)
    return (
        "StackAnt needs the following tools to be installed and on your PATH:\n\n"
        f"{bullet_list}\n\n"
        "Install instructions:\n\n"
        f"{hints}\n\n"
        "See the README for more details."
    )
