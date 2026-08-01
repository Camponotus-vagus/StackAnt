"""ffmpeg-based frame extraction as a non-blocking QProcess."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, pyqtSignal

FRAME_PATTERN = "frame_%05d.tif"
_PROGRESS_RE = re.compile(rb"frame=\s*(\d+)")


def build_ffmpeg_args(
    video_path: str,
    out_dir: str,
    decimation: int = 1,
    start_sec: float | None = None,
    end_sec: float | None = None,
) -> list[str]:
    """Build ffmpeg CLI arguments (the 'ffmpeg' program name is not included)."""
    args: list[str] = ["-hide_banner", "-y"]
    if start_sec:
        args += ["-ss", f"{start_sec}"]
    if end_sec:
        args += ["-to", f"{end_sec}"]
    args += ["-i", video_path]
    if decimation > 1:
        args += ["-vf", rf"select='not(mod(n\,{decimation}))'"]
    args += [
        "-fps_mode",
        "vfr",
        "-start_number",
        "0",
        str(Path(out_dir) / FRAME_PATTERN),
    ]
    return args


def probe_frame_count(path: str) -> int | None:
    """Return total video frame count via ffprobe; None if probe fails."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-count_packets",
                "-show_entries",
                "stream=nb_read_packets",
                "-of",
                "csv=p=0",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        n = int(result.stdout.strip())
        return n if n > 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


class FrameExtractor(QObject):
    progress = pyqtSignal(int)           # 0..100
    log = pyqtSignal(str)                # raw stderr lines
    finished_ok = pyqtSignal(list)       # list[str] — sorted output paths
    failed = pyqtSignal(str)             # human-readable error
    cancelled = pyqtSignal()             # user-initiated cancel completed

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._proc: QProcess | None = None
        self._out_dir: Path | None = None
        self._expected_frames: int | None = None
        self._stderr_tail: bytearray = bytearray()
        self._cancelled: bool = False

    @property
    def is_running(self) -> bool:
        return self._proc is not None

    def extract(
        self,
        video_path: str,
        out_dir: str,
        decimation: int = 1,
        start_sec: float | None = None,
        end_sec: float | None = None,
    ) -> None:
        if self.is_running:
            self.failed.emit("Extraction already in progress.")
            return
        self._out_dir = Path(out_dir)
        self._out_dir.mkdir(parents=True, exist_ok=True)
        self._stderr_tail = bytearray()
        self._cancelled = False

        total = probe_frame_count(video_path)
        if total and decimation > 1:
            self._expected_frames = max(1, total // decimation)
        else:
            self._expected_frames = total

        args = build_ffmpeg_args(
            video_path, out_dir, decimation=decimation,
            start_sec=start_sec, end_sec=end_sec,
        )
        self._proc = QProcess(self)
        self._proc.setProgram("ffmpeg")
        self._proc.setArguments(args)
        self._proc.readyReadStandardError.connect(self._on_stderr)
        self._proc.finished.connect(self._on_finished)
        self._proc.errorOccurred.connect(self._on_proc_error)
        self.progress.emit(0)
        self._proc.start()

    def cancel(self) -> None:
        if self._proc is not None:
            self._cancelled = True
            self._proc.kill()

    def _on_stderr(self) -> None:
        if self._proc is None:
            return
        data = bytes(self._proc.readAllStandardError())
        if not data:
            return
        self._stderr_tail.extend(data)
        # keep last 4 KiB only for error reporting
        if len(self._stderr_tail) > 4096:
            del self._stderr_tail[:-4096]
        self.log.emit(data.decode(errors="replace"))
        matches = _PROGRESS_RE.findall(data)
        if matches and self._expected_frames:
            latest = int(matches[-1])
            pct = min(100, int(latest * 100 / max(1, self._expected_frames)))
            self.progress.emit(pct)

    def _on_finished(self, exit_code: int, _exit_status) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        if self._cancelled:
            self._cancelled = False
            self.cancelled.emit()
            return
        if exit_code != 0:
            tail = bytes(self._stderr_tail).decode(errors="replace")
            self.failed.emit(f"ffmpeg exited with code {exit_code}:\n{tail}")
            return
        assert self._out_dir is not None
        frames = sorted(self._out_dir.glob("frame_*.tif"))
        if not frames:
            self.failed.emit("ffmpeg produced no frames.")
            return
        self.progress.emit(100)
        self.finished_ok.emit([str(p) for p in frames])

    def _on_proc_error(self, _err) -> None:
        if self._proc is None:
            return
        if self._cancelled:
            # _on_finished will handle the cancelled emission shortly.
            return
        err_str = self._proc.errorString()
        self.failed.emit(f"ffmpeg could not run: {err_str}")
