import io
import os
import zipfile
from types import SimpleNamespace

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


def test_safe_extract_enforces_archive_file_and_expansion_limits(monkeypatch, tmp_path):
    archive_data = io.BytesIO()
    with zipfile.ZipFile(archive_data, "w") as archive:
        archive.writestr("repository/a.txt", "a")
        archive.writestr("repository/b.txt", "b")

    monkeypatch.setattr(git.config, "MAX_UPLOAD_ARCHIVE_FILES", 1)
    archive_data.seek(0)
    with zipfile.ZipFile(archive_data) as archive:
        with pytest.raises(RuntimeError, match="too many files"):
            git._safe_extract(archive, str(tmp_path))

    monkeypatch.setattr(git.config, "MAX_UPLOAD_ARCHIVE_FILES", 10)
    monkeypatch.setattr(git.config, "MAX_UPLOAD_UNCOMPRESSED_MB", 0)
    archive_data.seek(0)
    with zipfile.ZipFile(archive_data) as archive:
        with pytest.raises(RuntimeError, match="expands beyond"):
            git._safe_extract(archive, str(tmp_path))


def test_safe_extract_rejects_unsafe_compression_ratio(monkeypatch, tmp_path):
    archive_data = io.BytesIO()
    with zipfile.ZipFile(archive_data, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("repository/large.txt", "0" * 100_000)

    monkeypatch.setattr(git.config, "MAX_UPLOAD_COMPRESSION_RATIO", 2)
    archive_data.seek(0)
    with zipfile.ZipFile(archive_data) as archive:
        with pytest.raises(RuntimeError, match="compression ratio"):
            git._safe_extract(archive, str(tmp_path))


def test_clone_uses_selected_branch_and_deployment_workspace(monkeypatch, tmp_path):
    deployment_id = "f790b17d-5687-4c0b-91c6-84ed4a777ca8"
    captured = {}
    monkeypatch.setattr(git, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(git.shutil, "which", lambda _: "git")

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["environment"] = kwargs["env"]
        os.makedirs(command[-1])
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(git.subprocess, "run", fake_run)

    repo_path = git.clone_repo(
        "owner/repository",
        "private-token",
        branch="feature/production-ready",
        workspace_key=deployment_id,
    )

    assert captured["command"] == [
        "git",
        "clone",
        "--depth",
        "1",
        "--branch",
        "feature/production-ready",
        "--single-branch",
        "https://github.com/owner/repository.git",
        repo_path,
    ]
    assert "private-token" not in captured["command"]
    assert repo_path == str(tmp_path / "deployments" / deployment_id)

    git.cleanup_workspace(repo_path)
    assert not os.path.exists(repo_path)


def test_zipball_fallback_uses_only_selected_branch(monkeypatch, tmp_path):
    archive_data = io.BytesIO()
    with zipfile.ZipFile(archive_data, "w") as archive:
        archive.writestr("owner-repository-sha/application.txt", "real source")
    payload = archive_data.getvalue()
    requested_urls = []

    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.close()

    def fake_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        return FakeResponse(payload)

    monkeypatch.setattr(git, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(git.shutil, "which", lambda _: None)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    repo_path = git.clone_repo(
        "owner/repository",
        branch="release/2026-07",
        workspace_key="deployment-123",
    )

    assert requested_urls == [
        "https://api.github.com/repos/owner/repository/zipball/release%2F2026-07"
    ]
    assert (tmp_path / "deployments" / "deployment-123" / "application.txt").read_text() == "real source"
    git.cleanup_workspace(repo_path)


def test_workspace_and_branch_values_cannot_escape_managed_root(monkeypatch, tmp_path):
    monkeypatch.setattr(git, "WORKSPACE_DIR", str(tmp_path))

    with pytest.raises(ValueError, match="Workspace key"):
        git.get_repo_path("owner/repository", "../another-deployment")
    with pytest.raises(ValueError, match="branch"):
        git.clone_repo("owner/repository", branch="../main", workspace_key="deployment-123")


def test_clone_checks_out_the_resolved_commit_detached(monkeypatch, tmp_path):
    commit_sha = "a1" * 20
    commands = []

    class Result:
        returncode = 0
        stderr = ""

        def __init__(self, stdout=""):
            self.stdout = stdout

    monkeypatch.setattr(git, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(git.shutil, "which", lambda _: "git")

    def fake_run(command, **_kwargs):
        commands.append(command)
        if command[-2:] == ["rev-parse", "HEAD"]:
            return Result(commit_sha + "\n")
        return Result()

    monkeypatch.setattr(git.subprocess, "run", fake_run)

    result = git.clone_repo(
        "owner/repository",
        token="secret-token",
        branch="release/reviewed",
        commit_sha=commit_sha,
        workspace_key="deployment-immutable",
    )

    assert result == str(tmp_path / "deployments" / "deployment-immutable")
    assert any(command[-5:] == ["fetch", "--depth", "1", "origin", commit_sha] for command in commands)
    assert any(command[-3:] == ["checkout", "--detach", commit_sha] for command in commands)


def test_clone_rejects_partial_or_untrusted_commit_identifiers(monkeypatch, tmp_path):
    monkeypatch.setattr(git, "WORKSPACE_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="commit"):
        git.clone_repo(
            "owner/repository",
            branch="main",
            commit_sha="../main",
            workspace_key="deployment-123",
        )
    with pytest.raises(ValueError, match="outside"):
        git.cleanup_workspace(str(tmp_path.parent / "unmanaged"))


def test_uploaded_source_is_copied_into_disposable_deployment_workspace(monkeypatch, tmp_path):
    managed_root = tmp_path / "managed"
    source_root = tmp_path / "uploaded-source"
    source_root.mkdir()
    (source_root / "application.py").write_text("print('production source')")
    monkeypatch.setattr(git, "WORKSPACE_DIR", str(managed_root))

    deployment_path = git.prepare_local_source(str(source_root), "deployment-upload")

    assert deployment_path == str(managed_root / "deployments" / "deployment-upload")
    assert (managed_root / "deployments" / "deployment-upload" / "application.py").is_file()
    assert (source_root / "application.py").is_file()

    git.cleanup_workspace(deployment_path)
    assert not os.path.exists(deployment_path)
    assert (source_root / "application.py").is_file()
