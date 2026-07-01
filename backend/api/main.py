"""
AI Career Copilot — FastAPI Application Entry Point
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from core.config import get_settings
from api.routes import resumes, suggestions

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
# Vercel gives every deployment (production + every branch preview) its own
# unique *.vercel.app subdomain under the team's namespace. Requiring an
# exact FRONTEND_URL match means CORS breaks every time a different preview
# URL is used. Allow anything under this specific Vercel team's subdomain
# (not *.vercel.app broadly — that's a shared multi-tenant domain and would
# let any other developer's Vercel-hosted app make credentialed requests
# here too). FRONTEND_URL still works as an extra explicit origin, e.g. for
# a custom domain later, or if your production URL doesn't match this regex.
VERCEL_TEAM_ORIGIN_REGEX = r"^https://.*gargeypatel123-2282s-projects\.vercel\.app$"

# Confirmed production domain — doesn't match the regex above since Vercel's
# stable production URL for this project doesn't include the team slug.
# Hardcoded rather than relying solely on the FRONTEND_URL env var being
# entered correctly, so a typo in Render's dashboard can't break this again.
KNOWN_PRODUCTION_ORIGIN = "https://ai-career-copilot-taupe-five.vercel.app"

allowed_origins = (
    ["*"]
    if settings.is_development
    else list({KNOWN_PRODUCTION_ORIGIN, *[o for o in [settings.frontend_url] if o]})
)
allow_origin_regex = None if settings.is_development else VERCEL_TEAM_ORIGIN_REGEX


# ── Global Error Handler ─────────────────────────────────────────────────────
# A plain @app.exception_handler(Exception) gets special-cased by Starlette:
# it's pulled out into ServerErrorMiddleware, which sits OUTSIDE
# CORSMiddleware in the stack, so its responses never get CORS headers —
# the browser can't read them and shows a generic network failure with zero
# detail instead of the real error. Using an actual middleware instead, and
# registering it BEFORE CORSMiddleware below (Starlette builds the stack in
# reverse-add order, so this ends up INSIDE CORSMiddleware), keeps the error
# response flowing back through CORS header injection correctly.
class CatchExceptionsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
            return JSONResponse(status_code=500, content={"detail": f"Internal server error: {exc}"})


app.add_middleware(CatchExceptionsMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=allow_origin_regex,
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


app.include_router(resumes.router,     prefix="/api/resumes",     tags=["Resumes"])
app.include_router(suggestions.router, prefix="/api/suggestions", tags=["Suggestions"])

# ── Future routers (uncomment as you build each phase) ───────────────────────
# from api.routes import auth, users, jobs, admin
# app.include_router(auth.router,    prefix="/api/auth",    tags=["Auth"])
# app.include_router(users.router,   prefix="/api/users",   tags=["Users"])
# app.include_router(jobs.router,    prefix="/api/jobs",    tags=["Jobs"])
# app.include_router(admin.router,   prefix="/api/admin",   tags=["Admin"])
