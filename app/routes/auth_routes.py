"""Google OAuth and JWT authentication routes."""
import uuid
from datetime import datetime, timezone

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from urllib.parse import quote
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_jwt_token, get_current_user
from app.config import get_settings
from app.database import get_db
from app.models import Organisation, User, UserRole
from app.schemas import MeResponse, OrganisationOut, TokenResponse, UserOut
from app.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])
callback_router = APIRouter(tags=["auth"])

oauth = OAuth()


def setup_oauth():
    """Register Google OAuth client. Called during app startup."""
    settings = get_settings()
    oauth.register(
        name="google",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


@router.get("/google")
async def google_login(request: Request):
    """GET /auth/google — redirect the user to Google login."""
    settings = get_settings()
    return await oauth.google.authorize_redirect(request, settings.GOOGLE_REDIRECT_URI)


@callback_router.get("/auth/callback")
async def google_callback(request: Request, db: AsyncSession = Depends(get_db)):
    """
    GET /auth/callback — receives the Google token, extracts email and name.
    Creates org/user if needed; returns a signed JWT.
    """
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        logger.warning("google_auth_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "google_auth_failed",
                "message": f"Google authentication failed: {str(e)}",
                "request_id": str(getattr(request.state, "request_id", "unknown")),
            },
        )

    user_info = token.get("userinfo")
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_google_token",
                "message": "Could not retrieve user information from Google.",
                "request_id": str(getattr(request.state, "request_id", "unknown")),
            },
        )

    email = user_info.get("email")
    name = user_info.get("name", email.split("@")[0] if email else "Unknown")
    google_id = user_info.get("sub")

    if not email or not google_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_google_token",
                "message": "Google token is missing required user information.",
                "request_id": str(getattr(request.state, "request_id", "unknown")),
            },
        )

    # Extract domain from email for organisation matching
    domain = email.split("@")[1].lower()
    slug = domain.replace(".", "-")

    # Check if user already exists
    result = await db.execute(select(User).where(User.google_id == google_id))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        jwt_token = create_jwt_token(
            existing_user.id, existing_user.organisation_id, existing_user.role.value
        )
        return RedirectResponse(url=f"/?token={quote(jwt_token)}", status_code=303)

    # Check if organisation exists for this email domain
    result = await db.execute(select(Organisation).where(Organisation.slug == slug))
    org = result.scalar_one_or_none()

    if org is None:
        # Create a new organisation and make the user admin
        org = Organisation(
            id=uuid.uuid4(),
            name=domain.split(".")[0].title(),
            slug=slug,
            created_at=datetime.now(timezone.utc),
        )
        db.add(org)
        await db.flush()
        role = UserRole.admin
    else:
        role = UserRole.member

    # Create the user
    user = User(
        id=uuid.uuid4(),
        email=email,
        name=name,
        google_id=google_id,
        organisation_id=org.id,
        role=role,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.commit()

    jwt_token = create_jwt_token(user.id, user.organisation_id, user.role.value)
    logger.info(
        "user_authenticated",
        user_id=str(user.id),
        org_id=str(org.id),
        role=role.value,
        is_new=True,
    )
    return RedirectResponse(url=f"/?token={quote(jwt_token)}", status_code=303)
