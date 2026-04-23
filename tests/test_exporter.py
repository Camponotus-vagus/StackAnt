import hashlib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from stackant.exporter import export_jpeg, export_tiff


def _make_tiff(path: Path, size=(120, 80), color=(30, 90, 170)) -> None:
    arr = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    arr[:] = color
    Image.fromarray(arr).save(path, format="TIFF")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_export_tiff_is_byte_for_byte_copy(tmp_path: Path) -> None:
    src = tmp_path / "stacked.tif"
    dst = tmp_path / "out.tif"
    _make_tiff(src)
    export_tiff(str(src), str(dst))
    assert dst.is_file()
    assert _sha(src) == _sha(dst)


def test_export_tiff_same_path_is_a_noop(tmp_path: Path) -> None:
    src = tmp_path / "same.tif"
    _make_tiff(src)
    sha_before = _sha(src)
    export_tiff(str(src), str(src))
    assert _sha(src) == sha_before


def test_export_jpeg_writes_readable_image(tmp_path: Path) -> None:
    src = tmp_path / "stacked.tif"
    dst = tmp_path / "out.jpg"
    _make_tiff(src)
    export_jpeg(str(src), str(dst), quality=90)
    assert dst.is_file()
    with Image.open(dst) as img:
        assert img.format == "JPEG"
        assert img.size == (120, 80)


def test_export_jpeg_quality_affects_file_size(tmp_path: Path) -> None:
    src = tmp_path / "stacked.tif"
    rng = np.random.default_rng(0)
    # Textured image so quality actually changes output bytes.
    arr = rng.integers(0, 255, size=(400, 600, 3), dtype=np.uint8)
    Image.fromarray(arr).save(src, format="TIFF", compression="raw")
    q_low = tmp_path / "low.jpg"
    q_high = tmp_path / "high.jpg"
    export_jpeg(str(src), str(q_low), quality=60)
    export_jpeg(str(src), str(q_high), quality=98)
    assert q_low.stat().st_size < q_high.stat().st_size
