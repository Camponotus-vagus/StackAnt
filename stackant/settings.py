"""Thin QSettings wrapper — one key per persisted value.

All loads use QSettings' `type=` coercion so a corrupted or
hand-edited config falls back to the default rather than crashing.
"""
from __future__ import annotations

from PyQt6.QtCore import QByteArray, QSettings

from . import config


def _s() -> QSettings:
    return QSettings(config.ORG_NAME, config.APP_NAME)


# ---- window geometry --------------------------------------------------

def save_window_state(geometry: QByteArray, state: QByteArray) -> None:
    s = _s()
    s.setValue("window/geometry", geometry)
    s.setValue("window/state", state)


def load_window_state() -> tuple[QByteArray, QByteArray]:
    s = _s()
    geom = s.value("window/geometry", QByteArray(), type=QByteArray)
    state = s.value("window/state", QByteArray(), type=QByteArray)
    return geom, state


# ---- export defaults --------------------------------------------------

def save_export_defaults(folder: str, quality: int, tiff: bool, jpeg: bool) -> None:
    s = _s()
    s.setValue("export/folder", folder)
    s.setValue("export/quality", int(quality))
    s.setValue("export/tiff", bool(tiff))
    s.setValue("export/jpeg", bool(jpeg))


def load_export_defaults() -> dict:
    s = _s()
    return {
        "folder": s.value("export/folder", "", type=str),
        "quality": s.value("export/quality", 95, type=int),
        "tiff": s.value("export/tiff", True, type=bool),
        "jpeg": s.value("export/jpeg", True, type=bool),
    }


# ---- stacker advanced params -----------------------------------------
#
# `extra_cli` here is the *raw* text the user typed in the Extra CLI
# field. The `--no-opencl` flag is persisted separately through
# `no_opencl`. At runtime they get combined in StackControls.params().

def save_stack_params(
    consistency: int,
    denoise: bool,
    sharp_strength: int,
    halo_radius: int | None,
    extra_cli: str,
    no_opencl: bool,
) -> None:
    s = _s()
    s.setValue("stack/consistency", int(consistency))
    s.setValue("stack/denoise", bool(denoise))
    s.setValue("stack/sharp_strength", int(sharp_strength))
    s.setValue("stack/halo_radius", -1 if halo_radius is None else int(halo_radius))
    s.setValue("stack/extra_cli", extra_cli or "")
    s.setValue("stack/no_opencl", bool(no_opencl))


def load_stack_params() -> dict:
    s = _s()
    halo = s.value("stack/halo_radius", -1, type=int)
    return {
        "consistency": s.value("stack/consistency", config.FOCUS_STACK_CONSISTENCY, type=int),
        "denoise": s.value("stack/denoise", config.FOCUS_STACK_DENOISE, type=bool),
        "sharp_strength": s.value(
            "stack/sharp_strength", config.FOCUS_STACK_SHARP_STRENGTH, type=int
        ),
        "halo_radius": None if halo < 0 else halo,
        "extra_cli": s.value("stack/extra_cli", "", type=str),
        "no_opencl": s.value("stack/no_opencl", False, type=bool),
    }
