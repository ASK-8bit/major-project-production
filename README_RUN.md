# Run Guide for the Project

This project consists of:
- a FastAPI backend
- a React + Vite frontend
- a ChromaDB-based retrieval pipeline for indexed repositories

## 1. Prerequisites

Make sure you have installed:
- Python 3.10+ 
- Node.js 18+ 
- Git
- A terminal with internet access for installing dependencies

## 2. Clone and open the project

```bash
git clone <your-repo-url>
cd major-project-production
```

## 3. Backend setup

### Create and activate a virtual environment

Windows PowerShell:
```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
```

### Install Python dependencies

```bash
cd backend
pip install -r requirements.txt
```

### Create environment variables

Create a file named `.env` inside the `backend` folder with the following values:

```env
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_service_role_key
OPENAI_API_KEY=your_openai_key_optional
OPENAI_MODEL=gpt-4o-mini
```

> The app can run without OpenAI credentials because it has a built-in fallback answer generator.

### Start the backend

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at:
- http://localhost:8000/docs
- http://localhost:8000/health

## 4. Frontend setup

Open a new terminal and run:

```bash
cd frontend
npm install
npm run dev
```

The frontend will be available at:
- http://localhost:5173

## 5. How to use the app

1. Open the frontend in the browser.
2. Sign up or log in.
3. Upload a public GitHub repository URL.
4. Wait for indexing to complete.
5. Create a chat session for that repository.
6. Ask questions about the repository code.

## 6. Common issues

### Backend fails because Supabase is not configured
- Make sure `.env` exists inside the `backend` folder.
- Confirm `SUPABASE_URL` and `SUPABASE_KEY` are valid.

### Frontend cannot connect to backend
- Ensure the backend is running on port 8000.
- Confirm the frontend API base URL in `frontend/src/services/api.js` points to `http://localhost:8000`.

### Indexing does not work
- Check that the repository URL is public.
- Verify that Git is installed.
- Check backend logs for errors.

## 7. Optional: run tests

Backend tests:

```bash
cd backend
python -m pytest -q
```

Frontend build check:

```bash
cd frontend
npm run build
```
