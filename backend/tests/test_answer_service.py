import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.answer_service import build_answer


def test_build_answer_returns_summary_and_citations():
    chunks = [
        {
            "text": "def login(user, password):\n    return authenticate(user, password)",
            "metadata": {
                "file_path": "/repo/auth.py",
                "qualified_name": "AuthService.login",
                "start_line": 10,
                "end_line": 12,
            },
            "distance": 0.12,
        }
    ]

    result = build_answer("How does login work?", chunks)

    assert result["answer"]
    assert "login" in result["answer"].lower()
    assert len(result["citations"]) == 1
    assert result["citations"][0]["file_path"].endswith("auth.py")
