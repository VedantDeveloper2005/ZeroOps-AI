import os
import tempfile
import zipfile

import pytest
from fastapi import HTTPException

try:
    from backend.main import safe_extract_zip
except ImportError:
    from main import safe_extract_zip


def test_safe_extract_zip_allows_regular_source_files():
    with tempfile.TemporaryDirectory() as directory:
        archive_path = os.path.join(directory, "source.zip")
        target = os.path.join(directory, "target")
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("app/package.json", "{}")

        safe_extract_zip(archive_path, target)

        assert os.path.isfile(os.path.join(target, "app", "package.json"))


@pytest.mark.parametrize("entry_name", ["../outside.txt", "/outside.txt"])
def test_safe_extract_zip_rejects_path_traversal(entry_name):
    with tempfile.TemporaryDirectory() as directory:
        archive_path = os.path.join(directory, "unsafe.zip")
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr(entry_name, "unsafe")

        with pytest.raises(HTTPException, match="unsafe paths"):
            safe_extract_zip(archive_path, os.path.join(directory, "target"))


def test_safe_extract_zip_rejects_symbolic_links():
    with tempfile.TemporaryDirectory() as directory:
        archive_path = os.path.join(directory, "unsafe.zip")
        entry = zipfile.ZipInfo("link")
        entry.create_system = 3
        entry.external_attr = 0o120777 << 16
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr(entry, "target")

        with pytest.raises(HTTPException, match="symbolic links"):
            safe_extract_zip(archive_path, os.path.join(directory, "target"))
