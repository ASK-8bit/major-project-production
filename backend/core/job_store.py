from threading import Lock

# In-memory job tracker.
# Survives only while server is running — Supabase `jobs` table is the
# persistent backup, synced on every status change.
_jobs: dict[str, dict] = {}
_lock = Lock()


def create_job(job_id: str, session_id: str):
    with _lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "session_id": session_id,
            "status": "pending",
            "chunks_done": 0,
            "total_chunks": 0,
            "error": None,
        }


def update_job(job_id: str, **fields):
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)


def get_job(job_id: str) -> dict | None:
    with _lock:
        return _jobs.get(job_id, None)