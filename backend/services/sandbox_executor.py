import json
import subprocess
import sys
import textwrap


SANDBOX_SKELETON = """
import ast
import json
import sys

INPUT_CODE = {input_code_repr}

{function_code}

try:
    result = execute_analysis(INPUT_CODE)
    if not isinstance(result, dict):
        print(json.dumps({{
            "success": False,
            "data": None,
            "error": "execute_analysis must return a dict, got: " + type(result).__name__
        }}))
    else:
        print(json.dumps({{
            "success": True,
            "data": result,
            "error": None
        }}))
except Exception as e:
    print(json.dumps({{
        "success": False,
        "data": None,
        "error": str(e)
    }}))
"""


def execute_function(function_code: str, file_content: str, timeout: int = 10) -> dict:
    """
    Execute an analytical function inside an isolated Python subprocess.

    Args:
        function_code: Python function def execute_analysis(code_string: str) -> dict
        file_content:  The raw Python file fetched from GitHub
        timeout:       Max seconds before killing subprocess (default 10)

    Returns:
        dict with keys: success (bool), data (dict|None), error (str|None)
    """
    script = SANDBOX_SKELETON.format(
        input_code_repr=repr(file_content),
        function_code=textwrap.dedent(function_code)
    )

    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=timeout
        )

        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()

        if not stdout:
            print(
                f"[Sandbox] ERROR: No output from subprocess.\n"
                f"[Sandbox] stderr: {stderr}"
            )
            return {
                "success": False,
                "data": None,
                "error": f"No output produced. stderr: {stderr}"
            }

        try:
            result = json.loads(stdout)
            if not result.get("success"):
                print(f"[Sandbox] ERROR: Function execution failed: {result.get('error')}")
            return result

        except json.JSONDecodeError:
            print(
                f"[Sandbox] ERROR: Could not parse subprocess output as JSON.\n"
                f"[Sandbox] Raw stdout: {stdout}"
            )
            return {
                "success": False,
                "data": None,
                "error": f"Invalid JSON output: {stdout}"
            }

    except subprocess.TimeoutExpired:
        print(
            f"[Sandbox] ERROR: Execution timed out after {timeout} seconds. "
            f"Function may have an infinite loop or is too slow."
        )
        return {
            "success": False,
            "data": None,
            "error": f"Execution timed out after {timeout} seconds."
        }

    except Exception as e:
        print(f"[Sandbox] ERROR: Unexpected error running subprocess: {e}")
        return {
            "success": False,
            "data": None,
            "error": str(e)
        }