from contextlib import asynccontextmanager
from app.core.config import settings
from app.core.database import db
from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect(dsn=settings.DATABASE_URL)
    yield
    await db.disconnect()


app = FastAPI(
    title="SuperWallet API",
    description="Production-grade digital wallet backend",
    version="1.0.0",
    lifespan=lifespan
)






@app.get("/")
async def hello():
    return {"hello:SO"}
