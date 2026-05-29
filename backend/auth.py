import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Request, HTTPException, Depends, status
from jose import jwt, JWTError
import bcrypt
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

# Setup logger
logger = logging.getLogger("zeroops.auth")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Compare plain password against hashed password with detailed logging."""
    if not hashed_password:
        logger.warning("Password verification failed: No stored password hash found.")
        return False
    try:
        plain_bytes = plain_password.encode("utf-8")
        hash_bytes = hashed_password.encode("utf-8")
        
        logger.info(f"Verifying password. Stored Hash Length: {len(hashed_password)}.")
        result = bcrypt.checkpw(plain_bytes, hash_bytes)
        logger.info(f"Password verification status: {'SUCCESS' if result else 'FAILED'}")
        return result
    except Exception as e:
        logger.error(f"Password verification encountered exception: {e}")
        return False

def get_password_hash(password: str) -> str:
    """Hash password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Generate signed JWT access token with detailed logging."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    try:
        encoded_jwt = jwt.encode(to_encode, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)
        logger.info(f"JWT generation status: SUCCESS. Sub: {to_encode.get('sub')}")
        return encoded_jwt
    except Exception as e:
        logger.error(f"JWT generation failed: {e}")
        raise

async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """
    Dependency to authenticate request and get the current user.
    Checks HTTP-only cookie first, fallback to Authorization Bearer header.
    """
    token = request.cookies.get("session_token")
    
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ")[1]
            
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials.",
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials or token expired.",
        )

    # Check if token is blacklisted (logged out)
    try:
        from backend import models
    except ImportError:
        import models
        
    revoked_result = await db.execute(
        select(models.RevokedToken).filter(models.RevokedToken.token == token)
    )
    if revoked_result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired or was logged out.",
        )
        
    # Query database for user
    try:
        import uuid
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID format in token.",
        )
        
    result = await db.execute(select(User).filter(User.id == user_uuid))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User associated with this token does not exist.",
        )
    return user
