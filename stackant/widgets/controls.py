"""Left-side controls panel: input loading + extraction parameters."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .export_controls import ExportControls
from .filter_controls import FilterControls
from .stack_controls import StackControls


class ControlsPanel(QFrame):
    video_selected = pyqtSignal(str)
    folder_selected = pyqtSignal(str)
    extract_requested = pyqtSignal(int)   # decimation
    cancel_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._input_path: str | None = None
        self._input_is_folder: bool = False
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        input_box = QGroupBox("Input")
        ib = QVBoxLayout(input_box)
        row = QHBoxLayout()
        self.btn_open_video = QPushButton("Open Video…")
        self.btn_open_video.setAccessibleName("Open video file")
        self.btn_open_video.setToolTip("Open a video file to extract frames for focus stacking")
        self.btn_open_folder = QPushButton("Open Image Folder…")
        self.btn_open_folder.setAccessibleName("Open image folder")
        self.btn_open_folder.setToolTip("Open a directory containing pre-extracted image frames")
        row.addWidget(self.btn_open_video)
        row.addWidget(self.btn_open_folder)
        ib.addLayout(row)
        self.lbl_input = QLabel("No input loaded.")
        self.lbl_input.setWordWrap(True)
        self.lbl_input.setStyleSheet("color: gray;")
        ib.addWidget(self.lbl_input)
        layout.addWidget(input_box)

        self.extract_box = QGroupBox("Frame extraction")
        eb = QVBoxLayout(self.extract_box)
        dec_row = QHBoxLayout()
        dec_row.addWidget(QLabel("Keep every Nth frame:"))
        self.spn_decimation = QSpinBox()
        self.spn_decimation.setRange(1, 100)
        self.spn_decimation.setValue(1)
        self.spn_decimation.setAccessibleName("Frame decimation step")
        self.spn_decimation.setToolTip("1 = keep every frame; 3 = every third; etc.")
        dec_row.addWidget(self.spn_decimation)
        dec_row.addStretch(1)
        eb.addLayout(dec_row)

        btn_row = QHBoxLayout()
        self.btn_extract = QPushButton("Extract Frames")
        self.btn_extract.setAccessibleName("Extract frames")
        self.btn_extract.setEnabled(False)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setAccessibleName("Cancel extraction")
        self.btn_cancel.setToolTip("Cancel frame extraction process")
        self.btn_cancel.setEnabled(False)
        btn_row.addWidget(self.btn_extract)
        btn_row.addWidget(self.btn_cancel)
        eb.addLayout(btn_row)
        layout.addWidget(self.extract_box)

        self.filter_controls = FilterControls()
        layout.addWidget(self.filter_controls)

        self.stack_controls = StackControls()
        layout.addWidget(self.stack_controls)

        self.export_controls = ExportControls()
        layout.addWidget(self.export_controls)

        layout.addStretch(1)

        self.btn_open_video.clicked.connect(self._pick_video)
        self.btn_open_folder.clicked.connect(self._pick_folder)
        self.btn_extract.clicked.connect(self._emit_extract)
        self.btn_cancel.clicked.connect(self.cancel_requested.emit)
        self._update_extract_tooltip()

    def _pick_video(self, path: str | None = None) -> None:
        if not isinstance(path, str):
            path, _ = QFileDialog.getOpenFileName(
                self, "Open video", "", "Videos (*.mp4 *.mov *.avi *.mkv);;All files (*)"
            )
        if path:
            self._set_input(path, is_folder=False)
            self.video_selected.emit(path)

    def _pick_folder(self, path: str | None = None) -> None:
        if not isinstance(path, str):
            path = QFileDialog.getExistingDirectory(self, "Open image folder")
        if path:
            self._set_input(path, is_folder=True)
            self.folder_selected.emit(path)

    def _set_input(self, path: str, *, is_folder: bool) -> None:
        self._input_path = path
        self._input_is_folder = is_folder
        kind = "Folder" if is_folder else "Video"
        self.lbl_input.setText(f"{kind}: {Path(path).name}")
        self.lbl_input.setToolTip(path)
        self.lbl_input.setStyleSheet("")
        self.btn_extract.setEnabled(not is_folder)
        self.extract_box.setTitle(
            "Frame extraction" if not is_folder else "Frame extraction (not needed for folders)"
        )
        self.spn_decimation.setEnabled(not is_folder)
        self._update_extract_tooltip()

    def _emit_extract(self) -> None:
        self.extract_requested.emit(self.spn_decimation.value())

    def set_busy(self, busy: bool) -> None:
        self.btn_extract.setEnabled(not busy and self._input_path is not None and not self._input_is_folder)
        self.btn_cancel.setEnabled(busy)
        self.btn_open_video.setEnabled(not busy)
        self.btn_open_folder.setEnabled(not busy)
        self.spn_decimation.setEnabled(not busy and not self._input_is_folder)
        self._update_extract_tooltip()

    def _update_extract_tooltip(self) -> None:
        if self._input_path is None:
            tip = "Open a video file first to enable frame extraction."
        elif self._input_is_folder:
            tip = "Frame extraction is not needed when an image folder is loaded."
        elif self.btn_cancel.isEnabled():
            tip = "Frame extraction is currently in progress…"
        else:
            tip = "Extract frames from the loaded video using the specified decimation."
        self.btn_extract.setToolTip(tip)

    def snapshot_for_batch(self):
        """Capture the current panel settings as a BatchSettings for the batch run.

        `StackControls.params()` already folds --no-opencl into extra_cli, so the
        batch inherits the OpenCL choice. The export name/folder are intentionally
        dropped: the batch auto-names each output next to its source video.
        """
        from ..batch import BatchSettings

        sc = self.stack_controls
        exp = self.export_controls.settings()
        cap = self.filter_controls.decimation_target()
        return BatchSettings(
            method=sc.method(),
            extract_decimation=self.spn_decimation.value(),
            cap=cap if cap > 0 else None,
            focus_params=sc.params(),
            pyramid_params=sc.pyramid_params(),
            export={"tiff": exp["tiff"], "jpeg": exp["jpeg"], "quality": exp["quality"]},
        )

    @property
    def input_path(self) -> str | None:
        return self._input_path

    @property
    def input_is_folder(self) -> bool:
        return self._input_is_folder
