"""focus-stack wrapper as a non-blocking QProcess."""
from __future__ import annotations

import re
import shlex
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, pyqtSignal


# focus-stack prints progress in square-bracketed "[ N/M]" prefixes for every
# per-frame task (e.g. "[ 40/214] Grayscale aligned_frame_00023.tif").
_PROGRESS_RE = re.compile(rb"\[\s*(\d+)\s*/\s*(\d+)\s*\]")

# focus-stack's GPU wavelet kernel (Task_Wavelet_OpenCL / decompose_vertical)
# fails on macOS' deprecated OpenCL stack with "can't create cl_mem handle ...".
# --no-opencl routes the same step through the CPU Task_Wavelet instead.
_OPENCL_FAILURE_RE = re.compile(r"opencl|cl_mem|CL_OUT_OF_RESOURCES", re.IGNORECASE)
_OPENCL_MARKER = "[OpenCL kernel failure]"


def is_opencl_failure(text: str) -> bool:
    """True if a focus-stack log mentions an OpenCL/GPU kernel failure."""
    return bool(_OPENCL_FAILURE_RE.search(text))


def should_retry_without_opencl(
    msg: str,
    *,
    compare_mode: bool,
    already_retried: bool,
    extra_cli: str,
) -> bool:
    """Decide whether a failed focus-stack run should be retried on the CPU.

    Retry exactly once, only for a genuine OpenCL failure, and never when the
    user is comparing backends or has already disabled OpenCL.
    """
    if compare_mode or already_retried:
        return False
    if "--no-opencl" in extra_cli:
        return False
    return is_opencl_failure(msg)


def build_focus_stack_args(
    input_frames: list[str],
    output_path: str,
    *,
    consistency: int = 2,
    denoise: bool = True,
    sharp_strength: int = 1,
    halo_radius: int | None = None,
    extra_cli: str = "",
) -> list[str]:
    """Build focus-stack CLI arguments (without the 'focus-stack' program name).

    All flags use the `--key=value` form; positional frame paths come last.
    """
    args: list[str] = [
        f"--output={output_path}",
        f"--consistency={int(consistency)}",
        f"--denoise={1 if denoise else 0}",
        f"--sharp-strength={int(sharp_strength)}",
    ]
    if halo_radius is not None:
        args.append(f"--halo-radius={int(halo_radius)}")
    if extra_cli.strip():
        args.extend(shlex.split(extra_cli))
    args.extend(input_frames)
    return args


class FocusStacker(QObject):
    progress = pyqtSignal(int)           # 0..100, from "Step N/M" parsing
    log = pyqtSignal(str)                # streamed stdout/stderr
    command_ready = pyqtSignal(str)      # the full command line before launch
    finished_ok = pyqtSignal(str)        # output path
    failed = pyqtSignal(str)             # human-readable error
    cancelled = pyqtSignal()             # user-initiated cancel completed

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._proc: QProcess | None = None
        self._output_path: str | None = None
        self._log_tail = bytearray()
        self._cancelled: bool = False

    @property
    def is_running(self) -> bool:
        return self._proc is not None

    def stack(
        self,
        input_frames: list[str],
        output_path: str,
        *,
        consistency: int = 2,
        denoise: bool = True,
        sharp_strength: int = 1,
        halo_radius: int | None = None,
        extra_cli: str = "",
    ) -> None:
        if self.is_running:
            self.failed.emit("A stack is already running.")
            return
        if not input_frames:
            self.failed.emit("No frames to stack.")
            return
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        self._cancelled = False

        args = build_focus_stack_args(
            input_frames, output_path,
            consistency=consistency, denoise=denoise,
            sharp_strength=sharp_strength, halo_radius=halo_radius,
            extra_cli=extra_cli,
        )
        self._output_path = output_path
        self._log_tail = bytearray()
        self.command_ready.emit("focus-stack " + " ".join(shlex.quote(a) for a in args))

        self._proc = QProcess(self)
        self._proc.setProgram("focus-stack")
        self._proc.setArguments(args)
        self._proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._proc.readyReadStandardOutput.connect(self._on_output)
        self._proc.finished.connect(self._on_finished)
        self._proc.errorOccurred.connect(self._on_proc_error)
        self.progress.emit(0)
        self._proc.start()

    def cancel(self) -> None:
        if self._proc is not None:
            self._cancelled = True
            self._proc.kill()

    def _on_output(self) -> None:
        if self._proc is None:
            return
        data = bytes(self._proc.readAllStandardOutput())
        if not data:
            return
        self._log_tail.extend(data)
        if len(self._log_tail) > 8192:
            del self._log_tail[:-8192]
        self.log.emit(data.decode(errors="replace"))
        m = _PROGRESS_RE.findall(data)
        if m:
            cur, total = int(m[-1][0]), int(m[-1][1])
            if total > 0:
                self.progress.emit(min(100, int(cur * 100 / total)))

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
            full = bytes(self._log_tail).decode(errors="replace")
            tail = full[-800:]
            # The OpenCL error can scroll past the 800-byte tail behind a flood
            # of repeated progress lines; surface a stable marker so the caller
            # can still detect it and retry on the CPU.
            if is_opencl_failure(full) and not is_opencl_failure(tail):
                tail = f"{_OPENCL_MARKER}\n{tail}"
            self.failed.emit(f"focus-stack exited with code {exit_code}:\n{tail}")
            return
        if self._output_path and Path(self._output_path).is_file():
            self.progress.emit(100)
            self.finished_ok.emit(self._output_path)
        else:
            self.failed.emit("focus-stack reported success but no output file was found.")

    def _on_proc_error(self, _err) -> None:
        if self._proc is None:
            return
        if self._cancelled:
            return
        msg = self._proc.errorString()
        self.failed.emit(f"focus-stack could not run: {msg}")
