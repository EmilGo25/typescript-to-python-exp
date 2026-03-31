"""Sandboxed Python code execution.

Runs user code in a subprocess with:
- Restricted builtins (no file/network/os access)
- Execution timeout
- Stdout/stderr capture
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Dict, List, Optional


TIMEOUT_SECONDS = 5
MAX_OUTPUT_BYTES = 50_000


@dataclass
class SandboxResult:
    results: Optional[List[Dict]] = None
    error: Optional[str] = None


def _build_runner_script(user_code: str, func_name: str, test_cases_json: str) -> str:
    """Build the sandboxed runner script with user code and test cases injected via JSON."""
    # We inject user_code and test data as base64/JSON to avoid any escaping issues
    import base64
    code_b64 = base64.b64encode(user_code.encode()).decode()
    func_b64 = base64.b64encode(func_name.encode()).decode()
    tests_b64 = base64.b64encode(test_cases_json.encode()).decode()

    return f'''
import json, sys, math, itertools, functools, collections, re, copy, typing, base64

_ALLOWED_BUILTINS = {{
    "abs": abs, "all": all, "any": any, "bin": bin, "bool": bool,
    "bytearray": bytearray, "bytes": bytes, "callable": callable,
    "chr": chr, "complex": complex, "dict": dict, "dir": dir,
    "divmod": divmod, "enumerate": enumerate, "filter": filter,
    "float": float, "format": format, "frozenset": frozenset,
    "getattr": getattr, "hasattr": hasattr, "hash": hash, "hex": hex,
    "id": id, "int": int, "isinstance": isinstance, "issubclass": issubclass,
    "iter": iter, "len": len, "list": list, "map": map, "max": max,
    "min": min, "next": next, "object": object, "oct": oct, "ord": ord,
    "pow": pow, "print": print, "property": property, "range": range,
    "repr": repr, "reversed": reversed, "round": round, "set": set,
    "setattr": setattr, "slice": slice, "sorted": sorted,
    "staticmethod": staticmethod, "str": str, "sum": sum, "super": super,
    "tuple": tuple, "type": type, "vars": vars, "zip": zip,
    "True": True, "False": False, "None": None,
    "__import__": __import__,
}}

_SAFE_MODULES = frozenset({{
    "math", "itertools", "functools", "collections", "re", "copy",
    "typing", "json", "string", "operator", "decimal", "fractions",
    "heapq", "bisect", "statistics", "datetime",
}})

_real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__
def _restricted_import(name, *args, **kwargs):
    if name.split(".")[0] not in _SAFE_MODULES:
        raise ImportError(f"Import of '{{name}}' is not allowed")
    return _real_import(name, *args, **kwargs)

_ALLOWED_BUILTINS["__import__"] = _restricted_import

_user_code = base64.b64decode("{code_b64}").decode()
_func_name = base64.b64decode("{func_b64}").decode()
_test_cases_json = base64.b64decode("{tests_b64}").decode()

_sandbox_globals = {{"__builtins__": _ALLOWED_BUILTINS}}
for _mod_name in ("math", "itertools", "functools", "collections", "re", "copy", "typing", "json"):
    _sandbox_globals[_mod_name] = sys.modules[_mod_name]

try:
    exec(_user_code, _sandbox_globals)
except Exception as e:
    print(json.dumps({{"error": f"Compilation error: {{type(e).__name__}}: {{e}}"}}))
    sys.exit(0)

if _func_name not in _sandbox_globals:
    print(json.dumps({{"error": f"Function '{{_func_name}}' not found in submitted code"}}))
    sys.exit(0)

_func = _sandbox_globals[_func_name]
_test_cases = json.loads(_test_cases_json)
_results = []

for _tc in _test_cases:
    _input_val = json.loads(_tc["input"])
    _expected = json.loads(_tc["expected_output"])
    try:
        if isinstance(_input_val, list):
            _actual = _func(*_input_val)
        else:
            _actual = _func(_input_val)
        _passed = _actual == _expected
        _results.append({{
            "passed": _passed,
            "input": _tc["input"],
            "expected": json.dumps(_expected),
            "actual": json.dumps(_actual),
            "error": None,
        }})
    except Exception as e:
        _results.append({{
            "passed": False,
            "input": _tc["input"],
            "expected": json.dumps(_expected),
            "actual": "N/A",
            "error": f"{{type(e).__name__}}: {{e}}",
        }})

print(json.dumps({{"results": _results}}))
'''


def run_user_code(
    user_code: str,
    func_name: str,
    test_cases: list,
) -> SandboxResult:
    """Execute user Python code in a sandboxed subprocess.

    Args:
        user_code: The user's Python code.
        func_name: Name of the function to test.
        test_cases: List of dicts with 'input' and 'expected_output' JSON strings.

    Returns:
        SandboxResult with either results list or error string.
    """
    test_cases_json = json.dumps(test_cases)
    script = _build_runner_script(user_code, func_name, test_cases_json)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=True) as f:
        f.write(script)
        f.flush()

        try:
            proc = subprocess.run(
                [sys.executable, f.name],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
                env={},  # Empty env — no access to parent env vars
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(error="Execution timed out (5 second limit)")

    stdout = proc.stdout[:MAX_OUTPUT_BYTES].strip()
    stderr = proc.stderr[:MAX_OUTPUT_BYTES].strip()

    if not stdout:
        error_msg = stderr if stderr else "No output produced"
        return SandboxResult(error=f"Execution error: {error_msg}")

    try:
        output = json.loads(stdout)
    except json.JSONDecodeError:
        return SandboxResult(error=f"Unexpected output: {stdout[:500]}")

    if "error" in output:
        return SandboxResult(error=output["error"])

    return SandboxResult(results=output.get("results", []))
