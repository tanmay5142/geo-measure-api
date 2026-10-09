from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import models  # noqa: F401  (importing it registers the tables)
from app.api.files import router as files_router
from app.database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Geospatial File Measurement API", lifespan=lifespan)
app.include_router(files_router)


@app.get("/health")
def health():
    return {"status": "ok"}