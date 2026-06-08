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
        self._stacked_paths: dict[str, str | None] = {
            "pyramid": None, "focus-stack": None,
        }
        self._compare_view: str | None = None  # "pyramid" or "focus-stack" while comparing
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
        self.btn_compare_view = QPushButton()
        self.btn_compare_view.setVisible(False)
        self.btn_compare_view.clicked.connect(self._cycle_compare_view)
        self.btn_compare_view.setToolTip(
            "Cycle between the two stacked outputs from Compare mode."
        )
        header_row.addWidget(self.btn_compare_view)
        root.addLayout(header_row)

        self.preview_label = _PreviewLabel()
        self.preview_label.crop_drawn.connect(self._on_crop_drawn)
        self.preview_label.crop_cleared.connect(self._on_crop_cleared)
        preview_container = QFrame()
        preview_container.setFrameShape(QFrame.Shape.StyledPanel)
        preview_container.setObjectName("previewContainer")
        preview_container.setStyleSheet(
            "QFrame#previewContainer { background-color: #2b2b2b; border: 1px solid #444; }"
        )
        pc = QVBoxLayout(preview_container)
        pc.setContentsMargins(4, 4, 4, 4)
        pc.addWidget(self.preview_label, alignment=Qt.AlignmentFlag.AlignCenter)
        pc.addStretch(1)
        root.addWidget(preview_container, stretch=3)

        detail_header = QHBoxLayout()
        lbl_detail = QLabel("Crop detail:")
        lbl_detail.setToolTip(
            "Shows the selected rectangle at 1:1 pixel scale when it fits, "
            "otherwise scales to fit the pane while preserving aspect."
        )
        detail_header.addWidget(lbl_detail)
        detail_header.addStretch(1)
        self.btn_reset_crop = QPushButton("Reset crop")
        self.btn_reset_crop.clicked.connect(self._reset_crop)
        self.btn_reset_crop.setEnabled(False)
        detail_header.addWidget(self.btn_reset_crop)
        root.addLayout(detail_header)

        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(False)
        self.detail_scroll.setStyleSheet(
            "QScrollArea { background-color: #1e1e1e; border: 1px solid #444; }"
            "QScrollArea > QWidget > QWidget { background-color: #1e1e1e; }"
        )
        self.detail_label = QLabel()
        self.detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_label.setStyleSheet("background: transparent; color: gray;")
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
        self._stacked_paths = {"pyramid": None, "focus-stack": None}
        self._compare_view = None
        self.btn_compare_view.setVisible(False)
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
        viewport = self.detail_scroll.viewport().size()
        # Show 1:1 when it fits; otherwise scale to fit aspect so the whole
        # crop is visible without forcing the user to scroll.
        if crop.width() <= viewport.width() and crop.height() <= viewport.height():
            display = crop
        else:
            display = crop.scaled(
                viewport,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self.detail_label.setPixmap(display)
        self.detail_label.setFixedSize(display.size())
        self.btn_reset_crop.setEnabled(True)

    def _on_crop_cleared(self) -> None:
        self._clear_detail()

    def _clear_detail(self) -> None:
        self.detail_label.clear()
        self.detail_label.setText(
            "Draw a rectangle on the preview above to inspect it."
        )
        self.detail_label.setFixedSize(self.detail_scroll.viewport().size())
        self.btn_reset_crop.setEnabled(False)

    def _reset_crop(self) -> None:
        self.preview_label.clear_rubber()
        self._clear_detail()

    def set_compare_outputs(
        self,
        pyramid_path: str | None,
        focus_stack_path: str | None,
    ) -> None:
        """Enter compare mode with one or both stacked outputs."""
        self._stacked_paths["pyramid"] = pyramid_path
        self._stacked_paths["focus-stack"] = focus_stack_path
        first = "pyramid" if pyramid_path else "focus-stack"
        self._compare_view = first
        self._show_compare(first)
        has_both = bool(pyramid_path and focus_stack_path)
        self.btn_compare_view.setVisible(has_both)
        self._update_compare_button_label()

    def _show_compare(self, which: str) -> None:
        path = self._stacked_paths[which]
        if path:
            self.show_stacked(path)

    def _cycle_compare_view(self) -> None:
        if self._compare_view == "pyramid":
            self._compare_view = "focus-stack"
        else:
            self._compare_view = "pyramid"
        self._show_compare(self._compare_view)
        self._update_compare_button_label()

    def _update_compare_button_label(self) -> None:
        if self._compare_view is None:
            return
        current = "Pyramid" if self._compare_view == "pyramid" else "focus-stack"
        self.btn_compare_view.setText(f"View: {current} ↻")
