"""QApplication bootstrap with dependency gate."""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

from . import config
from .dependency_checker import check, missing_deps_message
from .mainwindow import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setApplicationVersion(config.APP_VERSION)
    app.setOrganizationName(config.ORG_NAME)

    statuses = check()
    error = missing_deps_message(statuses)
    if error:
        dlg = QMessageBox()
        dlg.setIcon(QMessageBox.Icon.Critical)
        dlg.setWindowTitle(f"{config.APP_NAME} — missing dependencies")
        dlg.setText("Required external tools are not available.")
        dlg.setInformativeText(error)
        dlg.setStandardButtons(QMessageBox.StandardButton.Close)
        dlg.exec()
        return 1

    window = MainWindow(statuses)
    window.show()
    return app.exec()
