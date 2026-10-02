from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from workers.embedding_worker_manager import embedding_worker

from api.auth import router as auth_router
from api.upload import router as upload_router
from api.chat import router as chat_router
from workers.query_worker_manager import query_worker   # ← add


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Server is starting → load the model once
    query_worker.start()
    embedding_worker.start()
    yield
    # Server is shutting down
    query_worker.stop()
    embedding_worker.stop()


app = FastAPI(
    title="Legacy Code RAG Assistant",
    description="RAG-based assistant for querying legacy codebases",
    version="1.0.0",
    lifespan=lifespan,          # ← add this
)

# CORS stays the same
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(upload_router)
app.include_router(chat_router)