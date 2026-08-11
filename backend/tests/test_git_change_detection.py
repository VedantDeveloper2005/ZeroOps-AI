from pathlib import Path
from types import SimpleNamespace

from backend.services import git


def test_changed_files_returns_none_for_archive_workspace(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspaces"
    repository = workspace / "deployments" / "run-1"
    repository.mkdir(parents=True)
    monkeypatch.setattr(git, "WORKSPACE_DIR", str(workspace))

    assert git.get_changed_files(
        str(repository),
        "a" * 40,
        "b" * 40,
    ) is None


def test_changed_files_fetches_baseline_without_exposing_token(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspaces"
    repository = workspace / "deployments" / "run-1"
    (repository / ".git").mkdir(parents=True)
    monkeypatch.setattr(git, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setattr(git.shutil, "which", lambda name: "/usr/bin/git")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if "cat-file" in command:
            return SimpleNamespace(returncode=1, stdout="")
        if "fetch" in command:
            return SimpleNamespace(returncode=0, stdout="")
        return SimpleNamespace(returncode=0, stdout="src/app.py\nREADME.md\nsrc/app.py\n")

    monkeypatch.setattr(git.subprocess, "run", fake_run)

    changed = git.get_changed_files(
        str(repository),
        "a" * 40,
        "b" * 40,
        "github-secret",
    )

    assert changed == ("README.md", "src/app.py")
    assert all("github-secret" not in " ".join(command) for command, _ in calls)
    assert all(call[1]["env"]["GIT_CONFIG_VALUE_0"].startswith("Authorization: Basic ") for call in calls)
