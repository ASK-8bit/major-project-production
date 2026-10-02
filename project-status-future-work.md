# Project Status Overview: What Still Needs to Be Done

This document lists the remaining tasks and improvements needed to take the project from a working MVP to a stronger, more complete RAG-based legacy code documentation assistant.

## High-Priority Remaining Work

### 1. LLM-based explanation generation
- The current backend only returns retrieved code chunks.
- It does not yet generate a final natural-language explanation from the retrieved context.
- This is one of the most important missing features.

### 2. Better response quality
- The current query experience is based on vector retrieval only.
- The assistant should produce:
  - summary of the relevant logic
  - explanation of how the component works
  - dependency/context explanation
  - answer to the user’s question in plain English

### 3. Prompt engineering
- The system needs a robust prompt template for:
  - explaining code
  - answering repository questions
  - citing source files and relevant code regions
  - avoiding hallucinations by grounding responses in retrieved chunks

### 4. Source citation and evidence display
- The frontend should clearly show which code snippets were used to answer a question.
- Better UI/UX is needed for displaying evidence, references, and confidence.

## Medium-Priority Improvements

### 5. Improve indexing quality
- Current indexing focuses on Python functions and methods.
- The system could be improved to support:
  - class-level summaries
  - module-level context
  - dependency relationships
  - better chunking strategies

### 6. Support more repository types
- The current implementation is centered on Python repositories.
- Future work could expand to:
  - JavaScript/TypeScript projects
  - Django/Flask projects with richer structure awareness
  - mixed-language repositories

### 7. Better repository understanding
- The project could include:
  - project tree summary
  - architecture overview
  - file dependency visualization
  - feature-level documentation generation

## UI/UX Enhancements

### 8. Improve chat experience
- Add richer assistant responses instead of simple chunk lists.
- Show markdown-formatted answers, bullet points, and structured summaries.
- Make the chat experience feel closer to a modern AI assistant.

### 9. Better loading and status feedback
- Improve progress indicators for indexing and query operations.
- Display clearer error messages and retry guidance.

## Technical / Project Maturity Improvements

### 10. Testing and reliability
- Add backend tests for authentication, upload, indexing, and query flows.
- Add frontend tests for major components.
- Improve error handling and edge cases.

### 11. Deployment readiness
- Add production configuration.
- Set up environment variables securely.
- Prepare Docker/container deployment if required.
- Configure deployment for Supabase, ChromaDB, and backend/frontend hosting.

### 12. Documentation and polish
- Add a developer setup guide.
- Include architecture diagrams.
- Document API endpoints and expected behavior.
- Improve README quality for evaluation/demo purposes.

## Suggested Next Step

The most important next milestone is:
- connect the retriever output to an LLM
- generate a final answer based on the retrieved code chunks
- show that answer in the chat interface with proper source references

Once that is complete, the project will feel much more like a complete documentation assistant rather than a retrieval prototype.