import io
import zipfile

import pytest

try:
    from backend.services import git
except ImportError:
    from services import git


def test_repository_name_rejects_urls_and_path_traversal():
    for invalid_name in ("../repo", "owner/../repo", "https://github.com/owner/repo", "owner/repo/extra"):
        with pytest.raises(ValueError):
            git.get_repo_path(invalid_name)


def test_safe_extract_rejects_archive_path_traversal(tmp_path):
    archive_data = io.BytesIO()
    with zipfile.ZipFile(archive_data, "w") as archive:
        archive.writestr("../outside.txt", "unsafe")

    archive_data.seek(0)
    with zipfile.ZipFile(archive_data) as archive:
        with pytest.raises(RuntimeError, match="unsafe path"):
            git._safe_extract(archive, str(tmp_path))

    assert not (tmp_path.parent / "outside.txt").exists()
