import cv2
import numpy as np

from stackant.imread import imread


def test_reads_non_ascii_path(tmp_path):
    folder = tmp_path / "José_formiche"
    folder.mkdir()
    path = folder / "frame_ü.png"
    img = np.full((8, 10, 3), 77, dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    path.write_bytes(buf.tobytes())
    out = imread(str(path))
    assert out is not None and out.shape == (8, 10, 3)
    assert int(out[0, 0, 0]) == 77


def test_missing_or_empty_returns_none(tmp_path):
    assert imread(str(tmp_path / "nope.tif")) is None
    empty = tmp_path / "empty.tif"
    empty.write_bytes(b"")
    assert imread(str(empty)) is None
    junk = tmp_path / "junk.tif"
    junk.write_bytes(b"not an image")
    assert imread(str(junk)) is None
