"""
GitHub OAuth Service
====================
Handles GitHub OAuth 2.0 flow, token encryption, and GitHub API interactions.
All GitHub access tokens are encrypted at rest using Fernet symmetric encryption.
Tokens are NEVER exposed to the frontend.
"""

import base64
import hashlib
import logging
import re
import secrets
from typing import Optional
from urllib.parse import quote

import httpx
from cryptography.fernet import Fernet

try:
    from backend import config
except ImportError:
    import config

logger = logging.getLogger("zeroops.github_oauth")
_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_COMMIT_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")

# ──────────────────────────────────────────────
# TOKEN ENCRYPTION (Fernet)
# ──────────────────────────────────────────────

def _get_fernet_key() -> bytes:
    """Derive a Fernet-compatible 32-byte URL-safe base64 key from JWT_SECRET."""
    raw = hashlib.sha256(config.JWT_SECRET.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(raw)


def encrypt_token(token: str) -> str:
    """Encrypt a GitHub access token for secure database storage."""
    f = Fernet(_get_fernet_key())
    return f.encrypt(token.encode("utf-8")).decode("utf-8")


def decrypt_token(encrypted: str) -> str:
    """Decrypt a stored GitHub access token for server-side API use."""
    f = Fernet(_get_fernet_key())
    return f.decrypt(encrypted.encode("utf-8")).decode("utf-8")


# ──────────────────────────────────────────────
# OAUTH STATE MANAGEMENT
# ──────────────────────────────────────────────

# In-memory state store for CSRF protection (short-lived, per-process)
# For multi-instance production, replace with Redis or DB-backed store.
_oauth_states: dict[str, bool] = {}


def generate_oauth_state() -> str:
    """Generate a cryptographically random state parameter for CSRF protection."""
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = True
    # Limit state store size (prevent memory leak from abandoned flows)
    if len(_oauth_states) > 1000:
        oldest_keys = list(_oauth_states.keys())[:500]
        for k in oldest_keys:
            _oauth_states.pop(k, None)
    return state


def validate_oauth_state(state: str) -> bool:
    """Validate and consume an OAuth state parameter (one-time use)."""
    if state and state in _oauth_states:
        del _oauth_states[state]
        return True
    return False


def get_authorization_url(state: str, redirect_uri: str = "") -> str:
    """Build the GitHub OAuth authorization URL."""
    scopes = config.GITHUB_OAUTH_SCOPES
    url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={config.GITHUB_CLIENT_ID}"
        f"&scope={scopes}"
        f"&state={state}"
    )
    if redirect_uri:
        from urllib.parse import quote as _quote
        url += f"&redirect_uri={_quote(redirect_uri, safe='')}"
    return url


# ──────────────────────────────────────────────
# OAUTH TOKEN EXCHANGE
# ──────────────────────────────────────────────

async def exchange_code_for_token(code: str) -> Optional[str]:
    """Exchange the authorization code for a GitHub access token."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            "https://github.com/login/oauth/access_token",
            json={
                "client_id": config.GITHUB_CLIENT_ID,
                "client_secret": config.GITHUB_CLIENT_SECRET,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
        if response.status_code != 200:
            logger.error(f"GitHub token exchange failed: HTTP {response.status_code}")
            return None

        data = response.json()
        access_token = data.get("access_token")
        if not access_token:
            error = data.get("error_description", data.get("error", "unknown"))
            logger.error(f"GitHub token exchange error: {error}")
            return None

        logger.info("GitHub OAuth token exchange successful.")
        return access_token


# ──────────────────────────────────────────────
# GITHUB USER API
# ──────────────────────────────────────────────

async def get_github_user(token: str) -> Optional[dict]:
    """Fetch the authenticated GitHub user's profile."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        if response.status_code != 200:
            logger.error(f"GitHub user fetch failed: HTTP {response.status_code}")
            return None
        return response.json()


async def get_github_user_email(token: str) -> Optional[str]:
    """Fetch the authenticated user's primary verified email from GitHub."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://api.github.com/user/emails",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        if response.status_code != 200:
            logger.warning(f"GitHub emails fetch failed: HTTP {response.status_code}")
            return None

        emails = response.json()
        # Find primary verified email
        for email_obj in emails:
            if email_obj.get("primary") and email_obj.get("verified"):
                return email_obj["email"]
        # Fallback: first verified email
        for email_obj in emails:
            if email_obj.get("verified"):
                return email_obj["email"]
        # Do not fall back to an unverified address. The callback treats this
        # value as proof of account email ownership.
        return None


# ──────────────────────────────────────────────
# GITHUB REPOS API
# ──────────────────────────────────────────────

async def get_user_repos(
    token: str,
    page: int = 1,
    per_page: int = 30,
    sort: str = "updated",
    query: Optional[str] = None,
) -> dict:
    """Fetch the authenticated user's repositories with pagination.
    
    Returns:
        dict with keys: repos (list), total_count, page, per_page, has_next
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        # If query provided, use GitHub search API for the user's repos
        if query and query.strip():
            return await _search_user_repos(client, token, query.strip(), page, per_page)

        response = await client.get(
            "https://api.github.com/user/repos",
            params={
                "page": page,
                "per_page": per_page,
                "sort": sort,
                "direction": "desc",
                "affiliation": "owner,collaborator,organization_member",
            },
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        if response.status_code != 200:
            logger.error(f"GitHub repos fetch failed: HTTP {response.status_code}")
            return {"repos": [], "total_count": 0, "page": page, "per_page": per_page, "has_next": False}

        repos_raw = response.json()
        repos = [_format_repo(r) for r in repos_raw]

        # Check if there's a next page via Link header
        link_header = response.headers.get("Link", "")
        has_next = 'rel="next"' in link_header

        return {
            "repos": repos,
            "total_count": len(repos),
            "page": page,
            "per_page": per_page,
            "has_next": has_next,
        }


async def _search_user_repos(
    client: httpx.AsyncClient,
    token: str,
    query: str,
    page: int,
    per_page: int,
) -> dict:
    """Search repositories owned/accessible by the authenticated user."""
    # Use GitHub search API: user:USERNAME query
    # First get the username
    user_response = await client.get(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
    )
    if user_response.status_code != 200:
        return {"repos": [], "total_count": 0, "page": page, "per_page": per_page, "has_next": False}

    username = user_response.json().get("login", "")
    search_query = f"{query} user:{username} fork:true"

    response = await client.get(
        "https://api.github.com/search/repositories",
        params={
            "q": search_query,
            "page": page,
            "per_page": per_page,
            "sort": "updated",
            "order": "desc",
        },
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
    )
    if response.status_code != 200:
        logger.error(f"GitHub repo search failed: HTTP {response.status_code}")
        return {"repos": [], "total_count": 0, "page": page, "per_page": per_page, "has_next": False}

    data = response.json()
    repos = [_format_repo(r) for r in data.get("items", [])]
    total_count = data.get("total_count", 0)
    has_next = (page * per_page) < total_count

    return {
        "repos": repos,
        "total_count": total_count,
        "page": page,
        "per_page": per_page,
        "has_next": has_next,
    }


def _format_repo(repo: dict) -> dict:
    """Normalize a GitHub API repo object into our response format."""
    return {
        "id": repo.get("id"),
        "name": repo.get("name", ""),
        "full_name": repo.get("full_name", ""),
        "description": repo.get("description"),
        "private": repo.get("private", False),
        "language": repo.get("language"),
        "stargazers_count": repo.get("stargazers_count", 0),
        "default_branch": repo.get("default_branch", "main"),
        "updated_at": repo.get("updated_at", ""),
        "html_url": repo.get("html_url", ""),
        "owner_avatar_url": repo.get("owner", {}).get("avatar_url"),
    }


# ──────────────────────────────────────────────
# GITHUB BRANCHES API
# ──────────────────────────────────────────────

async def get_repo_branches(token: str, owner: str, repo: str) -> list[str]:
    """Fetch branches for a specific repository."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/branches",
            params={"per_page": 100},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        if response.status_code != 200:
            logger.warning(f"GitHub branches fetch failed for {owner}/{repo}: HTTP {response.status_code}")
            return []

        branches = response.json()
        return [b.get("name", "") for b in branches if b.get("name")]


async def resolve_branch_commit(
    token: str,
    repo_full_name: str,
    branch: str,
) -> Optional[str]:
    """Resolve a saved GitHub branch to a complete immutable commit SHA."""

    if not token or not _REPOSITORY_PATTERN.fullmatch(repo_full_name or ""):
        return None
    if (
        not isinstance(branch, str)
        or not branch
        or len(branch) > 255
        or branch.startswith(("-", "/"))
        or branch.endswith(("/", ".", ".lock"))
        or ".." in branch
        or "@{" in branch
        or any(ord(char) < 32 or char in " ~^:?*[\\\x7f" for char in branch)
    ):
        return None

    encoded_branch = quote(branch, safe="")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"https://api.github.com/repos/{repo_full_name}/commits/{encoded_branch}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "ZeroOps-AI",
                },
            )
        if response.status_code != 200:
            logger.warning(
                "GitHub commit resolution failed for %s at the saved branch: HTTP %s",
                repo_full_name,
                response.status_code,
            )
            return None
        commit_sha = str(response.json().get("sha") or "")
        return commit_sha.lower() if _COMMIT_PATTERN.fullmatch(commit_sha) else None
    except (httpx.HTTPError, ValueError, TypeError) as error:
        logger.warning("GitHub commit resolution failed for %s: %s", repo_full_name, error)
        return None


# ──────────────────────────────────────────────
# GITHUB REPO CONTENTS & TREES API (NO GIT CLONE)
# ──────────────────────────────────────────────

def build_tree_from_github_items(items: list[dict], max_depth: int = 3) -> str:
    """Helper to convert GitHub git/trees recursive API response into a readable tree string."""
    lines = []
    filtered_items = []
    for item in items:
        path = item.get("path", "")
        parts = path.split("/")
        if len(parts) <= max_depth:
            filtered_items.append(item)
            
    filtered_items.sort(key=lambda x: x.get("path", ""))
    
    for item in filtered_items:
        path = item.get("path", "")
        type_ = item.get("type", "")
        parts = path.split("/")
        indent = "  " * (len(parts) - 1)
        name = parts[-1]
        if type_ == "tree":
            lines.append(f"{indent}📁 {name}/")
        else:
            lines.append(f"{indent}📄 {name}")
    return "\n".join(lines)


async def fetch_github_file_content(client: httpx.AsyncClient, token: str, owner: str, repo: str, path: str, branch: str) -> Optional[str]:
    """Fetch raw file content from GitHub repository without local cloning."""
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3.raw",
        "User-Agent": "ZeroOps-AI"
    }
    try:
        response = await client.get(url, params={"ref": branch}, headers=headers, timeout=8.0)
        if response.status_code == 200:
            return response.text
        return None
    except Exception as e:
        logger.warning(f"Error fetching file content for {path}: {e}")
        return None


def scan_context_for_env_vars(files_context: dict) -> list[str]:
    """Scan loaded config files and .env files for references to environment variables."""
    import re
    vars_found = set()
    js_pattern = re.compile(r'process\.env\.([A-Z0-9_]+)')
    py_pattern = re.compile(r'os\.(?:environ\.get|getenv)\(\s*[\'"]([A-Z0-9_]+)[\'"]')
    
    for filename, content in files_context.items():
        if not content:
            continue
        # If it's a .env or .env.example, parse lines
        basename = filename.split("/")[-1]
        if basename in [".env.example", ".env"]:
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key = line.split("=", 1)[0].strip()
                    if key:
                        vars_found.add(key)
        else:
            # Run regex patterns
            for match in js_pattern.finditer(content):
                vars_found.add(match.group(1))
            for match in py_pattern.finditer(content):
                vars_found.add(match.group(1))
    return list(vars_found)


async def fetch_github_repo_context(token: str, repo_full_name: str, branch: Optional[str] = None) -> dict:
    """Fetch all repository metadata, file tree structure, and select configuration contents.
    Runs concurrently and does not require local git binary or disk clone.
    """
    import asyncio
    parts = repo_full_name.split("/")
    if len(parts) != 2:
        raise ValueError(f"Invalid repository full name format: '{repo_full_name}'")
    owner, repo = parts

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "ZeroOps-AI"
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        # 1. Fetch default branch if not specified
        if not branch:
            repo_url = f"https://api.github.com/repos/{owner}/{repo}"
            resp = await client.get(repo_url, headers=headers)
            if resp.status_code != 200:
                detail_msg = f"Failed to retrieve repository metadata: HTTP {resp.status_code}"
                try:
                    err_json = resp.json()
                    if "message" in err_json:
                        detail_msg = f"GitHub API error: {err_json['message']}"
                except Exception:
                    pass
                raise RuntimeError(detail_msg)
            
            repo_data = resp.json()
            branch = repo_data.get("default_branch", "main")

        # 2. Get recursive tree
        tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}"
        tree_resp = await client.get(tree_url, params={"recursive": "1"}, headers=headers)
        
        if tree_resp.status_code != 200:
            logger.warning(f"Recursive trees API failed for {repo_full_name} branch {branch}: HTTP {tree_resp.status_code}")
            items = []
        else:
            items = tree_resp.json().get("tree", [])

        # Filter file paths
        files_list = [item["path"] for item in items if item.get("type") == "blob"]
        
        # 3. Build tree
        repo_tree = build_tree_from_github_items(items, max_depth=3)
        
        # 4. Identify target files to download
        target_basenames = {
            "package.json", "requirements.txt", "pyproject.toml",
            "Dockerfile", "docker-compose.yml", "README.md",
            ".env.example", ".env", "next.config.js", "next.config.mjs",
            "vite.config.js", "vite.config.mjs", "vite.config.ts", "vite.config.mts",
        }
        
        target_files = []
        workflow_files = []
        for file_path in files_list:
            basename = file_path.split("/")[-1]
            if basename in target_basenames:
                target_files.append(file_path)
            elif file_path.startswith(".github/workflows/") and file_path.endswith((".yml", ".yaml")):
                # Limit workflows to avoid too many requests
                if len(workflow_files) < 2:
                    workflow_files.append(file_path)

        # Inspect only a small, deterministic set of likely client entry files.
        # This gives the analyzer source evidence for UI/runtime claims without
        # downloading an unbounded repository or sending these files to a model.
        client_entries = {
            "src/app.js", "src/app.jsx", "src/app.ts", "src/app.tsx",
            "src/main.js", "src/main.jsx", "src/main.ts", "src/main.tsx",
        }
        client_files = [
            file_path
            for file_path in files_list
            if file_path.replace("\\", "/").lower() in client_entries
        ]

        # Root metadata and the client entry point are the strongest facts for
        # a single application. Put them before nested workspace files so the
        # hard request cap cannot silently drop the source entry point.
        launch_basenames = {
            "package.json", "requirements.txt", "pyproject.toml", "Dockerfile",
            "docker-compose.yml", "next.config.js", "next.config.mjs",
            "vite.config.js", "vite.config.mjs", "vite.config.ts", "vite.config.mts",
        }
        root_launch_targets = [
            path for path in target_files
            if "/" not in path and path.split("/")[-1] in launch_basenames
        ]
        root_supporting_targets = [
            path for path in target_files
            if "/" not in path and path not in root_launch_targets
        ]
        nested_targets = [path for path in target_files if "/" in path]
        files_to_download = list(dict.fromkeys(
            root_launch_targets + client_files + root_supporting_targets + nested_targets + workflow_files
        ))

        # Limit overall downloads
        files_to_download = files_to_download[:12]

        # 5. Fetch contents concurrently
        tasks = [
            fetch_github_file_content(client, token, owner, repo, path, branch)
            for path in files_to_download
        ]
        
        contents = await asyncio.gather(*tasks, return_exceptions=True)
        
        files_context = {}
        for path, content in zip(files_to_download, contents):
            if isinstance(content, str):
                normalized_path = path.replace("\\", "/").lower()
                # Likely client entry points are used only by the deterministic
                # local scanner (the model allow-list excludes them). Keep a
                # bounded but complete-enough view to validate rendered claims.
                limit = 30_000 if normalized_path in client_entries else 3_000
                files_context[path] = content[:limit]

        # 6. Scan variables
        scanned_vars = scan_context_for_env_vars(files_context)

        return {
            "repo_tree": repo_tree,
            "files_context": files_context,
            "files_list": files_list,
            "scanned_vars": scanned_vars,
            "default_branch": branch
        }
