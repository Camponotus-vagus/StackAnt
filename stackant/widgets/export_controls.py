"""Export panel: format selection, quality, name, output folder."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
)


class ExportControls(QGroupBox):
    export_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Export", parent)
        self._default_folder: str = str(Path.home())
        self._build_ui()
        self.set_exportable(False)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        fmt_row = QHBoxLayout()
        self.chk_tiff = QCheckBox("TIFF")
        self.chk_tiff.setChecked(True)
        self.chk_tiff.setToolTip("Export as a lossless TIFF file")
        self.chk_tiff.setAccessibleName("Export as TIFF")
        self.chk_jpeg = QCheckBox("JPEG")
        self.chk_jpeg.setChecked(True)
        self.chk_jpeg.setToolTip("Export as a compressed JPEG file")
        self.chk_jpeg.setAccessibleName("Export as JPEG")
        fmt_row.addWidget(self.chk_tiff)
        fmt_row.addWidget(self.chk_jpeg)
        fmt_row.addStretch(1)
        layout.addLayout(fmt_row)

        q_row = QHBoxLayout()
        q_row.addWidget(QLabel("JPEG quality:"))
        self.sld_quality = QSlider(Qt.Orientation.Horizontal)
        self.sld_quality.setRange(60, 100)
        self.sld_quality.setValue(95)
        self.sld_quality.setToolTip("Compression quality for JPEG export (60–100)")
        self.sld_quality.setAccessibleName("JPEG compression quality")
        self.lbl_quality = QLabel("95")
        self.lbl_quality.setMinimumWidth(28)
        self.sld_quality.valueChanged.connect(lambda v: self.lbl_quality.setText(str(v)))
        q_row.addWidget(self.sld_quality, stretch=1)
        q_row.addWidget(self.lbl_quality)
        layout.addLayout(q_row)
        self.chk_jpeg.toggled.connect(self._sync_quality_enabled)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("output_stacked")
        self.txt_name.setToolTip(
            "File name without extension. The .tif and/or .jpg suffix is "
            "appended automatically based on the selected formats."
        )
        self.txt_name.setAccessibleName("Output filename")
        name_row.addWidget(self.txt_name, stretch=1)
        layout.addLayout(name_row)

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Folder:"))
        self.txt_folder = QLineEdit()
        self.txt_folder.setToolTip("Destination folder for the exported file")
        self.txt_folder.setAccessibleName("Output folder path")
        self.btn_browse = QPushButton("Browse…")
        self.btn_browse.setToolTip("Select the output folder")
        self.btn_browse.setAccessibleName("Browse for output folder")
        self.btn_browse.clicked.connect(self._browse_folder)
        folder_row.addWidget(self.txt_folder, stretch=1)
        folder_row.addWidget(self.btn_browse)
        layout.addLayout(folder_row)

        self.btn_export = QPushButton("Export")
        self.btn_export.setAccessibleName("Export result")
        self.btn_export.clicked.connect(self.export_requested.emit)
        layout.addWidget(self.btn_export)

    def set_exportable(self, exportable: bool) -> None:
        """Gate only the Export button. Formats/quality/name/folder stay editable
        so they can be dialed in before stacking (single mode) or for a batch."""
        self.btn_export.setEnabled(exportable)
        if exportable:
            self.btn_export.setToolTip("Export the stacked result to the chosen folder")
        else:
            self.btn_export.setToolTip("Run a stack first to enable export")

    def _sync_quality_enabled(self, on: bool) -> None:
        self.sld_quality.setEnabled(on)
        self.lbl_quality.setEnabled(on)

    def _browse_folder(self) -> None:
        start = self.txt_folder.text() or self._default_folder
        path = QFileDialog.getExistingDirectory(self, "Select output folder", start)
        if path:
            self.txt_folder.setText(path)

    # ---- public API ------------------------------------------------------

    def prefill_for_input(self, input_path: str) -> None:
        p = Path(input_path)
        if p.is_dir():
            folder = str(p)
            stem = p.name or "stacked"
        else:
            folder = str(p.parent)
            stem = p.stem or "output"
        self._default_folder = folder
        self.txt_folder.setText(folder)
        self.txt_name.setText(f"{stem}_stacked")

    def settings(self) -> dict:
        return {
            "tiff": self.chk_tiff.isChecked(),
            "jpeg": self.chk_jpeg.isChecked(),
            "quality": self.sld_quality.value(),
            "name": self.txt_name.text().strip() or "output_stacked",
            "folder": self.txt_folder.text().strip(),
        }
