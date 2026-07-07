from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.auth import router as auth_router
from api.upload import router as upload_router
from api.chat import router as chat_router

app = FastAPI(
    title="Legacy Code RAG Assistant",
    description="RAG-based assistant for querying legacy codebases",
    version="1.0.0"
)

# ── CORS ─────────────────────────────────────────────────────────
# Allows React dev server (localhost:5173) to call this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # React default port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(upload_router)
app.include_router(chat_router)

# Future routers go here:
# app.include_router(llm_router) — once LLM is integrated


@app.get("/health")
async def health():
    return {"status": "ok"}