"""QApplication bootstrap with dependency gate."""
from __future__ import annotations

import contextlib
import sys
import traceback

from PyQt6.QtWidgets import QApplication, QMessageBox

from . import config, tempfiles
from .dependency_checker import augment_path, check, missing_deps_message
from .mainwindow import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setApplicationVersion(config.APP_VERSION)
    app.setOrganizationName(config.ORG_NAME)

    augment_path()
    statuses = check()
    error = missing_deps_message(statuses)
    if error:
        sys.__stderr__.write(error + "\n")
        missing_deps_dialog(error).exec()
        return 1

    tempfiles.sweep_stale()
    window = MainWindow(statuses)
    install_excepthook(window)
    window.show()
    return app.exec()


def missing_deps_dialog(error: str) -> QMessageBox:
    dlg = QMessageBox()
    # The native NSAlert that Qt 6.11 uses on macOS throws during layout on
    # macOS 27 and takes the process down (trace trap) before it is shown.
    dlg.setOptions(QMessageBox.Option.DontUseNativeDialog)
    dlg.setIcon(QMessageBox.Icon.Critical)
    dlg.setWindowTitle(f"{config.APP_NAME} — missing dependencies")
    dlg.setText("Required external tools are not available.")
    dlg.setInformativeText(error)
    dlg.setStandardButtons(QMessageBox.StandardButton.Close)
    return dlg


def install_excepthook(window: MainWindow) -> None:
    """Report uncaught slot exceptions instead of letting them kill the app.

    With the default sys.excepthook, PyQt6 aborts the whole process on an
    exception raised inside a slot; any custom hook keeps it alive.
    """
    def hook(exc_type, exc, tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        sys.__stderr__.write(text)
        with contextlib.suppress(Exception):  # never raise from the hook itself
            window.report_internal_error(text)

    sys.excepthook = hook
