from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import models  # noqa: F401  (importing it registers the tables)
from app.database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Geospatial File Measurement API", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}