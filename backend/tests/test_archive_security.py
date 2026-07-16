import zipfile
import pytest
from app.parsers import UnsafeArchiveError, safe_extract_rar, safe_extract_zip


def test_zip_path_traversal_is_rejected(tmp_path):
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../escape.csv", "x")
    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(archive, tmp_path / "out")


def test_zip_extraction_stays_inside_target(tmp_path):
    archive = tmp_path / "safe.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("bank/flow.csv", "a,b\n1,2")
    files = safe_extract_zip(archive, tmp_path / "out")
    assert len(files) == 1
    assert files[0].resolve().is_relative_to((tmp_path / "out").resolve())


def test_zip_uncompressed_size_limit_is_enforced(tmp_path):
    archive = tmp_path / "bomb.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        handle.writestr("large.txt", "0" * 4096)
    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(archive, tmp_path / "out", max_bytes=1024)


def test_rar_path_traversal_is_rejected_before_member_is_opened(tmp_path, monkeypatch):
    class Member:
        filename = "../escape.csv"
        file_size = 1

        @staticmethod
        def isdir():
            return False

    class Archive:
        def __init__(self, _path):
            self.opened = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        @staticmethod
        def infolist():
            return [Member()]

        def open(self, _member):
            self.opened = True
            raise AssertionError("unsafe member must not be opened")

    monkeypatch.setattr("app.parsers.rarfile.RarFile", Archive)
    with pytest.raises(UnsafeArchiveError):
        safe_extract_rar(tmp_path / "unsafe.rar", tmp_path / "out")
