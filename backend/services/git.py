import os
import shutil
import subprocess
import base64
import re
import stat
from urllib.parse import quote

try:
    from backend import config
except ImportError:
    import config

WORKSPACE_DIR = config.WORKSPACE_DIR

_GITHUB_REPOSITORY_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9])?/[A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9])?$"
)
_WORKSPACE_KEY_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?$")
_GITHUB_COMMIT_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
_MAX_CHANGED_PATHS = 25_000


def _validated_repository_name(full_name: str) -> str:
    """Accept only an owner/repository identifier, never a URL or local path."""
    if not isinstance(full_name, str) or not _GITHUB_REPOSITORY_PATTERN.fullmatch(full_name):
        raise ValueError("Repository must use the GitHub owner/repository format.")
    return full_name


def _validated_branch_name(branch: str) -> str:
    """Validate a GitHub branch before using it as a git ref or URL segment."""
    if (
        not isinstance(branch, str)
        or not branch
        or len(branch) > 255
        or branch.startswith("-")
        or branch.endswith(("/", ".", ".lock"))
        or branch.startswith("/")
        or ".." in branch
        or "@{" in branch
        or any(ord(char) < 32 or char in " ~^:?*[\\\x7f" for char in branch)
    ):
        raise ValueError("The selected GitHub branch name is invalid.")
    return branch


def _validated_commit_sha(commit_sha: str) -> str:
    """Accept only a complete GitHub commit identifier."""
    if not isinstance(commit_sha, str) or not _GITHUB_COMMIT_PATTERN.fullmatch(commit_sha):
        raise ValueError("The selected GitHub commit is invalid.")
    return commit_sha.lower()


def _validated_workspace_key(workspace_key: str) -> str:
    """Accept only a caller-generated identifier, never an arbitrary path."""
    if not isinstance(workspace_key, str) or not _WORKSPACE_KEY_PATTERN.fullmatch(workspace_key):
        raise ValueError("Workspace key contains unsupported characters.")
    return workspace_key


def _git_environment(token: str | None) -> dict[str, str]:
    """Supply an OAuth token without placing it in the git command line."""
    allowed = {
        "COMSPEC",
        "LANG",
        "LC_ALL",
        "PATH",
        "PATHEXT",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "WINDIR",
    }
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in allowed
    }
    environment.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_LFS_SKIP_SMUDGE": "1",
            "GIT_OPTIONAL_LOCKS": "0",
        }
    )
    if token:
        credentials = base64.b64encode(f"x-access-token:{token}".encode("utf-8")).decode("ascii")
        environment["GIT_CONFIG_COUNT"] = "1"
        environment["GIT_CONFIG_KEY_0"] = "http.extraHeader"
        environment["GIT_CONFIG_VALUE_0"] = f"Authorization: Basic {credentials}"
    return environment


def _safe_extract(zip_file, destination: str) -> None:
    """Bound archive expansion and reject unsafe entries before extraction."""
    destination_root = os.path.realpath(destination)
    destination_prefix = destination_root + os.sep
    members = zip_file.infolist()
    if len(members) > config.MAX_UPLOAD_ARCHIVE_FILES:
        raise RuntimeError("Repository archive contains too many files.")

    total_uncompressed = sum(member.file_size for member in members)
    max_uncompressed = config.MAX_UPLOAD_UNCOMPRESSED_MB * 1024 * 1024
    if total_uncompressed > max_uncompressed:
        raise RuntimeError("Repository archive expands beyond the allowed size.")

    for member in members:
        target = os.path.realpath(os.path.join(destination_root, member.filename))
        if target != destination_root and not target.startswith(destination_prefix):
            raise RuntimeError("Repository archive contains an unsafe path.")
        if stat.S_ISLNK(member.external_attr >> 16):
            raise RuntimeError("Repository archive contains an unsupported symbolic link.")
        if (
            member.file_size > 0
            and member.file_size / max(member.compress_size, 1)
            > config.MAX_UPLOAD_COMPRESSION_RATIO
        ):
            raise RuntimeError("Repository archive contains an unsafe compression ratio.")
    zip_file.extractall(destination_root)


def _validate_source_tree(path: str) -> None:
    """Reject links, special files, and oversized repository trees.

    Repository scanners and build planners must never be able to follow a
    tenant-controlled link into worker storage.  Archive extraction already
    rejects links, but native Git checkouts and uploaded directories need the
    same boundary before they are handed to any downstream tool.
    """

    root = os.path.abspath(path)
    if os.path.islink(root) or not os.path.isdir(root):
        raise RuntimeError("Repository source must be a regular directory without symbolic links.")

    maximum_entries = int(config.MAX_UPLOAD_ARCHIVE_FILES)
    maximum_bytes = int(config.MAX_UPLOAD_UNCOMPRESSED_MB) * 1024 * 1024
    entries_seen = 0
    bytes_seen = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as iterator:
                for entry in iterator:
                    entries_seen += 1
                    if entries_seen > maximum_entries:
                        raise RuntimeError("Repository source contains too many filesystem entries.")
                    if entry.is_symlink():
                        raise RuntimeError("Repository source contains an unsupported symbolic link.")
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(entry.path)
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        raise RuntimeError("Repository source contains an unsupported special file.")
                    bytes_seen += entry.stat(follow_symlinks=False).st_size
                    if bytes_seen > maximum_bytes:
                        raise RuntimeError("Repository source exceeds the allowed expanded size.")
        except RuntimeError:
            raise
        except OSError as error:
            raise RuntimeError(
                f"Repository source could not be validated: {type(error).__name__}."
            ) from error


def get_repo_path(full_name: str, workspace_key: str | None = None) -> str:
    """Return a managed path for a repository.

    Deployment callers supply their immutable deployment ID as ``workspace_key``
    so concurrent releases of the same repository never share build files.
    """
    full_name = _validated_repository_name(full_name)
    if workspace_key is not None:
        safe_key = _validated_workspace_key(workspace_key)
        return os.path.join(WORKSPACE_DIR, "deployments", safe_key)
    folder_name = full_name.replace("/", "_")
    return os.path.join(WORKSPACE_DIR, folder_name)


def _assert_managed_path(path: str) -> str:
    """Resolve a path and prove that it is a child of WORKSPACE_DIR."""
    workspace_root = os.path.abspath(WORKSPACE_DIR)
    target = os.path.abspath(path)
    try:
        contained = os.path.commonpath([workspace_root, target]) == workspace_root
    except ValueError:
        contained = False
    if not contained or target == workspace_root:
        raise ValueError("Refusing to operate outside the managed workspace.")
    return target


def cleanup_workspace(path: str) -> None:
    """Safely remove one managed repository workspace."""
    target = _assert_managed_path(path)
    if not os.path.lexists(target):
        return
    if os.path.islink(target):
        os.unlink(target)
        return
    real_root = os.path.realpath(WORKSPACE_DIR)
    real_target = os.path.realpath(target)
    if os.path.commonpath([real_root, real_target]) != real_root:
        raise ValueError("Refusing to remove a workspace that resolves outside the managed root.")
    shutil.rmtree(target)


def prepare_local_source(source_path: str, workspace_key: str) -> str:
    """Copy uploaded source into an isolated, disposable deployment workspace."""
    if os.path.islink(os.path.abspath(source_path)):
        raise RuntimeError("Uploaded source path must not be a symbolic link.")
    source = os.path.realpath(source_path)
    if not os.path.isdir(source):
        raise RuntimeError("Uploaded source path is missing or is not a directory.")
    _validate_source_tree(source)
    destination = get_repo_path("local/upload", workspace_key)
    cleanup_workspace(destination)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    try:
        # Preserve any link that appears in the small validation/copy race so
        # the destination validation rejects it instead of following it into
        # an external worker path.
        shutil.copytree(source, destination, symlinks=True)
        _validate_source_tree(destination)
    except Exception:
        cleanup_workspace(destination)
        raise
    return destination


def clone_repo(
    full_name: str,
    token: str | None = None,
    *,
    branch: str | None = None,
    commit_sha: str | None = None,
    workspace_key: str | None = None,
) -> str:
    """Clones a GitHub repository to the local workspace and returns its path.
    Falls back to zipball download if git binary is not present or clone fails.
    """
    full_name = _validated_repository_name(full_name)
    selected_branch = _validated_branch_name(branch) if branch is not None else None
    selected_commit = _validated_commit_sha(commit_sha) if commit_sha is not None else None
    repo_path = get_repo_path(full_name, workspace_key)

    # Clean existing directory if present
    cleanup_workspace(repo_path)
    os.makedirs(os.path.dirname(repo_path), exist_ok=True)

    clone_url = f"https://github.com/{full_name}.git"

    branch_description = f" at branch {selected_branch}" if selected_branch else ""
    print(f"Cloning {full_name}{branch_description} to {repo_path}...")

    # Check if git is available
    git_available = shutil.which("git") is not None
    if git_available:
        try:
            environment = _git_environment(token)
            if selected_commit:
                commands = [
                    ["git", "init", repo_path],
                    ["git", "-C", repo_path, "remote", "add", "origin", clone_url],
                    ["git", "-C", repo_path, "fetch", "--depth", "1", "origin", selected_commit],
                    ["git", "-C", repo_path, "checkout", "--detach", selected_commit],
                    ["git", "-C", repo_path, "rev-parse", "HEAD"],
                ]
                results = []
                for command in commands:
                    result = subprocess.run(
                        command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=60,
                        env=environment,
                    )
                    results.append(result)
                    if result.returncode != 0:
                        break
                verified_revision = results[-1].stdout.strip().lower() if len(results) == len(commands) else ""
                if len(results) == len(commands) and verified_revision == selected_commit:
                    try:
                        _validate_source_tree(repo_path)
                    except Exception:
                        cleanup_workspace(repo_path)
                        raise
                    print(f"Checked out immutable commit {selected_commit} to {repo_path}")
                    return repo_path
                exit_code = results[-1].returncode if results else "unknown"
                print(
                    f"Immutable git checkout failed with exit code {exit_code}. "
                    "Trying zipball fallback."
                )
            else:
                command = ["git", "clone", "--depth", "1"]
                if selected_branch:
                    command.extend(["--branch", selected_branch, "--single-branch"])
                command.extend([clone_url, repo_path])
                res = subprocess.run(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=60,
                    env=environment,
                )
                if res.returncode == 0:
                    try:
                        _validate_source_tree(repo_path)
                    except Exception:
                        cleanup_workspace(repo_path)
                        raise
                    print(f"Cloned successfully to {repo_path}")
                    return repo_path
                print(f"git clone failed with exit code {res.returncode}. Trying zipball fallback.")
        except Exception as e:
            print(f"git clone error: {e}. Trying zipball fallback.")
    else:
        print("git executable not found on PATH. Using zipball fallback.")

    # Fallback to ZIP download
    cleanup_workspace(repo_path)
    print(f"Downloading zipball fallback for {full_name}...")
    temp_extract_dir = repo_path + "_temp"
    try:
        import urllib.request
        import zipfile
        import tempfile

        # An explicitly selected branch must never silently fall back to main.
        candidate_revisions = (
            [selected_commit]
            if selected_commit
            else ([selected_branch] if selected_branch else ["main", "master"])
        )
        for candidate_revision in candidate_revisions:
            try:
                cleanup_workspace(repo_path)
                cleanup_workspace(temp_extract_dir)
                encoded_revision = quote(candidate_revision, safe="")
                url = f"https://api.github.com/repos/{full_name}/zipball/{encoded_revision}"
                req = urllib.request.Request(url)
                req.add_header("User-Agent", "ZeroOps-AI-Deployment")
                if token:
                    req.add_header("Authorization", f"Bearer {token}")

                max_archive_bytes = config.MAX_CODE_UPLOAD_MB * 1024 * 1024
                with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as archive:
                    with urllib.request.urlopen(req, timeout=60) as response:
                        content_length = getattr(response, "headers", {}).get("Content-Length")
                        if content_length and int(content_length) > max_archive_bytes:
                            raise RuntimeError("Repository archive exceeds the allowed download size.")
                        downloaded = 0
                        while True:
                            chunk = response.read(1024 * 1024)
                            if not chunk:
                                break
                            downloaded += len(chunk)
                            if downloaded > max_archive_bytes:
                                raise RuntimeError("Repository archive exceeds the allowed download size.")
                            archive.write(chunk)
                    archive.seek(0)
                    with zipfile.ZipFile(archive) as zip_ref:
                        os.makedirs(temp_extract_dir, exist_ok=True)
                        _safe_extract(zip_ref, temp_extract_dir)

                # Move the single extracted repository root into its isolated workspace.
                if not os.path.isdir(temp_extract_dir):
                    raise RuntimeError("GitHub archive extraction did not produce a repository.")
                subdirs = [
                    entry
                    for entry in os.listdir(temp_extract_dir)
                    if os.path.isdir(os.path.join(temp_extract_dir, entry))
                ]
                if len(subdirs) != 1:
                    raise RuntimeError("GitHub archive did not contain one repository root.")
                src_dir = os.path.join(temp_extract_dir, subdirs[0])
                shutil.copytree(src_dir, repo_path)
                _validate_source_tree(repo_path)
                cleanup_workspace(temp_extract_dir)
                print(f"Successfully extracted zipball to {repo_path}")
                return repo_path
            except Exception as branch_err:
                cleanup_workspace(repo_path)
                cleanup_workspace(temp_extract_dir)
                print(f"Zipball fallback failed for revision {candidate_revision}: {branch_err}")
                continue

        attempted = selected_commit or selected_branch or "main and master"
        raise RuntimeError(f"GitHub zipball download failed for {attempted}.")
    except Exception as e:
        cleanup_workspace(repo_path)
        cleanup_workspace(temp_extract_dir)
        raise RuntimeError(f"Unable to fetch repository '{full_name}' via clone or zipball: {e}") from e


def get_changed_files(
    repo_path: str,
    baseline_sha: str,
    current_sha: str,
    token: str | None = None,
    *,
    max_paths: int = _MAX_CHANGED_PATHS,
) -> tuple[str, ...] | None:
    """Return a bounded immutable Git diff, or ``None`` when Git metadata is absent.

    A ZIP source archive intentionally has no Git object database.  Callers
    must treat ``None`` as unavailable evidence and use repository fingerprints
    rather than silently claiming that no files changed.
    """

    target = _assert_managed_path(repo_path)
    baseline = _validated_commit_sha(baseline_sha)
    current = _validated_commit_sha(current_sha)
    if max_paths < 1:
        raise ValueError("max_paths must be positive")
    if not os.path.isdir(os.path.join(target, ".git")):
        return None
    executable = shutil.which("git")
    if not executable:
        return None

    environment = _git_environment(token)
    exists = subprocess.run(
        [executable, "-C", target, "cat-file", "-e", f"{baseline}^{{commit}}"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=30,
        env=environment,
        check=False,
    )
    if exists.returncode != 0:
        fetched = subprocess.run(
            [executable, "-C", target, "fetch", "--depth", "1", "origin", baseline],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
            env=environment,
            check=False,
        )
        if fetched.returncode != 0:
            return None

    result = subprocess.run(
        [
            executable,
            "-C",
            target,
            "diff",
            "--name-only",
            "--no-renames",
            "--diff-filter=ACDMRTUXB",
            baseline,
            current,
            "--",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=60,
        env=environment,
        check=False,
    )
    if result.returncode != 0:
        return None
    paths = tuple(sorted({line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}))
    if len(paths) > max_paths:
        raise RuntimeError("Git diff contains more paths than the change detector can safely represent.")
    if any(path.startswith("/") or ".." in path.split("/") or "\x00" in path for path in paths):
        raise RuntimeError("Git returned an unsafe repository-relative path.")
    return paths

def get_branches(full_name: str, token: str = None) -> list[str]:
    """Fetch remote branches for a repository."""
    full_name = _validated_repository_name(full_name)
    import shutil
    import subprocess
    
    # Try git first if available
    git_available = shutil.which("git") is not None
    if git_available:
        url = f"https://github.com/{full_name}.git"

        try:
            res = subprocess.run(
                ["git", "ls-remote", "--heads", url],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
                env=_git_environment(token),
            )
            if res.returncode == 0:
                branches = []
                for line in res.stdout.strip().split("\n"):
                    if line:
                        ref = line.split("\t")[1]
                        branch_name = ref.replace("refs/heads/", "")
                        branches.append(branch_name)
                return branches
        except Exception:
            pass

    # Fallback to GitHub API branches endpoint using urllib
    print(f"git ls-remote failed or git missing. Querying branches API for {full_name}...")
    try:
        import urllib.request
        import json
        url = f"https://api.github.com/repos/{full_name}/branches?per_page=100"
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "ZeroOps-AI-Deployment")
        req.add_header("Accept", "application/vnd.github+json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
            
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            branches = [b.get("name") for b in data if b.get("name")]
            return branches
    except Exception as e:
        print(f"GitHub branches API fallback failed: {e}")
        pass

    return []
