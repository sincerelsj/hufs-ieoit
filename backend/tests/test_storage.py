from pathlib import Path

import pytest

from app.config import Settings
from app.storage import LocalStorage, make_storage, media_key


def test_local_put_open_roundtrip(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)

    storage.put("instagram/org/101.jpg", b"dummy-bytes", "image/jpeg")

    assert storage.open("instagram/org/101.jpg") == b"dummy-bytes"
    assert (tmp_path / "instagram" / "org" / "101.jpg").is_file()


def test_local_rejects_traversal(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)

    with pytest.raises(ValueError):
        storage.put("../x", b"x", "text/plain")
    with pytest.raises(ValueError):
        storage.open("instagram/../../x")


@pytest.mark.parametrize("key", ["/etc/passwd", "C:/x", "C:\\x", "a\\b", ""])
def test_local_rejects_invalid_keys(tmp_path: Path, key: str) -> None:
    storage = LocalStorage(tmp_path)

    with pytest.raises(ValueError):
        storage.put(key, b"x", "text/plain")
    with pytest.raises(ValueError):
        storage.delete(key)


def test_local_open_missing_key_raises(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)

    with pytest.raises(FileNotFoundError):
        storage.open("instagram/org/missing.jpg")


def test_local_delete_removes_file(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    storage.put("instagram/org/102.jpg", b"dummy", "image/jpeg")

    storage.delete("instagram/org/102.jpg")

    assert not (tmp_path / "instagram" / "org" / "102.jpg").exists()


def test_local_delete_missing_is_noop(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)

    storage.delete("instagram/org/never-stored.jpg")


def test_media_key_format() -> None:
    assert media_key("org", "123", "jpg") == "instagram/org/123.jpg"


def test_make_storage_returns_local_storage(settings: Settings) -> None:
    assert isinstance(make_storage(settings), LocalStorage)
