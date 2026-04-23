"""Laplacian-variance blur scoring, threshold filtering, and decimation.

Design note on the threshold:
    High Laplacian variance → sharp frame; low variance → motion-blurred
    transition frame in a focus pull. The auto-threshold is a floor computed
    as `mean - k * std` (k=1 by default): frames whose sharpness is more than
    one standard deviation below the mean are flagged as too blurry. Users
    can override with a slider.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np


@dataclass(frozen=True)
class FrameScore:
    index: int
    path: str
    laplacian_var: float


def laplacian_variance(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def score_image(path: str, max_edge: int = 512) -> float:
    """Load an image, downscale the long edge to `max_edge`, return Laplacian variance.

    Downscaling keeps scoring fast for 4K-ish frames while preserving the
    relative sharpness ordering that matters for filtering.
    """
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return 0.0
    h, w = img.shape
    longest = max(h, w)
    if longest > max_edge:
        scale = max_edge / longest
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return laplacian_variance(img)


def score_frames(paths: list[str]) -> list[FrameScore]:
    return [FrameScore(i, p, score_image(p)) for i, p in enumerate(paths)]


def auto_threshold(scores: list[float], k: float = 1.0) -> float:
    """Floor threshold: mean - k * std. Frames at or below this are too blurry."""
    if not scores:
        return 0.0
    arr = np.asarray(scores, dtype=np.float64)
    return float(arr.mean() - k * arr.std())


def even_subsample(indices: list[int], target: int) -> list[int]:
    """Pick `target` indices evenly spaced from `indices`. No duplicates."""
    n = len(indices)
    if n == 0 or target <= 0:
        return []
    if n <= target:
        return list(indices)
    picks = np.linspace(0, n - 1, target).round().astype(int)
    return sorted({indices[int(i)] for i in picks})


def suggested_decimation_target(num_frames: int, lo: int = 50, hi: int = 100) -> int:
    """Target count for the second-stage decimation.

    - Fewer than `lo` frames: keep all (no decimation needed).
    - Between lo and hi: keep all.
    - Above hi: aim for 75 (middle of lo..hi).
    """
    if num_frames <= hi:
        return num_frames
    return (lo + hi) // 2


@dataclass
class FilterState:
    """Mutable filter state: threshold + manual per-frame overrides + optional decimation cap.

    `manual_overrides[i] = True` forces-include frame i, `False` forces-exclude.
    Manual overrides win over the threshold. Decimation is applied last and
    can only drop auto-kept frames — forced-include frames are always kept.
    """
    scores: list[float]
    threshold: float
    decimation_target: int | None = None
    manual_overrides: dict[int, bool] = field(default_factory=dict)

    @property
    def n(self) -> int:
        return len(self.scores)

    def kept_mask(self) -> list[bool]:
        n = self.n
        mask = [s >= self.threshold for s in self.scores]
        for i, forced in self.manual_overrides.items():
            if 0 <= i < n:
                mask[i] = forced

        if self.decimation_target and self.decimation_target > 0:
            forced_in = {i for i, v in self.manual_overrides.items() if v}
            forced_out = {i for i, v in self.manual_overrides.items() if not v}
            kept_auto = [
                i for i, m in enumerate(mask)
                if m and i not in forced_in and i not in forced_out
            ]
            budget = max(0, self.decimation_target - len(forced_in))
            if len(kept_auto) > budget:
                chosen = set(even_subsample(kept_auto, budget))
                mask = [
                    (i in forced_in) or (m and (i in chosen))
                    for i, m in enumerate(mask)
                ]
        return mask

    def counts(self) -> tuple[int, int]:
        mask = self.kept_mask()
        return sum(mask), len(mask)
