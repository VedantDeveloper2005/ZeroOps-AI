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


def test_git_environment_does_not_inherit_worker_credentials(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://credentialed-worker")
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "azure-secret")
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))

    environment = git._git_environment("github-token")

    assert "DATABASE_URL" not in environment
    assert "AZURE_CLIENT_SECRET" not in environment
    assert all("github-token" not in str(value) for value in environment.values())
    assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
    assert environment["GIT_CONFIG_GLOBAL"] == os.devnull
    assert environment["GIT_LFS_SKIP_SMUDGE"] == "1"


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

    def fake_urlopen(request, *, timeout, allowed_hosts):
        assert timeout == 60
        assert allowed_hosts == git._GITHUB_ARCHIVE_HOSTS
        requested_urls.append(request.full_url)
        return FakeResponse(payload)

    monkeypatch.setattr(git, "WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setattr(git.shutil, "which", lambda _: None)
    monkeypatch.setattr(git, "_open_github_request", fake_urlopen)

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


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://api.github.com/repos/owner/repository",
        "https://api.github.com.evil.example/repos/owner/repository",
        "https://api.github.com@evil.example/repos/owner/repository",
        "https://127.0.0.1/repos/owner/repository",
    ],
)
def test_github_url_allowlist_rejects_file_and_untrusted_origins(url):
    with pytest.raises(ValueError, match="approved HTTPS origins"):
        git._validated_github_url(url, allowed_hosts=git._GITHUB_ARCHIVE_HOSTS)


def test_github_request_rejects_redirect_outside_allowlist(monkeypatch):
    class RedirectedResponse(io.BytesIO):
        def __init__(self):
            super().__init__(b"")
            self.was_closed = False

        def geturl(self):
            return "file:///etc/passwd"

        def close(self):
            self.was_closed = True
            super().close()

    response = RedirectedResponse()

    class FakeOpener:
        def open(self, request, *, timeout):
            assert request.full_url == "https://api.github.com/repos/owner/repository/branches"
            assert timeout == 10
            return response

    monkeypatch.setattr(git.urllib.request, "build_opener", lambda *_: FakeOpener())
    request = git.urllib.request.Request(
        "https://api.github.com/repos/owner/repository/branches"
    )

    with pytest.raises(ValueError, match="approved HTTPS origins"):
        git._open_github_request(
            request,
            timeout=10,
            allowed_hosts=frozenset({git._GITHUB_API_HOST}),
        )

    assert response.was_closed


def test_github_archive_redirect_does_not_forward_bearer_token():
    request = git.urllib.request.Request(
        "https://api.github.com/repos/owner/repository/zipball/main"
    )
    request.add_header("Authorization", "Bearer must-not-cross-origins")
    handler = git._GitHubRedirectHandler(git._GITHUB_ARCHIVE_HOSTS)

    redirected = handler.redirect_request(
        request,
        None,
        302,
        "Found",
        {},
        "https://codeload.github.com/owner/repository/legacy.zip/main",
    )

    assert redirected is not None
    assert redirected.full_url.startswith("https://codeload.github.com/")
    assert redirected.get_header("Authorization") is None


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
        if command[1] == "init":
            os.makedirs(command[2], exist_ok=True)
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


def test_uploaded_source_rejects_symbolic_links_before_copy(monkeypatch, tmp_path):
    managed_root = tmp_path / "managed"
    source_root = tmp_path / "uploaded-source"
    source_root.mkdir()
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("must not be scanned", encoding="utf-8")
    link = source_root / "linked-secret.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symbolic links are unavailable in this test environment")
    monkeypatch.setattr(git, "WORKSPACE_DIR", str(managed_root))

    with pytest.raises(RuntimeError, match="symbolic link"):
        git.prepare_local_source(str(source_root), "deployment-upload")

    assert not (managed_root / "deployments" / "deployment-upload").exists()


def test_source_tree_limits_are_enforced_before_downstream_tools(monkeypatch, tmp_path):
    source_root = tmp_path / "repository"
    source_root.mkdir()
    (source_root / "one.txt").write_text("one", encoding="utf-8")
    (source_root / "two.txt").write_text("two", encoding="utf-8")
    monkeypatch.setattr(git.config, "MAX_UPLOAD_ARCHIVE_FILES", 1)

    with pytest.raises(RuntimeError, match="too many filesystem entries"):
        git._validate_source_tree(str(source_root))
