from pathlib import Path

from stackant.folder_loader import list_images


def _touch(folder: Path, *names: str) -> None:
    for n in names:
        (folder / n).write_bytes(b"x")


def test_natural_order_not_lexicographic(tmp_path):
    _touch(tmp_path, "img_10.jpg", "img_2.jpg", "img_1.jpg")
    assert [Path(p).name for p in list_images(str(tmp_path))] == [
        "img_1.jpg", "img_2.jpg", "img_10.jpg",
    ]


def test_sort_is_case_insensitive(tmp_path):
    _touch(tmp_path, "b.jpg", "A.jpg", "c.jpg")
    assert [Path(p).name for p in list_images(str(tmp_path))] == ["A.jpg", "b.jpg", "c.jpg"]


def test_dotfiles_and_non_images_skipped(tmp_path):
    _touch(tmp_path, "._img_1.jpg", ".hidden.tif", "img_1.jpg", "notes.txt")
    assert [Path(p).name for p in list_images(str(tmp_path))] == ["img_1.jpg"]


def test_missing_folder_is_empty(tmp_path):
    assert list_images(str(tmp_path / "nope")) == []
