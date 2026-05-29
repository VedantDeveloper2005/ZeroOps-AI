import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Request, Response, HTTPException, Depends, status
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
    """Generate signed JWT access token with detailed logging (15 min expiry)."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire, "type": "access"})
    try:
        encoded_jwt = jwt.encode(to_encode, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)
        logger.info(f"Access JWT generated: SUCCESS. Sub: {to_encode.get('sub')}")
        return encoded_jwt
    except Exception as e:
        logger.error(f"JWT access token generation failed: {e}")
        raise

def create_refresh_token(data: dict) -> str:
    """Generate signed JWT refresh token with 7 days expiry."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=7)
    to_encode.update({"exp": expire, "type": "refresh"})
    try:
        encoded_jwt = jwt.encode(to_encode, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)
        logger.info(f"Refresh JWT generated: SUCCESS. Sub: {to_encode.get('sub')}")
        return encoded_jwt
    except Exception as e:
        logger.error(f"JWT refresh token generation failed: {e}")
        raise

async def get_current_user(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> User:
    """
    Dependency to authenticate request and get the current user.
    Uses 15-minute Access Token and 7-day Refresh Token with transparent rotation.
    """
    from jose import ExpiredSignatureError
    
    token = request.cookies.get("session_token")
    
    # Fallback to Authorization Bearer header if cookie is missing
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ")[1]

    user = None
    
    if token:
        try:
            payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
            user_id: str = payload.get("sub")
            token_type: str = payload.get("type", "access")
            
            if user_id and token_type == "access":
                # Verify user in database
                import uuid
                try:
                    user_uuid = uuid.UUID(user_id)
                    result = await db.execute(select(User).filter(User.id == user_uuid))
                    user = result.scalars().first()
                except ValueError:
                    pass
        except ExpiredSignatureError:
            # Access token is expired, we will attempt transparent rotation below
            pass
        except JWTError:
            pass

    # If access token was missing, expired, or invalid, try to rotate using refresh token
    if not user:
        refresh_token = request.cookies.get("refresh_token")
        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication credentials were not provided or have expired.",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        try:
            refresh_payload = jwt.decode(refresh_token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
            user_id = refresh_payload.get("sub")
            token_type = refresh_payload.get("type")
            
            if not user_id or token_type != "refresh":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid refresh token type.",
                )
                
            import uuid
            user_uuid = uuid.UUID(user_id)
            # Query user matching the user ID and active refresh token
            result = await db.execute(select(User).filter(User.id == user_uuid, User.refresh_token == refresh_token))
            user = result.scalars().first()
            
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Session has expired or has been revoked.",
                )
                
            # Access token rotation: Issue a new access token
            new_access_token = create_access_token(data={"sub": str(user.id)})
            is_prod = config.APP_ENV == "production"
            response.set_cookie(
                key="session_token",
                value=new_access_token,
                httponly=True,
                max_age=15 * 60,  # 15 minutes
                samesite="none" if is_prod else "lax",
                secure=is_prod
            )
            logger.info(f"Transparent access token rotation successful for sub: {user.id}")
        except ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token expired. Please log in again.",
            )
        except (JWTError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials.",
            )

    return user
