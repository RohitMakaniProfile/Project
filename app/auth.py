"""Authentication dependencies: JWT creation, validation, and user extraction."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import User, UserRole
from app.logging_config import get_logger

logger = get_logger(__name__)
security = HTTPBearer(auto_error=False)


def create_jwt_token(
    user_id: uuid.UUID,
    organisation_id: uuid.UUID,
    role: str,
) -> str:
    """Create a signed JWT token for a user."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "org_id": str(organisation_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(hours=settings.JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_jwt_token(token: str) -> dict:
    """Decode and verify a JWT token. Raises JWTError on failure."""
    settings = get_settings()
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Dependency that extracts and validates the JWT, then loads the user from DB.
    Returns the User ORM object with organisation eagerly loaded.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "authentication_required",
                "message": "JWT token is missing from the request.",
                "request_id": str(request.state.request_id),
            },
        )

    token = credentials.credentials
    try:
        payload = decode_jwt_token(token)
    except JWTError as e:
        logger.warning("jwt_validation_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_token",
                "message": "JWT token is expired or has been tampered with.",
                "request_id": str(request.state.request_id),
            },
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_token",
                "message": "Token payload is missing required fields.",
                "request_id": str(request.state.request_id),
            },
        )

    result = await db.execute(
        select(User).where(User.id == uuid.UUID(user_id))
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "user_not_found",
                "message": "The user associated with this token no longer exists.",
                "request_id": str(request.state.request_id),
            },
        )

    return user


async def require_admin(
    request: Request,
    user: User = Depends(get_current_user),
) -> User:
    """Dependency that requires the user to have admin role."""
    if user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "forbidden",
                "message": "This action requires admin privileges.",
                "request_id": str(request.state.request_id),
            },
        )
    return user
