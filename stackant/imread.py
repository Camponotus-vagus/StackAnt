"""Image decoding that survives paths cv2.imread cannot open."""
from __future__ import annotations

import cv2
import numpy as np


def imread(path: str, flags: int = cv2.IMREAD_COLOR) -> np.ndarray | None:
    """Drop-in for cv2.imread: None when the file is missing or undecodable.

    cv2.imread uses the narrow-char C API on Windows, so a path with
    non-ASCII characters (C:\\Users\\José\\AppData\\Local\\Temp\\…) silently
    returns None. Reading the bytes in Python and decoding in memory works
    on every platform.
    """
    try:
        data = np.fromfile(path, dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, flags)
