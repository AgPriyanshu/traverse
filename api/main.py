from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, status
from fastapi.responses import JSONResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI()


@app.get("/ping")
async def pong():
    return {"message": "pong"}


@app.post("/generate-embeddings")
async def generate_embeddings(file: UploadFile):
    return JSONResponse(
        {"message": "File accepted for embedding"}, status_code=status.HTTP_202_ACCEPTED
    )
