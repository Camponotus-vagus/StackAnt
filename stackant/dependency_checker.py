"""Verify external tools (ffmpeg, focus-stack) are installed.

Runs at startup before the main window appears. Version probing uses blocking
subprocess.run here because each call is a one-shot that completes in <100ms;
QProcess is reserved for the long-running workflow calls.
"""
from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass
from typing import Iterable

REQUIRED_TOOLS: tuple[str, ...] = ("ffmpeg", "focus-stack")


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
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    raw = (result.stdout or result.stderr or "").strip()
    return raw.splitlines()[0] if raw else None


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


def missing_deps_message(statuses: Iterable[ToolStatus]) -> str | None:
    missing = [s.name for s in statuses if not s.present]
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
