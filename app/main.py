import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.config.log.cleanup import delete_old_logs
from app.routers import (
    MenuResource,
    UserResource,
    chat,
    client_errors,
    faq,
    login,
    upload,
)
from app.routers import user
from app.routers import RoleResource

from app.config.database.database import engine, init_db
from app.config.log.log_config import get_logger

# Load environment variables early
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

# Rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
logger = get_logger("app_main")

SECURE_RESPONSE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events"""
    scheduler = AsyncIOScheduler()
    try:
        # Startup
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for folder in [
            "logs",
            "logs/client-errors",
            "chromadb",
            "imagefiles",
            "audiofiles",
            "uploadfiles",
            "FAQ",
            "uploads/pdfs",
        ]:
            os.makedirs(os.path.join(BASE_DIR, folder), exist_ok=True)

        scheduler.add_job(delete_old_logs, "interval", days=1)
        scheduler.start()

        await init_db()
        logger.info("Application startup complete")
        yield
    except Exception as exc:
        logger.exception("Unhandled startup/shutdown error: %s", str(exc))
        raise
    finally:
        if scheduler.running:
            scheduler.shutdown()
        logger.info("Application shutdown complete")


# Use lifespan parameter instead of deprecated on_startup/on_shutdown


app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    logger.warning(
        "HTTP exception on %s %s: %s",
        request.method,
        request.url.path,
        exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "status": "error"},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(
        "Validation error on %s %s: %s",
        request.method,
        request.url.path,
        exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "status": "error"},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "status": "error",
        },
    )


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)

    for header, value in SECURE_RESPONSE_HEADERS.items():
        response.headers.setdefault(header, value)

    if request.headers.get("x-forwarded-proto", request.url.scheme) == "https":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )

    return response


# Serve audiofiles directory at /audiofiles
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
audio_dir = os.path.join(BASE_DIR, "audiofiles")
app.mount("/audiofiles", StaticFiles(directory=audio_dir), name="audiofiles")

# Serve uploads/audio directory at /uploads/audio
uploads_audio_dir = os.path.join(BASE_DIR, "uploads", "audio")
app.mount(
    "/uploads/audio", StaticFiles(directory=uploads_audio_dir), name="uploads_audio"
)

# Serve uploads/images directory at /uploads/images
uploads_images_dir = os.path.join(BASE_DIR, "uploads", "images")
app.mount(
    "/uploads/images", StaticFiles(directory=uploads_images_dir), name="uploads_images"
)

# Serve uploads/pdfs directory at /uploads/pdfs
uploads_pdfs_dir = os.path.join(BASE_DIR, "uploads", "pdfs")
os.makedirs(uploads_pdfs_dir, exist_ok=True)
app.mount("/uploads/pdfs", StaticFiles(directory=uploads_pdfs_dir), name="uploads_pdfs")

# Load environment variables from .env
# (already loaded at top of file)

# Get CORS origins from environment variable or use dev defaults
_cors_env = os.getenv("CORS_ORIGINS", "")
if _cors_env:
    cors_origins = [origin.strip() for origin in _cors_env.split(",") if origin.strip()]
else:
    cors_origins = [
        "http://localhost:5173",
        "https://localhost:5173",
        "http://localhost:3000",
        "https://localhost:3000",
    ]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(chat.router)
app.include_router(login.router)
app.include_router(upload.router)
app.include_router(client_errors.router)
app.include_router(user.router)
app.include_router(faq.router)
app.include_router(MenuResource.router)
app.include_router(RoleResource.router)
app.include_router(UserResource.router)


@app.get("/")
async def home():
    return {"status": "Logging system running"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/health/live")
async def health_live():
    return {"status": "alive"}


@app.get("/health/ready")
async def health_ready():
    checks = {
        "database": "ok",
        "logs": "ok",
    }

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Readiness database check failed")
        checks["database"] = "error"

    if not os.path.isdir(os.path.join(BASE_DIR, "logs")):
        checks["logs"] = "error"

    status_code = 200 if all(value == "ok" for value in checks.values()) else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if status_code == 200 else "degraded",
            "checks": checks,
        },
    )
