"""Horizontal filmstrip of frame thumbnails with kept/rejected visual state."""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem

from ..thumbnails import make_rejected_pixmap, make_thumbnail

_THUMB_PX = 110
_PATH_ROLE = Qt.ItemDataRole.UserRole
_INDEX_ROLE = Qt.ItemDataRole.UserRole + 1


class Filmstrip(QListWidget):
    toggle_requested = pyqtSignal(int)  # user wants to flip frame at this index

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

        self._base_pixmaps: list = []
        self._rejected_pixmaps: list = []

        self.itemDoubleClicked.connect(self._on_item_double_clicked)

    def load_frames(self, paths: list[str]) -> None:
        self.clear()
        self._base_pixmaps = []
        self._rejected_pixmaps = []
        for i, p in enumerate(paths):
            try:
                pm = make_thumbnail(p, _THUMB_PX)
            except Exception:
                continue
            self._base_pixmaps.append(pm)
            self._rejected_pixmaps.append(make_rejected_pixmap(pm))
            item = QListWidgetItem(QIcon(pm), f"{i + 1}")
            item.setData(_PATH_ROLE, p)
            item.setData(_INDEX_ROLE, i)
            self.addItem(item)
        if self.count():
            self.setCurrentRow(0)

    def apply_mask(self, mask: list[bool]) -> None:
        for i in range(min(self.count(), len(mask))):
            kept = mask[i]
            pm = self._base_pixmaps[i] if kept else self._rejected_pixmaps[i]
            self.item(i).setIcon(QIcon(pm))

    def frame_paths(self) -> list[str]:
        return [self.item(i).data(_PATH_ROLE) for i in range(self.count())]

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        idx = item.data(_INDEX_ROLE)
        if idx is not None:
            self.toggle_requested.emit(int(idx))
