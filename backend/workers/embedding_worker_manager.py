import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Define the path here — do NOT import from upload_service
WORKER_DIR = Path(__file__).parent
EMBEDDING_WORKER = str(WORKER_DIR / "embedding_worker.py")


class EmbeddingWorkerManager:
    def __init__(self):
        self._proc: Optional[subprocess.Popen] = None

    def start(self):
        if self._proc is not None and self._proc.poll() is None:
            return

        self._proc = subprocess.Popen(
            [sys.executable, EMBEDDING_WORKER],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=sys.stderr,
            text=True,
            bufsize=1,
        )

    def submit_job(
        self,
        repo_url: str,
        session_id: str,
        job_id: str,
        progress_path: str,
        log_dir: str,
    ):
        self.start()

        payload = {
            "repo_url": repo_url,
            "session_id": session_id,
            "job_id": job_id,
            "progress_path": progress_path,
            "log_dir": log_dir,
        }

        assert self._proc and self._proc.stdin
        self._proc.stdin.write(json.dumps(payload) + "\n")
        self._proc.stdin.flush()

    def stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()


embedding_worker = EmbeddingWorkerManager()