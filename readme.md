# Legacy Code RAG Assistant

A full-stack RAG-based application for understanding and querying legacy code repositories.

## Features
- User authentication and session management
- Repository upload and indexing
- Background code parsing and embedding
- ChromaDB-based retrieval for code chunks
- Chat-based querying over indexed repositories
- Generated answers with source citations

## Project structure
- backend/ - FastAPI backend
- frontend/ - React + Vite frontend
- README_RUN.md - step-by-step setup and run instructions

## Quick start

### 1. Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file in the `backend` folder:
```env
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
OPENAI_API_KEY=your_openai_key_optional
OPENAI_MODEL=gpt-4o-mini
```

Run the backend:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Frontend
```bash
cd frontend
npm install
npm run dev
```

Open the frontend at:
- http://localhost:5173

### 3. Access the API docs
- http://localhost:8000/docs
- http://localhost:8000/health

## Notes
- The app can work without OpenAI credentials because it includes a fallback answer generator.
- For a full experience, configure Supabase and a public GitHub repository URL.

## Additional help
See [README_RUN.md](README_RUN.md) for a more detailed setup and troubleshooting guide.

Compare Models 
Model A 
Llama3 8B 
Model B 
Page 9 of 12 
Mistral 7B 
Project 1: RAG-Based Legacy Code Understanding and Documentation Assistant 
Evaluate 
Metric 
Clarity 
Hallucination 
Latency 
Phase 8: Dependency Mapping 
Goal 
Generate code relationships. 
Example: 
LoginController 
↓ 
AuthService 
↓ 
UserRepository 
↓ 
Database 
Tools 
NetworkX 
Graphviz 
Deliverable 
Dependency Graph 
Phase 9: Frontend Development: Streamlit Pages 
Page 1 
Repository Upload 
Page 10 of 12 
Page 2 
Project 1: RAG-Based Legacy Code Understanding and Documentation Assistant 
Ask Questions 
Page 3 
Retrieved Code 
Page 4 
Dependency Graph 
Page 5 
Auto Documentation 
Phase 10: Evaluation 
Test Dataset Creation 
Prepare: 
50 Questions 
Examples: 
How is authentication handled? 
Which file validates payments? 
How are orders stored? 
Evaluation Metrics 
Retrieval Precision 
Relevant Chunks Retrieved -------------------------------- 
Total Chunks Retrieved 
Answer Relevance 
Faculty Rating 
1–5 scale 
Page 11 of 12 
Hallucination Rate 
Project 1: RAG-Based Legacy Code Understanding and Documentation Assistant 
Incorrect Answers --------------------- 
Total Answers 
Latency 
Average response time. 
10. Expected Outcomes 
Students should demonstrate: 
Functional Deliverables 
Upload repository 
Parse source code 
Create vector database 
Semantic search 
AI-generated explanations 
Dependency visualization 
Auto documentation 
Page 12 of 12 