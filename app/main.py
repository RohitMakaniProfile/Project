"""NexusAPI — Main application entry point."""
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.logging_config import setup_logging, get_logger
from app.middleware.logging_middleware import RequestLoggingMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.redis_client import close_redis
from app.worker import close_arq_pool
from app.routes.auth_routes import setup_oauth

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown hooks."""
    logger.info("app_starting")
    setup_oauth()
    yield
    logger.info("app_shutting_down")
    await close_redis()
    await close_arq_pool()


app = FastAPI(
    title="NexusAPI",
    description="Multi-Tenant Credit-Gated Backend API",
    version="1.0.0",
    lifespan=lifespan,
)

# ─── Middleware (order matters: outermost first) ──────────────────
settings = get_settings()

# Session middleware required for OAuth state
app.add_middleware(SessionMiddleware, secret_key=settings.JWT_SECRET_KEY)

# Request logging (runs first, wraps everything)
app.add_middleware(RequestLoggingMiddleware)

# Rate limiting
app.add_middleware(RateLimitMiddleware)


# ─── Global exception handlers ───────────────────────────────────
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return structured error responses for validation failures."""
    request_id = str(getattr(request.state, "request_id", uuid.uuid4()))
    errors = exc.errors()
    # Build a human-readable message from validation errors
    messages = []
    for err in errors:
        loc = " → ".join(str(l) for l in err.get("loc", []))
        msg = err.get("msg", "")
        messages.append(f"{loc}: {msg}")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "validation_error",
            "message": "; ".join(messages),
            "request_id": request_id,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all handler: never return raw Python stack traces."""
    request_id = str(getattr(request.state, "request_id", uuid.uuid4()))
    logger.error(
        "unhandled_exception",
        error=str(exc),
        error_type=type(exc).__name__,
        request_id=request_id,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred. Please try again later.",
            "request_id": request_id,
        },
    )


# ─── Include routers ─────────────────────────────────────────────
from app.routes.health import router as health_router
from app.routes.auth_routes import router as auth_router, callback_router as auth_callback_router
from app.routes.credits import router as credits_router
from app.routes.products import router as products_router

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(auth_callback_router)
app.include_router(products_router)
app.include_router(credits_router)


# GET /me at root level
from app.auth import get_current_user
from app.database import get_db
from app.models import Organisation, User
from app.schemas import MeResponse, OrganisationOut, UserOut
from sqlalchemy import select


@app.get("/me")
async def get_me(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """GET /me — returns the authenticated user's profile and organisation."""
    result = await db.execute(
        select(Organisation).where(Organisation.id == user.organisation_id)
    )
    org = result.scalar_one_or_none()
    return MeResponse(
        user=UserOut.model_validate(user),
        organisation=OrganisationOut.model_validate(org),
    )


# ─── Serve frontend ───────────────────────────────────────────
_FRONTEND = Path(__file__).parent.parent / "frontend"

app.mount("/frontend", StaticFiles(directory=str(_FRONTEND)), name="frontend")


@app.get("/", include_in_schema=False)
async def serve_index():
    """Serve the SPA index page."""
    return FileResponse(str(_FRONTEND / "index.html"))
