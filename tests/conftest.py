"""Session-wide test isolation so the suite never touches real user state.

StackAnt persists through ``settings._s()`` — the single ``QSettings(ORG, APP)``
factory in the codebase. Several tests call ``settings.save_*`` against it, so an
unsandboxed run reads *and overwrites* the user's real preferences (export folder,
stacking method, OpenCL toggle, …).

On macOS the ``QSettings(org, app)`` constructor ignores ``setDefaultFormat`` and
always uses the native plist, so redirecting via ``setPath`` does not work. The
reliable fix is to replace the factory itself with one backed by a throwaway INI
file. This runs at import time, before any fixture or test.
"""
import os
import tempfile

from PyQt6.QtCore import QSettings

from stackant import settings

_QSETTINGS_FILE = os.path.join(
    tempfile.mkdtemp(prefix="stackant_qsettings_test_"), "stackant.ini"
)


def _isolated_settings() -> QSettings:
    return QSettings(_QSETTINGS_FILE, QSettings.Format.IniFormat)


settings._s = _isolated_settings
