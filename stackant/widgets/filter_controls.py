"""Filter panel: blur-threshold slider + decimation target + count readout."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)


class FilterControls(QGroupBox):
    """Filter group box. Emits when the user changes any filter parameter."""

    threshold_changed = pyqtSignal(float)
    decimation_changed = pyqtSignal(int)      # 0 = disabled
    auto_threshold_requested = pyqtSignal()

    _SLIDER_RESOLUTION = 1000

    def __init__(self, parent=None):
        super().__init__("Filter", parent)
        self._min_score: float = 0.0
        self._max_score: float = 1.0
        self._current_threshold: float = 0.0
        self._muted = False
        self._build_ui()
        self.setEnabled(False)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        t_row = QHBoxLayout()
        t_row.addWidget(QLabel("Blur threshold:"))
        self.lbl_threshold_value = QLabel("—")
        self.lbl_threshold_value.setMinimumWidth(70)
        self.lbl_threshold_value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        t_row.addWidget(self.lbl_threshold_value, stretch=1)
        layout.addLayout(t_row)

        self.sld_threshold = QSlider(Qt.Orientation.Horizontal)
        self.sld_threshold.setRange(0, self._SLIDER_RESOLUTION)
        self.sld_threshold.valueChanged.connect(self._on_slider_changed)
        self.sld_threshold.setToolTip(
            "Laplacian-variance floor: frames less sharp than this are rejected."
        )
        layout.addWidget(self.sld_threshold)

        auto_row = QHBoxLayout()
        self.btn_auto = QPushButton("Auto threshold (mean − 1σ)")
        self.btn_auto.clicked.connect(self.auto_threshold_requested.emit)
        auto_row.addWidget(self.btn_auto)
        layout.addLayout(auto_row)

        d_row = QHBoxLayout()
        self.chk_decimate = QCheckBox("Cap kept frames at:")
        self.chk_decimate.setToolTip(
            "When more frames survive the threshold than this cap, evenly-spaced\n"
            "thinning brings the set back down to the cap before stacking."
        )
        self.chk_decimate.toggled.connect(self._emit_decimation)
        self.spn_decimation_target = QSpinBox()
        self.spn_decimation_target.setRange(1, 1000)
        self.spn_decimation_target.setValue(75)
        self.spn_decimation_target.valueChanged.connect(self._emit_decimation)
        d_row.addWidget(self.chk_decimate)
        d_row.addWidget(self.spn_decimation_target)
        d_row.addStretch(1)
        layout.addLayout(d_row)

        self.lbl_counts = QLabel("—")
        self.lbl_counts.setStyleSheet("color: gray;")
        layout.addWidget(self.lbl_counts)

    def configure_range(self, min_score: float, max_score: float) -> None:
        """Set the slider's physical range from the observed score extremes."""
        if max_score <= min_score:
            max_score = min_score + 1.0
        self._min_score = min_score
        self._max_score = max_score

    def set_threshold(self, value: float) -> None:
        self._current_threshold = value
        self._muted = True
        try:
            rng = self._max_score - self._min_score
            pos = int(round((value - self._min_score) / rng * self._SLIDER_RESOLUTION))
            pos = max(0, min(self._SLIDER_RESOLUTION, pos))
            self.sld_threshold.setValue(pos)
            self.lbl_threshold_value.setText(f"{value:.1f}")
        finally:
            self._muted = False

    def set_counts(self, kept: int, total: int) -> None:
        self.lbl_counts.setText(f"{kept} / {total} frames kept")

    def decimation_target(self) -> int:
        return self.spn_decimation_target.value() if self.chk_decimate.isChecked() else 0

    def _on_slider_changed(self, pos: int) -> None:
        if self._muted:
            return
        rng = self._max_score - self._min_score
        value = self._min_score + pos / self._SLIDER_RESOLUTION * rng
        self._current_threshold = value
        self.lbl_threshold_value.setText(f"{value:.1f}")
        self.threshold_changed.emit(value)

    def _emit_decimation(self) -> None:
        self.decimation_changed.emit(self.decimation_target())
