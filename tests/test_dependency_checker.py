import os

import pytest

from stackant.dependency_checker import ToolStatus, missing_deps_message


@pytest.fixture(autouse=True)
def _no_allow_missing(monkeypatch):
    monkeypatch.delenv("STACKANT_ALLOW_MISSING", raising=False)


def test_all_present_returns_none():
    statuses = [
        ToolStatus("ffmpeg", "/usr/bin/ffmpeg", "ffmpeg version 6.1.1"),
        ToolStatus("focus-stack", "/usr/local/bin/focus-stack", "focus-stack 1.3"),
    ]
    assert missing_deps_message(statuses) is None


def test_missing_focus_stack_mentions_tool_and_source():
    statuses = [
        ToolStatus("ffmpeg", "/usr/bin/ffmpeg", "ffmpeg version 6.1.1"),
        ToolStatus("focus-stack", None, None),
    ]
    msg = missing_deps_message(statuses)
    assert msg is not None
    assert "focus-stack" in msg
    assert "github.com" in msg.lower() or "petteriaimonen" in msg.lower()


def test_missing_ffmpeg_message_present():
    statuses = [
        ToolStatus("ffmpeg", None, None),
        ToolStatus("focus-stack", "/usr/local/bin/focus-stack", "v"),
    ]
    msg = missing_deps_message(statuses)
    assert msg is not None
    assert "ffmpeg" in msg


def test_allow_missing_env_skips_block(monkeypatch):
    monkeypatch.setenv("STACKANT_ALLOW_MISSING", "focus-stack")
    statuses = [
        ToolStatus("ffmpeg", "/usr/bin/ffmpeg", "v"),
        ToolStatus("focus-stack", None, None),
    ]
    assert missing_deps_message(statuses) is None


def test_allow_missing_env_still_blocks_ffmpeg(monkeypatch):
    monkeypatch.setenv("STACKANT_ALLOW_MISSING", "focus-stack")
    statuses = [
        ToolStatus("ffmpeg", None, None),
        ToolStatus("focus-stack", None, None),
    ]
    msg = missing_deps_message(statuses)
    assert msg is not None
    assert "ffmpeg" in msg
    assert "focus-stack" not in msg
