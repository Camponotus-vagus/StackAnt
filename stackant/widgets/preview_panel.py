"""Right-side preview panel: full image + click-drag crop + 1:1 detail view."""
from __future__ import annotations

from PyQt6.QtCore import QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRubberBand,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import config
from ..preview import load_pixmap, scaled_for_preview


class _PreviewLabel(QLabel):
    """QLabel that lets the user drag a rectangular crop rect over its pixmap."""

    crop_drawn = pyqtSignal(QRect)  # in label (= scaled-pixmap) coordinates
    crop_cleared = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("background-color: #2b2b2b;")
        self._origin = None
        self._rubber = QRubberBand(QRubberBand.Shape.Rectangle, self)

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self.pixmap():
            self._origin = e.pos()
            self._rubber.setGeometry(QRect(self._origin, QSize()))
            self._rubber.show()

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if self._origin is not None:
            self._rubber.setGeometry(QRect(self._origin, e.pos()).normalized())

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if self._origin is not None and e.button() == Qt.MouseButton.LeftButton:
            rect = QRect(self._origin, e.pos()).normalized()
            self._origin = None
            if rect.width() < 6 or rect.height() < 6:
                self._rubber.hide()
                self.crop_cleared.emit()
            else:
                rect = rect.intersected(self.rect())
                self.crop_drawn.emit(rect)

    def clear_rubber(self) -> None:
        self._rubber.hide()


class PreviewPanel(QWidget):
    restack_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stacked_path: str | None = None
        self._input_path: str | None = None
        self._current_mode: str = "stacked"  # or "input"

        self._full_pixmap: QPixmap | None = None   # full-res currently displayed source
        self._scale: float = 1.0

        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        header_row = QHBoxLayout()
        self.lbl_mode = QLabel("Preview")
        f = self.lbl_mode.font()
        f.setBold(True)
        self.lbl_mode.setFont(f)
        header_row.addWidget(self.lbl_mode)
        header_row.addStretch(1)
        self.btn_toggle = QPushButton("Show input frame")
        self.btn_toggle.clicked.connect(self._toggle_mode)
        self.btn_toggle.setEnabled(False)
        header_row.addWidget(self.btn_toggle)
        root.addLayout(header_row)

        self.preview_label = _PreviewLabel()
        self.preview_label.crop_drawn.connect(self._on_crop_drawn)
        self.preview_label.crop_cleared.connect(self._on_crop_cleared)
        preview_container = QFrame()
        preview_container.setFrameShape(QFrame.Shape.StyledPanel)
        pc = QVBoxLayout(preview_container)
        pc.setContentsMargins(4, 4, 4, 4)
        pc.addWidget(self.preview_label, alignment=Qt.AlignmentFlag.AlignCenter)
        pc.addStretch(1)
        root.addWidget(preview_container, stretch=3)

        detail_header = QHBoxLayout()
        detail_header.addWidget(QLabel("1:1 detail:"))
        detail_header.addStretch(1)
        self.btn_reset_crop = QPushButton("Reset crop")
        self.btn_reset_crop.clicked.connect(self._reset_crop)
        self.btn_reset_crop.setEnabled(False)
        detail_header.addWidget(self.btn_reset_crop)
        root.addLayout(detail_header)

        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(False)
        self.detail_label = QLabel()
        self.detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_label.setStyleSheet("background-color: #1e1e1e; color: gray;")
        self.detail_label.setText("Draw a rectangle on the preview above to see it 1:1.")
        self.detail_scroll.setWidget(self.detail_label)
        root.addWidget(self.detail_scroll, stretch=2)

        bottom_row = QHBoxLayout()
        self.btn_restack = QPushButton("Re-stack with current params")
        self.btn_restack.clicked.connect(self.restack_requested.emit)
        self.btn_restack.setEnabled(False)
        bottom_row.addWidget(self.btn_restack)
        bottom_row.addStretch(1)
        root.addLayout(bottom_row)

    # ---- public API ------------------------------------------------------

    def show_stacked(self, path: str) -> None:
        self._stacked_path = path
        self._current_mode = "stacked"
        self._render_current()
        self._update_toggle_button()
        self.btn_restack.setEnabled(True)

    def set_input_reference(self, path: str | None) -> None:
        """Set which input frame the compare toggle should use."""
        self._input_path = path
        self._update_toggle_button()
        if self._current_mode == "input":
            # Refresh shown image if user already in compare mode
            self._render_current()

    def clear(self) -> None:
        self._stacked_path = None
        self._input_path = None
        self._current_mode = "stacked"
        self._full_pixmap = None
        self._scale = 1.0
        self.preview_label.clear()
        self.preview_label.clear_rubber()
        self.detail_label.clear()
        self.detail_label.setText("Draw a rectangle on the preview above to see it 1:1.")
        self.btn_toggle.setEnabled(False)
        self.btn_restack.setEnabled(False)
        self.btn_reset_crop.setEnabled(False)

    # ---- internal --------------------------------------------------------

    def _current_path(self) -> str | None:
        return self._stacked_path if self._current_mode == "stacked" else self._input_path

    def _update_toggle_button(self) -> None:
        has_input = self._input_path is not None
        has_stacked = self._stacked_path is not None
        self.btn_toggle.setEnabled(has_input and has_stacked)
        if self._current_mode == "stacked":
            self.btn_toggle.setText("Show input frame")
            self.lbl_mode.setText("Preview — stacked result")
        else:
            self.btn_toggle.setText("Show stacked result")
            self.lbl_mode.setText("Preview — input frame")

    def _toggle_mode(self) -> None:
        if self._current_mode == "stacked" and self._input_path:
            self._current_mode = "input"
        else:
            self._current_mode = "stacked"
        self._render_current()
        self._update_toggle_button()

    def _render_current(self) -> None:
        path = self._current_path()
        if not path:
            return
        try:
            pm = load_pixmap(path)
        except Exception as exc:  # image decode failure — show placeholder text
            self.preview_label.setText(f"(preview error: {exc})")
            self._full_pixmap = None
            return
        self._full_pixmap = pm
        scaled, scale = scaled_for_preview(pm, config.PREVIEW_MAX_PX)
        self._scale = scale
        self.preview_label.setPixmap(scaled)
        self.preview_label.setFixedSize(scaled.size())
        self.preview_label.clear_rubber()
        self._clear_detail()

    def _on_crop_drawn(self, rect: QRect) -> None:
        if self._full_pixmap is None:
            return
        inv = 1.0 / max(self._scale, 1e-6)
        full_rect = QRect(
            int(rect.x() * inv),
            int(rect.y() * inv),
            int(rect.width() * inv),
            int(rect.height() * inv),
        ).intersected(self._full_pixmap.rect())
        if full_rect.isEmpty():
            return
        crop = self._full_pixmap.copy(full_rect)
        self.detail_label.setPixmap(crop)
        self.detail_label.setFixedSize(crop.size())
        self.btn_reset_crop.setEnabled(True)

    def _on_crop_cleared(self) -> None:
        self._clear_detail()

    def _clear_detail(self) -> None:
        self.detail_label.clear()
        self.detail_label.setText("Draw a rectangle on the preview above to see it 1:1.")
        self.detail_label.setFixedSize(self.detail_scroll.viewport().size())
        self.btn_reset_crop.setEnabled(False)

    def _reset_crop(self) -> None:
        self.preview_label.clear_rubber()
        self._clear_detail()
