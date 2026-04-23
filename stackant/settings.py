"""Thin QSettings wrapper — one key per persisted value."""
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


def load_window_state() -> tuple[QByteArray | None, QByteArray | None]:
    s = _s()
    return s.value("window/geometry"), s.value("window/state")


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
        "quality": int(s.value("export/quality", 95)),
        "tiff": s.value("export/tiff", True, type=bool),
        "jpeg": s.value("export/jpeg", True, type=bool),
    }


# ---- stacker advanced params -----------------------------------------

def save_stack_params(params: dict) -> None:
    s = _s()
    s.setValue("stack/consistency", int(params.get("consistency", config.FOCUS_STACK_CONSISTENCY)))
    s.setValue("stack/denoise", bool(params.get("denoise", config.FOCUS_STACK_DENOISE)))
    s.setValue("stack/sharp_strength", int(params.get("sharp_strength", config.FOCUS_STACK_SHARP_STRENGTH)))
    halo = params.get("halo_radius")
    s.setValue("stack/halo_radius", -1 if halo is None else int(halo))
    s.setValue("stack/extra_cli", params.get("extra_cli", "") or "")


def load_stack_params() -> dict:
    s = _s()
    halo = int(s.value("stack/halo_radius", -1))
    return {
        "consistency": int(s.value("stack/consistency", config.FOCUS_STACK_CONSISTENCY)),
        "denoise": s.value("stack/denoise", config.FOCUS_STACK_DENOISE, type=bool),
        "sharp_strength": int(s.value("stack/sharp_strength", config.FOCUS_STACK_SHARP_STRENGTH)),
        "halo_radius": None if halo < 0 else halo,
        "extra_cli": s.value("stack/extra_cli", "", type=str),
    }
