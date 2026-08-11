from pathlib import Path

import pytest

from backend.services.repository_snapshot import (
    RepositorySnapshotError,
    collect_repository_snapshot,
)


def test_snapshot_is_secret_aware_and_ignores_generated_directories(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')", encoding="utf-8")
    (tmp_path / ".env").write_text(
        "API_TOKEN=do-not-hash-this\nexport SAFE_NAME=value\n",
        encoding="utf-8",
    )
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "ignored.js").write_text("ignored", encoding="utf-8")

    snapshot = collect_repository_snapshot(tmp_path)

    assert snapshot.files[".env"] == b""
    assert snapshot.files["src/app.py"] == b"print('ok')"
    assert "node_modules/ignored.js" not in snapshot.files
    assert snapshot.environment_variable_names == ("API_TOKEN", "SAFE_NAME")
    assert b"do-not-hash-this" not in b"".join(snapshot.files.values())


def test_snapshot_rejects_unbounded_file_count(tmp_path: Path):
    (tmp_path / "one.txt").write_text("1", encoding="utf-8")
    (tmp_path / "two.txt").write_text("2", encoding="utf-8")

    with pytest.raises(RepositorySnapshotError, match="more than"):
        collect_repository_snapshot(tmp_path, max_files=1)


def test_snapshot_streams_tree_without_materializing_rglob(tmp_path: Path, monkeypatch):
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "source.py").write_text("value = 1", encoding="utf-8")

    def reject_rglob(*_args, **_kwargs):
        raise AssertionError("snapshot traversal must remain streaming")

    monkeypatch.setattr(Path, "rglob", reject_rglob)

    snapshot = collect_repository_snapshot(tmp_path)

    assert snapshot.paths == ("nested/source.py",)


def test_large_files_are_represented_by_content_digest(tmp_path: Path, monkeypatch):
    import backend.services.repository_snapshot as module

    monkeypatch.setattr(module, "MAX_INLINE_FILE_BYTES", 4)
    (tmp_path / "asset.bin").write_bytes(b"abcdefgh")

    snapshot = collect_repository_snapshot(tmp_path)

    assert snapshot.files["asset.bin"].startswith(b"zeroops-large-file-sha256:")
    assert b"abcdefgh" not in snapshot.files["asset.bin"]
