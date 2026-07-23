from contextlib import asynccontextmanager
from fastapi import APIRouter, FastAPI

from app.core.config import settings
from app.core.database import db
from app.users.router.auth import router as user_auth_router
from app.users.router.profile import router as profile_router
from app.users.router.session_auth import router as session_auth_router
from app.users.router.session_auth import sessions_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect(dsn=settings.DATABASE_URL)
    yield
    await db.disconnect()


app = FastAPI(
    title="SuperWallet API",
    description="Production-grade digital wallet backend",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# 1. Agzybirlikli V1 Root Router
v1_router = APIRouter(
    prefix="/api/v1",
    responses={
        401: {"description": "Unauthorized"},
        429: {"description": "Too Many Requests"},
        500: {"description": "Internal Server Error"},
    },
)

# 2. Modul Router-lerini baglamak
v1_router.include_router(
    user_auth_router,
    prefix="/auth",
    tags=["Auth"],
)
v1_router.include_router(
    session_auth_router,
    prefix="/auth/session",
    tags=["Session Auth"],
)
v1_router.include_router(
    sessions_router,
    prefix="/sessions",
    tags=["Sessions Management"],
)
v1_router.include_router(
    profile_router,
    prefix="/users/me",
    tags=["User Profile"],
)

# 3. V1 Router-i Esasy App-a goşmak
app.include_router(v1_router)


# 4. Health Check Endpoint
@app.get("/", tags=["System"])
async def health_check():
    return {"status": "ok", "service": "SuperWallet API"}