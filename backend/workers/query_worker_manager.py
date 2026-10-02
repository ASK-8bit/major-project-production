import json
import subprocess
import sys
import threading
import uuid
from queue import Queue, Empty
from typing import Optional

from services.upload_service import WORKER_DIR

QUERY_WORKER = str(WORKER_DIR / "query_worker.py")


class QueryWorkerManager:
    def __init__(self):
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._pending: dict[str, Queue] = {}
        self._reader_thread: Optional[threading.Thread] = None

    def start(self):
        """Start the long-lived worker (call once at server startup)."""
        if self._proc is not None and self._proc.poll() is None:
            return  # already running

        self._proc = subprocess.Popen(
            [sys.executable, QUERY_WORKER],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,          # so you can see "Model loaded..." in logs
            text=True,
            bufsize=1,
        )

        self._reader_thread = threading.Thread(
            target=self._reader_loop, daemon=True
        )
        self._reader_thread.start()

    def _reader_loop(self):
        assert self._proc and self._proc.stdout
        for line in self._proc.stdout:
            try:
                data = json.loads(line)
                request_id = data.get("request_id")
                if request_id and request_id in self._pending:
                    self._pending[request_id].put(data)
            except Exception:
                pass

    def query(
        self,
        prompt: str,
        session_id: str,
        top_k: int = 5,
        timeout: float = 60.0,
    ) -> dict:
        self.start()  # safety: ensure it is running

        request_id = str(uuid.uuid4())
        result_q: Queue = Queue()

        with self._lock:
            self._pending[request_id] = result_q

            payload = {
                "request_id": request_id,
                "prompt": prompt,
                "session_id": session_id,
                "top_k": top_k,
            }
            assert self._proc and self._proc.stdin
            self._proc.stdin.write(json.dumps(payload) + "\n")
            self._proc.stdin.flush()

        try:
            return result_q.get(timeout=timeout)
        except Empty:
            raise TimeoutError("Query worker timed out")
        finally:
            with self._lock:
                self._pending.pop(request_id, None)

    def stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()


# Singleton used by the whole app
query_worker = QueryWorkerManager()