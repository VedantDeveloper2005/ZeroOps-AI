"""Authentication primitives for ZeroOps.

Session and MFA secrets only ever travel in HttpOnly cookies or encrypted
database columns. This module deliberately contains no browser storage logic.
"""

import base64
import hashlib
import hmac
import logging
import secrets
import struct
import time
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote

import bcrypt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, Request, Response, status
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

try:
    from backend import config
    from backend.database import get_db
    from backend.models import User
except ImportError:
    import config
    from database import get_db
    from models import User


logger = logging.getLogger("zeroops.auth")

ACCESS_COOKIE = "session_token"
REFRESH_COOKIE = "refresh_token"
MFA_CHALLENGE_COOKIE = "mfa_challenge"
PHONE_VERIFICATION_CHALLENGE_COOKIE = "phone_verification_challenge"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Compare a password with a bcrypt hash without logging credential details."""
    if not hashed_password:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        logger.warning("Password verification failed because the stored hash is invalid.")
        return False


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt's secure default work factor."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _encode_token(data: dict, token_type: str, expires_delta: timedelta) -> str:
    now = datetime.utcnow()
    payload = data.copy()
    payload.update(
        {
            "type": token_type,
            "iat": now,
            "exp": now + expires_delta,
            "jti": secrets.token_urlsafe(24),
        }
    )
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a short-lived access token."""
    return _encode_token(
        data,
        "access",
        expires_delta or timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(data: dict) -> str:
    """Create a refresh token that is rotated whenever it is used."""
    return _encode_token(data, "refresh", timedelta(days=config.REFRESH_TOKEN_EXPIRE_DAYS))


def create_mfa_challenge_token(user_id: str, challenge_id: str) -> str:
    """Create a five-minute, single-use pre-authentication MFA challenge."""
    return _encode_token(
        {"sub": user_id, "challenge_id": challenge_id},
        "mfa_challenge",
        timedelta(minutes=config.MFA_CHALLENGE_EXPIRE_MINUTES),
    )


def create_phone_verification_challenge_token(
    user_id: str,
    challenge_id: str,
    context: str,
) -> str:
    """Create a short-lived, HttpOnly phone-verification challenge."""
    return _encode_token(
        {"sub": user_id, "challenge_id": challenge_id, "context": context},
        "phone_verification",
        timedelta(minutes=config.PHONE_OTP_EXPIRE_MINUTES),
    )


def hash_refresh_token(token: str) -> str:
    """Hash high-entropy refresh tokens before persisting them."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _cookie_options(max_age: int) -> dict:
    return {
        "httponly": True,
        "secure": config.IS_PRODUCTION,
        "samesite": "none" if config.IS_PRODUCTION else "lax",
        "max_age": max_age,
        "path": "/",
    }


def set_session_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        **_cookie_options(config.ACCESS_TOKEN_EXPIRE_MINUTES * 60),
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        **_cookie_options(config.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60),
    )


def clear_session_cookies(response: Response) -> None:
    options = _cookie_options(0)
    response.delete_cookie(ACCESS_COOKIE, path=options["path"], secure=options["secure"], samesite=options["samesite"], httponly=True)
    response.delete_cookie(REFRESH_COOKIE, path=options["path"], secure=options["secure"], samesite=options["samesite"], httponly=True)


def set_mfa_challenge_cookie(response: Response, challenge_token: str) -> None:
    response.set_cookie(
        MFA_CHALLENGE_COOKIE,
        challenge_token,
        **_cookie_options(config.MFA_CHALLENGE_EXPIRE_MINUTES * 60),
    )


def clear_mfa_challenge_cookie(response: Response) -> None:
    options = _cookie_options(0)
    response.delete_cookie(MFA_CHALLENGE_COOKIE, path=options["path"], secure=options["secure"], samesite=options["samesite"], httponly=True)


def set_phone_verification_challenge_cookie(response: Response, challenge_token: str) -> None:
    response.set_cookie(
        PHONE_VERIFICATION_CHALLENGE_COOKIE,
        challenge_token,
        **_cookie_options(config.PHONE_OTP_EXPIRE_MINUTES * 60),
    )


def clear_phone_verification_challenge_cookie(response: Response) -> None:
    options = _cookie_options(0)
    response.delete_cookie(
        PHONE_VERIFICATION_CHALLENGE_COOKIE,
        path=options["path"],
        secure=options["secure"],
        samesite=options["samesite"],
        httponly=True,
    )


def get_session_tokens(user_id: str) -> tuple[str, str]:
    """Return an access/refresh pair for a fully authenticated user."""
    access_token = create_access_token({"sub": user_id})
    refresh_token = create_refresh_token({"sub": user_id})
    return access_token, refresh_token


def _get_fernet() -> Fernet:
    """Get the dedicated MFA cipher, with a safe compatibility fallback.

    Existing deployments can enable MFA without a disruptive secret migration.
    Production deployments should set MFA_ENCRYPTION_KEY to a separate Fernet
    key so MFA material is not coupled to the JWT signing secret.
    """
    configured_key = getattr(config, "MFA_ENCRYPTION_KEY", "")
    if configured_key:
        return Fernet(configured_key.encode("utf-8"))
    derived_key = base64.urlsafe_b64encode(hashlib.sha256(config.JWT_SECRET.encode("utf-8")).digest())
    return Fernet(derived_key)


def encrypt_mfa_secret(secret: str) -> str:
    return _get_fernet().encrypt(secret.encode("utf-8")).decode("utf-8")


def decrypt_mfa_secret(encrypted_secret: str) -> Optional[str]:
    try:
        return _get_fernet().decrypt(encrypted_secret.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        logger.error("Unable to decrypt an MFA secret. The account must re-enroll MFA.")
        return None


def generate_totp_secret() -> str:
    """Create a 160-bit Base32 TOTP secret compatible with authenticator apps."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def build_totp_uri(secret: str, email: str) -> str:
    label = quote(f"{config.MFA_ISSUER}:{email}", safe="")
    issuer = quote(config.MFA_ISSUER, safe="")
    return f"otpauth://totp/{label}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"


def _hotp(secret: str, counter: int) -> str:
    padding = "=" * (-len(secret) % 8)
    key = base64.b32decode((secret + padding).upper(), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{binary % 1_000_000:06d}"


def verify_totp_code(secret: str, code: str, valid_window: int = 1) -> Optional[int]:
    """Return the matching TOTP time step, allowing one step for clock drift."""
    normalized = "".join(code.split())
    if len(normalized) != 6 or not normalized.isdigit():
        return None

    current_counter = int(time.time() // 30)
    for counter in range(current_counter - valid_window, current_counter + valid_window + 1):
        if counter >= 0 and hmac.compare_digest(_hotp(secret, counter), normalized):
            return counter
    return None


def normalize_recovery_code(code: str) -> str:
    return "".join(char for char in code.upper() if char.isalnum())


def generate_recovery_codes(count: int = 10) -> tuple[list[str], list[str]]:
    """Generate one-time recovery codes and bcrypt hashes for storage."""
    raw_codes = [secrets.token_hex(4).upper() for _ in range(count)]
    codes = [f"{code[:4]}-{code[4:]}" for code in raw_codes]
    hashes = [get_password_hash(normalize_recovery_code(code)) for code in codes]
    return codes, hashes


def consume_recovery_code(user: User, code: str) -> bool:
    normalized = normalize_recovery_code(code)
    if len(normalized) != 8:
        return False

    hashes = list(user.mfa_recovery_code_hashes or [])
    for index, code_hash in enumerate(hashes):
        if verify_password(normalized, code_hash):
            hashes.pop(index)
            user.mfa_recovery_code_hashes = hashes
            return True
    return False


def is_recent_primary_authentication(user: User) -> bool:
    if not user.last_primary_auth_at:
        return False
    return datetime.utcnow() - user.last_primary_auth_at <= timedelta(minutes=config.MFA_REAUTH_WINDOW_MINUTES)


# ──────────────────────────────────────────────
# EMAIL VERIFICATION TOKENS
# ──────────────────────────────────────────────

def create_verification_token() -> str:
    """Create a URL-safe token for email verification links."""
    return secrets.token_urlsafe(48)


def hash_verification_token(token: str) -> str:
    """Hash a verification token with SHA-256 for safe database storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_verification_token(token: str, stored_hash: str) -> bool:
    """Compare a raw verification token against a stored SHA-256 hash."""
    return hmac.compare_digest(
        hashlib.sha256(token.encode("utf-8")).hexdigest(),
        stored_hash,
    )


# ──────────────────────────────────────────────
# EMAIL OTP
# ──────────────────────────────────────────────

def generate_email_otp(length: int = 6) -> str:
    """Generate a cryptographically random numeric OTP code."""
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def mask_phone_number(phone_number: str) -> str:
    """Return a minimal, non-sensitive hint suitable for the verification UI."""
    if len(phone_number) <= 4:
        return "••••"
    return f"••••{phone_number[-4:]}"


def hash_otp(otp: str) -> str:
    """Hash an OTP code with bcrypt for secure storage."""
    return get_password_hash(otp)


def verify_otp(otp: str, otp_hash: str) -> bool:
    """Verify a raw OTP code against a stored bcrypt hash."""
    return verify_password(otp.strip(), otp_hash)



def decode_mfa_challenge(request: Request) -> dict:
    token = request.cookies.get(MFA_CHALLENGE_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your verification session has expired. Sign in again.")
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
    except JWTError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your verification session has expired. Sign in again.") from error
    if payload.get("type") != "mfa_challenge" or not payload.get("sub") or not payload.get("challenge_id"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your verification session is invalid. Sign in again.")
    return payload


def decode_phone_verification_challenge(request: Request) -> dict:
    token = request.cookies.get(PHONE_VERIFICATION_CHALLENGE_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your phone verification session has expired. Start again.")
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
    except JWTError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your phone verification session has expired. Start again.") from error
    if (
        payload.get("type") != "phone_verification"
        or not payload.get("sub")
        or not payload.get("challenge_id")
        or payload.get("context") not in {"signup", "login"}
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your phone verification session is invalid. Start again.")
    return payload


async def get_current_user(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authenticate a full session and rotate refresh tokens when used."""
    access_token = request.cookies.get(ACCESS_COOKIE)
    if not access_token:
        # Bearer support is retained only for the CLI and external API clients.
        authorization = request.headers.get("Authorization", "")
        if authorization.lower().startswith("bearer "):
            access_token = authorization.split(" ", 1)[1]

    if access_token:
        try:
            payload = jwt.decode(access_token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
            if payload.get("type") == "access" and payload.get("sub"):
                import uuid

                user_id = uuid.UUID(payload["sub"])
                result = await db.execute(select(User).filter(User.id == user_id))
                user = result.scalars().first()
                if user:
                    return user
        except (JWTError, ValueError):
            # An expired or invalid access token may still be renewed by a valid
            # HttpOnly refresh cookie. Bearer tokens never trigger this path.
            pass

    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided or have expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        refresh_payload = jwt.decode(refresh_token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
        if refresh_payload.get("type") != "refresh" or not refresh_payload.get("sub"):
            raise JWTError("Invalid refresh token type")

        import uuid

        user_id = uuid.UUID(refresh_payload["sub"])
        result = await db.execute(select(User).filter(User.id == user_id))
        user = result.scalars().first()
        expected_hash = hash_refresh_token(refresh_token)
        # The raw-token comparison is a one-time compatibility path for sessions
        # created before refresh-token hashing was introduced.
        stored_token = user.refresh_token if user else None
        valid_token = bool(
            stored_token
            and (
                hmac.compare_digest(stored_token, expected_hash)
                or hmac.compare_digest(stored_token, refresh_token)
            )
        )
        if not user or not valid_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has expired or has been revoked.")

        new_access_token, new_refresh_token = get_session_tokens(str(user.id))
        user.refresh_token = hash_refresh_token(new_refresh_token)
        await db.commit()
        set_session_cookies(response, new_access_token, new_refresh_token)
        return user
    except HTTPException:
        raise
    except (JWTError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials.") from error
