"""Stack panel: stack/cancel buttons + default and advanced focus-stack params."""
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)


class StackControls(QGroupBox):
    stack_requested = pyqtSignal()
    cancel_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Focus stacking", parent)
        self._build_ui()
        self.set_ready(False)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        btn_row = QHBoxLayout()
        self.btn_stack = QPushButton("Stack Frames")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setEnabled(False)
        btn_row.addWidget(self.btn_stack)
        btn_row.addWidget(self.btn_cancel)
        layout.addLayout(btn_row)

        self.btn_stack.clicked.connect(self.stack_requested.emit)
        self.btn_cancel.clicked.connect(self.cancel_requested.emit)

        self.btn_advanced = QPushButton("Advanced options ▾")
        self.btn_advanced.setCheckable(True)
        self.btn_advanced.toggled.connect(self._toggle_advanced)
        layout.addWidget(self.btn_advanced)

        self.advanced_box = QGroupBox()
        self.advanced_box.setFlat(True)
        ab = QVBoxLayout(self.advanced_box)

        row = QHBoxLayout()
        row.addWidget(QLabel("Consistency (0–2):"))
        self.spn_consistency = QSpinBox()
        self.spn_consistency.setRange(0, 2)
        self.spn_consistency.setValue(2)
        self.spn_consistency.setToolTip(
            "Higher values reject more pixels that disagree across frames — "
            "cleaner result, slightly longer runtime."
        )
        row.addWidget(self.spn_consistency)
        row.addStretch(1)
        ab.addLayout(row)

        self.chk_denoise = QCheckBox("Denoise")
        self.chk_denoise.setChecked(True)
        ab.addWidget(self.chk_denoise)

        row = QHBoxLayout()
        row.addWidget(QLabel("Sharpen strength (0–3):"))
        self.spn_sharp = QSpinBox()
        self.spn_sharp.setRange(0, 3)
        self.spn_sharp.setValue(1)
        row.addWidget(self.spn_sharp)
        row.addStretch(1)
        ab.addLayout(row)

        row = QHBoxLayout()
        self.chk_halo = QCheckBox("Halo radius:")
        self.chk_halo.setToolTip(
            "Radius in pixels for halo removal around sharp edges. Leave off "
            "unless the result shows bright fringes."
        )
        self.spn_halo = QSpinBox()
        self.spn_halo.setRange(1, 200)
        self.spn_halo.setValue(32)
        self.spn_halo.setEnabled(False)
        self.chk_halo.toggled.connect(self.spn_halo.setEnabled)
        row.addWidget(self.chk_halo)
        row.addWidget(self.spn_halo)
        row.addStretch(1)
        ab.addLayout(row)

        ab.addWidget(QLabel("Extra CLI flags (passed verbatim):"))
        self.txt_extra = QLineEdit()
        self.txt_extra.setPlaceholderText("e.g. --threads=4 --no-contrast")
        ab.addWidget(self.txt_extra)

        layout.addWidget(self.advanced_box)
        self.advanced_box.setVisible(False)

    def _toggle_advanced(self, on: bool) -> None:
        self.advanced_box.setVisible(on)
        self.btn_advanced.setText("Advanced options ▴" if on else "Advanced options ▾")

    def set_ready(self, ready: bool) -> None:
        self.btn_stack.setEnabled(ready and not self.btn_cancel.isEnabled())

    def set_running(self, running: bool) -> None:
        self.btn_stack.setEnabled(not running)
        self.btn_cancel.setEnabled(running)

    def params(self) -> dict:
        return {
            "consistency": self.spn_consistency.value(),
            "denoise": self.chk_denoise.isChecked(),
            "sharp_strength": self.spn_sharp.value(),
            "halo_radius": self.spn_halo.value() if self.chk_halo.isChecked() else None,
            "extra_cli": self.txt_extra.text(),
        }
