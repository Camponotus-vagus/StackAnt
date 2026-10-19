import hashlib
from pathlib import Path

import numpy as np
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


def _jpeg_pixels(path: Path) -> np.ndarray:
    with Image.open(path) as img:
        return np.asarray(img.convert("RGB"))


def test_export_jpeg_uint16_gray_does_not_saturate(tmp_path: Path) -> None:
    import cv2

    arr = np.full((20, 40), 1000, dtype=np.uint16)
    arr[:, 20:] = 60000
    src = tmp_path / "g16.tif"
    assert cv2.imwrite(str(src), arr)
    dst = tmp_path / "g16.jpg"
    export_jpeg(str(src), str(dst), quality=100)
    px = _jpeg_pixels(dst)
    assert px[10, 5, 0] < 10
    assert 225 <= px[10, 35, 0] <= 240


def test_export_jpeg_uint16_rgb_does_not_saturate(tmp_path: Path) -> None:
    import cv2

    arr = np.zeros((20, 40, 3), dtype=np.uint16)
    arr[:, :20] = (1000, 1000, 1000)
    arr[:, 20:] = (60000, 1000, 1000)  # BGR: strong blue
    src = tmp_path / "c16.tif"
    assert cv2.imwrite(str(src), arr)
    dst = tmp_path / "c16.jpg"
    export_jpeg(str(src), str(dst), quality=100)
    px = _jpeg_pixels(dst)
    assert px[10, 5].max() < 10
    assert px[10, 35, 2] > 200 and px[10, 35, 0] < 20


def test_export_jpeg_corrupt_source_raises_oserror_and_leaves_nothing(tmp_path: Path) -> None:
    import pytest

    src = tmp_path / "bad.tif"
    src.write_bytes(b"not an image")
    dst = tmp_path / "out.jpg"
    with pytest.raises(OSError):
        export_jpeg(str(src), str(dst))
    assert not dst.exists()
    assert list(tmp_path.glob("*.part*")) == []


def test_export_tiff_failure_leaves_no_truncated_file(tmp_path: Path, monkeypatch) -> None:
    import pytest

    from stackant import exporter

    src = tmp_path / "s.tif"
    _make_tiff(src)
    dst = tmp_path / "out.tif"

    def half_copy(s, d):
        Path(d).write_bytes(b"trunc")
        raise OSError("disk full")

    monkeypatch.setattr(exporter.shutil, "copy2", half_copy)
    with pytest.raises(OSError):
        export_tiff(str(src), str(dst))
    assert not dst.exists()
    assert list(tmp_path.glob("*.part*")) == []


def test_export_overwrite_is_atomic_replace(tmp_path: Path) -> None:
    src = tmp_path / "s.tif"
    _make_tiff(src)
    dst = tmp_path / "out.tif"
    dst.write_bytes(b"old")
    export_tiff(str(src), str(dst))
    assert _sha(src) == _sha(dst)
