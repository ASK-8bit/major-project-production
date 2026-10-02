import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workers.embedding_worker import parse_python_file
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


def test_expand_context_with_dependencies_adds_related_chunks():
    chunks = [
        {
            "text": "def login(user, password):\n    token = validate_token(user)\n    return session.create(token)",
            "metadata": {
                "file_path": "/repo/auth.py",
                "qualified_name": "AuthService.login",
                "function_name": "login",
                "start_line": 20,
                "end_line": 30,
            },
            "distance": 0.1,
        },
        {
            "text": "def validate_token(user):\n    return user.token is not None",
            "metadata": {
                "file_path": "/repo/auth_helpers.py",
                "qualified_name": "AuthHelpers.validate_token",
                "function_name": "validate_token",
                "start_line": 5,
                "end_line": 8,
            },
            "distance": 0.2,
        },
        {
            "text": "def create_session(token):\n    return Session(token)",
            "metadata": {
                "file_path": "/repo/session.py",
                "qualified_name": "SessionFactory.create",
                "function_name": "create",
                "start_line": 12,
                "end_line": 14,
            },
            "distance": 0.3,
        },
    ]

    expanded = build_answer("How does login work?", chunks)

    assert expanded["answer"]
    assert len(expanded["citations"]) >= 3
    symbol_names = {citation["qualified_name"] for citation in expanded["citations"]}
    assert "AuthService.login" in symbol_names
    assert "AuthHelpers.validate_token" in symbol_names or "SessionFactory.create" in symbol_names


def test_parse_python_file_uses_chroma_safe_dependency_metadata(tmp_path):
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        "def login(user):\n    return validate_token(user)\n\n"
        "def validate_token(user):\n    return user is not None\n",
        encoding="utf-8",
    )

    documents = parse_python_file(file_path)

    assert documents
    dep_meta = documents[0].metadata.get("dependencies")
    assert isinstance(dep_meta, str)
    assert "validate_token" in dep_meta


def test_build_answer_explains_function_purpose_in_plain_english():
    chunks = [
        {
            "text": "def login(user, password):\n    if not user or not password:\n        return False\n    token = validate_token(user)\n    return session.create(token)",
            "metadata": {
                "file_path": "/repo/auth.py",
                "qualified_name": "AuthService.login",
                "function_name": "login",
                "start_line": 10,
                "end_line": 20,
            },
            "distance": 0.08,
        }
    ]

    result = build_answer("What does login do?", chunks)

    lower = result["answer"].lower()
    assert "login" in lower
    assert "validates" in lower or "checks" in lower or "creates" in lower
    assert "plain english" in lower or "it" in lower
