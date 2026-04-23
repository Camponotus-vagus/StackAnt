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
        self._ready: bool = False
        self._running: bool = False
        self._build_ui()
        self.set_ready(False)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        from PyQt6.QtWidgets import QButtonGroup, QRadioButton

        method_row = QVBoxLayout()
        method_row.addWidget(QLabel("Method:"))
        self._method_group = QButtonGroup(self)
        self.rb_pyramid = QRadioButton("Pyramid")
        self.rb_pyramid.setToolTip(
            "Laplacian-pyramid fusion with guided-filter smoothing.\n"
            "Slower, better edges (cleaner on legs/antennae).\n"
            "Same family as Helicon Method C and Zerene PMax."
        )
        self.rb_focus_stack = QRadioButton("focus-stack")
        self.rb_focus_stack.setToolTip(
            "Complex-wavelet fusion via the focus-stack CLI.\n"
            "Faster, GPU-accelerated when available.\n"
            "Slightly more halo-prone at hard contrast edges."
        )
        self.rb_auto = QRadioButton("Auto")
        self.rb_auto.setToolTip(
            "Picks per image: Pyramid for small stacks (≤50 frames at ≤2K),\n"
            "focus-stack otherwise. For quality-critical work, use Compare."
        )
        self._method_group.addButton(self.rb_pyramid, 0)
        self._method_group.addButton(self.rb_focus_stack, 1)
        self._method_group.addButton(self.rb_auto, 2)
        self.rb_pyramid.setChecked(True)
        method_row.addWidget(self.rb_pyramid)
        method_row.addWidget(self.rb_focus_stack)
        method_row.addWidget(self.rb_auto)
        layout.addLayout(method_row)

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

        self.chk_no_opencl = QCheckBox("Disable OpenCL (GPU) — use CPU only")
        self.chk_no_opencl.setToolTip(
            "Check this if stacking fails with a CL_OUT_OF_RESOURCES or similar\n"
            "OpenCL error. Slower, but works on machines where the GPU driver\n"
            "can't handle focus-stack's wavelet kernels."
        )
        ab.addWidget(self.chk_no_opencl)

        ab.addWidget(QLabel("Extra CLI flags (passed verbatim):"))
        self.txt_extra = QLineEdit()
        self.txt_extra.setPlaceholderText("e.g. --threads=4 --no-contrast")
        ab.addWidget(self.txt_extra)

        layout.addWidget(self.advanced_box)
        self.advanced_box.setVisible(False)

    def _toggle_advanced(self, on: bool) -> None:
        self.advanced_box.setVisible(on)
        self.btn_advanced.setText("Advanced options ▴" if on else "Advanced options ▾")

    def method(self) -> str:
        if self.rb_focus_stack.isChecked():
            return "focus-stack"
        if self.rb_auto.isChecked():
            return "auto"
        return "pyramid"

    def set_method(self, method: str) -> None:
        if method == "focus-stack":
            self.rb_focus_stack.setChecked(True)
        elif method == "auto":
            self.rb_auto.setChecked(True)
        else:
            self.rb_pyramid.setChecked(True)

    def set_ready(self, ready: bool) -> None:
        self._ready = ready
        self.btn_stack.setEnabled(ready and not self._running)

    def set_running(self, running: bool) -> None:
        self._running = running
        self.btn_cancel.setEnabled(running)
        # Stack is only clickable when we have frames AND nothing is running.
        self.btn_stack.setEnabled(self._ready and not running)

    def params(self) -> dict:
        extra = self.txt_extra.text().strip()
        if self.chk_no_opencl.isChecked() and "--no-opencl" not in extra:
            extra = ("--no-opencl " + extra).strip()
        return {
            "consistency": self.spn_consistency.value(),
            "denoise": self.chk_denoise.isChecked(),
            "sharp_strength": self.spn_sharp.value(),
            "halo_radius": self.spn_halo.value() if self.chk_halo.isChecked() else None,
            "extra_cli": extra,
        }
