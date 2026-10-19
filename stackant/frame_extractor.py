"""ffmpeg-based frame extraction as a non-blocking QProcess."""
from __future__ import annotations

import json
import os
import re
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
    """Build ffmpeg CLI arguments (the 'ffmpeg' program name is not included).

    The output pattern is relative: the caller runs ffmpeg with `out_dir` as its
    working directory, so a '%' in the directory name cannot corrupt the pattern.
    """
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
        FRAME_PATTERN,
    ]
    return args


def build_ffprobe_args(path: str) -> list[str]:
    """ffprobe arguments reading container/stream headers only (no packet scan)."""
    return [
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=nb_frames,duration,avg_frame_rate:format=duration",
        "-of", "json",
        "-i", path,
    ]


def _positive_float(value: object) -> float | None:
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return f if f > 0 and f != float("inf") else None


def _parse_rate(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    num, _, den = value.partition("/")
    n = _positive_float(num)
    d = _positive_float(den) if den else 1.0
    return n / d if n and d else None


def parse_frame_count(probe_json: str) -> int | None:
    """Frame count from `build_ffprobe_args` output; None if it cannot be derived.

    Prefers the stream's nb_frames, falling back to duration x avg_frame_rate.
    """
    try:
        data = json.loads(probe_json)
        stream = (data.get("streams") or [{}])[0]
        fmt = data.get("format") or {}
    except (ValueError, AttributeError, IndexError, TypeError):
        return None
    nb = _positive_float(stream.get("nb_frames"))
    if nb:
        return int(nb)
    duration = _positive_float(stream.get("duration")) or _positive_float(fmt.get("duration"))
    rate = _parse_rate(stream.get("avg_frame_rate"))
    if duration and rate:
        return max(1, round(duration * rate))
    return None


def frame_sort_key(path: Path) -> int:
    m = re.search(r"(\d+)", path.stem)
    return int(m.group(1)) if m else -1


class FrameExtractor(QObject):
    progress = pyqtSignal(int)           # 0..100
    log = pyqtSignal(str)                # raw stderr lines
    finished_ok = pyqtSignal(list)       # list[str] — sorted output paths
    failed = pyqtSignal(str)             # human-readable error
    cancelled = pyqtSignal()             # user-initiated cancel completed

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._proc: QProcess | None = None
        self._probe: QProcess | None = None
        self._decimation: int = 1
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
        try:
            self._out_dir.mkdir(parents=True, exist_ok=True)
            for stale in self._out_dir.glob("frame_*.tif"):
                stale.unlink()
        except OSError as exc:
            self.failed.emit(f"Cannot prepare frame folder: {exc}")
            return
        self._stderr_tail = bytearray()
        self._cancelled = False
        self._expected_frames = None
        self._decimation = max(1, decimation)
        video_path = os.path.abspath(video_path)

        args = build_ffmpeg_args(
            video_path, out_dir, decimation=decimation,
            start_sec=start_sec, end_sec=end_sec,
        )
        self._proc = QProcess(self)
        self._proc.setProgram("ffmpeg")
        self._proc.setArguments(args)
        self._proc.setWorkingDirectory(str(self._out_dir))
        self._proc.readyReadStandardError.connect(self._on_stderr)
        self._proc.finished.connect(self._on_finished)
        self._proc.errorOccurred.connect(self._on_proc_error)
        self.progress.emit(0)
        self._start_probe(video_path)
        self._proc.start()

    def cancel(self) -> None:
        self._dispose_probe()
        if self._proc is not None:
            self._cancelled = True
            self._proc.kill()

    def shutdown(self, timeout_ms: int = 2000) -> bool:
        """Kill any running process and wait for it; True once nothing runs."""
        proc = self._proc
        self.cancel()
        if proc is not None:
            proc.waitForFinished(timeout_ms)
        return self._proc is None

    def _start_probe(self, video_path: str) -> None:
        probe = QProcess(self)
        probe.setProgram("ffprobe")
        probe.setArguments(build_ffprobe_args(video_path))
        probe.finished.connect(self._on_probe_finished)
        probe.errorOccurred.connect(self._on_probe_error)
        self._probe = probe
        probe.start()

    def _dispose_probe(self) -> None:
        probe = self._probe
        self._probe = None
        if probe is None:
            return
        probe.finished.disconnect()
        probe.errorOccurred.disconnect()
        if probe.state() != QProcess.ProcessState.NotRunning:
            probe.kill()
        probe.deleteLater()

    def _on_probe_finished(self, exit_code: int, exit_status) -> None:
        probe = self._probe
        if probe is None:
            return
        out = bytes(probe.readAllStandardOutput()).decode(errors="replace")
        self._dispose_probe()
        if exit_code != 0 or exit_status != QProcess.ExitStatus.NormalExit:
            return
        total = parse_frame_count(out)
        if total and self._decimation > 1:
            total = max(1, total // self._decimation)
        self._expected_frames = total

    def _on_probe_error(self, err) -> None:
        if err == QProcess.ProcessError.FailedToStart:
            self._dispose_probe()

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

    def _on_finished(self, exit_code: int, exit_status) -> None:
        proc = self._proc
        self._proc = None
        self._dispose_probe()
        if proc is None:
            return
        if self._cancelled:
            self._cancelled = False
            self.cancelled.emit()
            return
        if exit_status != QProcess.ExitStatus.NormalExit:
            tail = bytes(self._stderr_tail).decode(errors="replace")[-800:]
            self.failed.emit(f"ffmpeg crashed:\n{tail}")
            return
        if exit_code != 0:
            tail = bytes(self._stderr_tail).decode(errors="replace")
            self.failed.emit(f"ffmpeg exited with code {exit_code}:\n{tail}")
            return
        assert self._out_dir is not None
        frames = sorted(self._out_dir.glob("frame_*.tif"), key=frame_sort_key)
        if not frames:
            self.failed.emit("ffmpeg produced no frames.")
            return
        self.progress.emit(100)
        self.finished_ok.emit([str(p) for p in frames])

    def _on_proc_error(self, err) -> None:
        # Only FailedToStart is terminal without a following `finished`; a
        # crash also emits `finished`, which reports it.
        if self._proc is None or err != QProcess.ProcessError.FailedToStart:
            return
        proc = self._proc
        self._proc = None
        self._dispose_probe()
        self._cancelled = False
        msg = proc.errorString()
        proc.deleteLater()
        self.failed.emit(f"ffmpeg could not run: {msg}")
