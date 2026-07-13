from contextlib import asynccontextmanager

from core.database import db
from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    yield
    await db.disconnect()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def hello():
    return {"hello:SO"}
