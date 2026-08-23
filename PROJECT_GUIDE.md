<!-- Single-file project guide: overview + all run commands -->
# Project Guide — Legacy Code RAG Assistant

Short, single-file guide that explains the project and lists all run/build/test commands.

## Overview
- **What it is:** A Retrieval-Augmented Generation (RAG) assistant for querying legacy codebases.
- **Components:** FastAPI backend, React + Vite frontend, ChromaDB vector store and background workers.
- **Key files:** [backend/main.py](backend/main.py), [docker-compose.yml](docker-compose.yml), [frontend/package.json](frontend/package.json), [README_RUN.md](README_RUN.md)

## Prerequisites
- Python 3.10+
- Node.js 18+
- Git
- Docker & Docker Compose (optional but recommended)

---

## Quickstart (Docker)
Run the full stack (recommended):

PowerShell / bash:

```bash
# build and start services
docker-compose up --build -d

# view logs (tail)
docker-compose logs -f

# stop and remove containers
docker-compose down
```

Containers exposed
- Backend: http://localhost:8000
- Frontend: http://localhost:5173

---

## Local development (no Docker)

### Backend (Windows PowerShell)

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# create .env in backend/ (see Env section below)
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Backend (macOS / Linux)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend dev: http://localhost:5173

To build production frontend:

```bash
cd frontend
npm run build
```

---

## Environment variables
Create a `.env` file in the `backend` folder (or set env vars for Docker). Common keys used in this repo (see [docker-compose.yml](docker-compose.yml)):

- `SUPABASE_URL`
- `SUPABASE_KEY`
- `EMBEDDING_MODEL` (embedding model id/name)
- `EMBED_BATCH_SIZE`
- `CHROMA_BATCH_SIZE`
- `CHROMA_API_KEY`
- `CHROMA_TENANT`
- `CHROMA_DATABASE`
- `GEMINI_API_KEY` (or other LLM API keys)
- Optional / historic keys: `OPENAI_API_KEY`, `OPENAI_MODEL`

Minimal example for basic local dev (backend/.env):

```
SUPABASE_URL=http://example
SUPABASE_KEY=service_role_key_here
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBED_BATCH_SIZE=64
CHROMA_DATABASE=chroma.sqlite3
```

Note: the repo also contains a small Chroma DB at `backend/chromadb` (persisted file). Keep an eye on volumes when using Docker.

---

## Background workers
- The app starts two background worker managers at server lifespan startup: `query_worker` and `embedding_worker` (see [backend/main.py](backend/main.py)).
- When running under `uvicorn` or Docker the workers are started automatically via the FastAPI lifespan hook.

If you need to debug workers separately, check `backend/workers/` for manager scripts and logs at `backend/workers/logs/` and `backend/workers/progress/`.

---

## Tests

Run backend tests:

```bash
cd backend
python -m pytest -q
```

Frontend build check:

```bash
cd frontend
npm run build
```

---

## Useful Docker commands

```bash
# Rebuild a single service
docker-compose build backend

# Start only backend
docker-compose up -d backend

# Execute a shell inside backend container
docker-compose exec backend /bin/sh

# Remove images (use with care)
docker-compose down --rmi local
```

---

## Troubleshooting & tips
- If backend cannot reach Supabase, confirm `SUPABASE_URL` and `SUPABASE_KEY`.
- If indexing fails, ensure Git is installed and repo URLs are public.
- For CORS issues, frontend expects backend at `http://localhost:8000` (see `backend/main.py`).
- Check worker logs: `backend/workers/logs/` and progress files in `backend/workers/progress/`.

---

## Where to look in the code
- API routes: [backend/api](backend/api) (files: [auth.py](backend/api/auth.py), [upload.py](backend/api/upload.py), [chat.py](backend/api/chat.py))
- Services: [backend/services](backend/services) (LLM + chat logic)
- Workers: [backend/workers](backend/workers)

---

If you want, I can also:
- add this file to the repo (done), or
- open a PR with small run-script shortcuts, or
- generate a single `Makefile` / `invoke` tasks file to unify commands.
