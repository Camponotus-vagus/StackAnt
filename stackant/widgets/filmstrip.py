"""Horizontal filmstrip of frame thumbnails."""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem

from ..thumbnails import make_thumbnail

_THUMB_PX = 110


class Filmstrip(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setFlow(QListWidget.Flow.LeftToRight)
        self.setWrapping(False)
        self.setIconSize(QSize(_THUMB_PX, _THUMB_PX))
        self.setGridSize(QSize(_THUMB_PX + 12, _THUMB_PX + 28))
        self.setMovement(QListWidget.Movement.Static)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSpacing(2)
        self.setUniformItemSizes(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def load_frames(self, paths: list[str]) -> None:
        self.clear()
        for i, p in enumerate(paths):
            try:
                pm = make_thumbnail(p, _THUMB_PX)
            except Exception:
                continue
            item = QListWidgetItem(QIcon(pm), f"{i + 1}")
            item.setData(Qt.ItemDataRole.UserRole, p)
            self.addItem(item)
        if self.count():
            self.setCurrentRow(0)

    def frame_paths(self) -> list[str]:
        return [
            self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())
        ]
