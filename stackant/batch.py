"""Pure helpers and value types for batch video processing (no Qt)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}


def discover_videos(folder: str) -> list[str]:
    """Sorted absolute paths of video files directly in `folder` (non-recursive)."""
    root = Path(folder)
    if not root.is_dir():
        return []
    found = [
        str(p)
        for p in root.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
    ]
    return sorted(found)


def output_targets(video_path: str, export: dict) -> list[Path]:
    """Destination files next to the source video for the selected formats."""
    src = Path(video_path)
    stem = f"{src.stem}_stacked"
    targets: list[Path] = []
    if export.get("tiff"):
        targets.append(src.parent / f"{stem}.tif")
    if export.get("jpeg"):
        targets.append(src.parent / f"{stem}.jpg")
    return targets


def is_already_done(video_path: str, export: dict) -> bool:
    """True iff every selected output already exists (drives skip-existing)."""
    targets = output_targets(video_path, export)
    return bool(targets) and all(t.exists() for t in targets)


@dataclass(frozen=True)
class BatchSettings:
    method: str                 # "pyramid" | "focus-stack" | "auto"
    extract_decimation: int     # "keep every Nth frame"
    cap: int | None             # filter decimation cap; None -> per-video suggestion
    focus_params: dict          # StackControls.params()
    pyramid_params: dict        # StackControls.pyramid_params()
    export: dict                # {"tiff": bool, "jpeg": bool, "quality": int}


@dataclass
class BatchItem:
    video_path: str
    status: str = "pending"     # pending|running|done|failed|skipped|cancelled
    step: str = ""
    message: str = ""
    output_paths: list[str] = field(default_factory=list)
