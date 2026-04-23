from stackant.dependency_checker import ToolStatus, missing_deps_message


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
