"""Method-selection heuristic for the Auto stacker mode.

No published rule exists for selecting a focus-stacking method per
image (Helicon, Zerene, and the photomacrography community all
recommend trying both). This module exposes a documented heuristic
based on frame count and resolution — it is a reasonable default,
not a claim of correctness. For quality-critical work users should
reach for the Compare button.
"""
from __future__ import annotations

_MAX_FRAMES_FOR_PYRAMID = 50
_MAX_LONGEST_EDGE_FOR_PYRAMID = 2048


def choose_method(n_frames: int, width: int, height: int) -> str:
    """Return "pyramid" or "focus-stack" for the current input.

    Rule: pyramid when the stack is small (<=50 kept frames) AND the
    longest edge is <=2048 px. Otherwise focus-stack, whose GPU path
    scales better to deeper / higher-resolution stacks.
    """
    if n_frames <= 0:
        raise ValueError("n_frames must be positive")
    small_stack = n_frames <= _MAX_FRAMES_FOR_PYRAMID
    small_edge = max(width, height) <= _MAX_LONGEST_EDGE_FOR_PYRAMID
    return "pyramid" if (small_stack and small_edge) else "focus-stack"
