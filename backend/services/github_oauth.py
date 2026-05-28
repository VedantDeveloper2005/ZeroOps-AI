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
import secrets
from typing import Optional

import httpx
from cryptography.fernet import Fernet

try:
    from backend import config
except ImportError:
    import config

logger = logging.getLogger("zeroops.github_oauth")

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


def get_authorization_url(state: str) -> str:
    """Build the GitHub OAuth authorization URL."""
    scopes = config.GITHUB_OAUTH_SCOPES
    return (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={config.GITHUB_CLIENT_ID}"
        f"&scope={scopes}"
        f"&state={state}"
    )


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
        # Last resort: first email
        if emails:
            return emails[0].get("email")
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
            return ["main"]

        branches = response.json()
        return [b.get("name", "") for b in branches if b.get("name")]
