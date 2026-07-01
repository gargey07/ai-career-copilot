"""
AI Career Copilot — FastAPI Application Entry Point
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_settings

# ── Logger Setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

settings = get_settings()


# ── App Lifespan ─────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs on startup and shutdown."""
    logger.info(f"🚀 AI Career Copilot API starting — env: {settings.app_env}")
    yield
    logger.info("👋 AI Career Copilot API shutting down")


# ── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="AI Career Copilot API",
    description="Backend API for AI-powered job discovery, matching, and resume generation.",
    version="2.0.0",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
allowed_origins = (
    ["*"]
    if settings.is_development
    else [origin for origin in [settings.frontend_url] if origin]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routes ───────────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
async def root():
    return {
        "status": "ok",
        "service": "AI Career Copilot API",
        "version": "2.0.0",
        "env": settings.app_env,
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy"}


# ── Future routers (uncomment as you build each phase) ───────────────────────
# from api.routes import auth, users, jobs, resumes, admin
# app.include_router(auth.router,    prefix="/api/auth",    tags=["Auth"])
# app.include_router(users.router,   prefix="/api/users",   tags=["Users"])
# app.include_router(jobs.router,    prefix="/api/jobs",    tags=["Jobs"])
# app.include_router(resumes.router, prefix="/api/resumes", tags=["Resumes"])
# app.include_router(admin.router,   prefix="/api/admin",   tags=["Admin"])
