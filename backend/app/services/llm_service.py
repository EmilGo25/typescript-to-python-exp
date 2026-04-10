"""LLM service — routes ALL calls through BlindBench. No direct Ollama/OpenAI/Anthropic."""
from __future__ import annotations

import json
from typing import Any

from app.services.blindbench_client import (
    generate_problem_via_arena,
    explain_via_blindbench,
    analyze_image_via_blindbench,
)


# ──────────────────────────────────────────────────────────────────────
# Problem generation — via BlindBench Arena
# ──────────────────────────────────────────────────────────────────────

_PROBLEM_PROMPT_TEMPLATE = """\
You are an expert TypeScript and Python instructor. Generate coding problems \
that help TypeScript developers learn Python. Return valid JSON only.

Generate a TypeScript-to-Python translation problem at {difficulty} difficulty \
focused on the "{category}" category.

Category guidelines:
- arrays: map/filter/reduce, sorting, slicing, spread, flat, find
- objects: dictionary transformations, merging, destructuring, key/value operations
- strings: template literals, regex, split/join, parsing, formatting
- classes: class inheritance, methods, properties, static members, encapsulation
- recursion: tree traversal, divide-and-conquer, memoization, nested structures
- async: promises, async/await patterns, callbacks (translate to sync Python equivalents)
- functions: closures, higher-order functions, decorators, currying, generators

Difficulty guidelines:
- easy: simple usage of the category concepts, single function
- medium: combining multiple patterns, edge cases, nested data
- hard: complex real-world scenarios, performance considerations, multiple interacting parts

Return a JSON object with EXACTLY this structure (no markdown, no extra text):
{{
  "title": "Short descriptive title",
  "description": "Clear description of what the function does",
  "typescript_code": "The full TypeScript function code",
  "python_solution": "The idiomatic Pythonic solution",
  "func_name": "the_python_function_name",
  "example_input": "Human-readable example input",
  "example_output": "Human-readable example output",
  "test_cases": [
    {{"input": "[arg1, arg2]", "expected_output": "expected_result"}},
    {{"input": "[arg1, arg2]", "expected_output": "expected_result"}},
    {{"input": "[arg1, arg2]", "expected_output": "expected_result"}},
    {{"input": "[arg1, arg2]", "expected_output": "expected_result"}},
    {{"input": "[arg1, arg2]", "expected_output": "expected_result"}}
  ]
}}

IMPORTANT rules:
- test_cases input/expected_output must be valid JSON strings
- input is a JSON array of function arguments (even for single arg, wrap in array)
- The Python solution must be idiomatic: use comprehensions, built-ins, unpacking
- Include at least 5 test cases covering edge cases
- The TypeScript and Python functions must be semantically equivalent
- python_solution must define a function named func_name
"""


_CUSTOM_PROBLEM_PROMPT_TEMPLATE = """\
You are an expert TypeScript and Python instructor. Generate coding problems \
that help TypeScript developers learn Python. Return valid JSON only.

Generate a TypeScript-to-Python translation problem at {difficulty} difficulty \
focused on the following custom subject:

Subject: {custom_subject}

Return a JSON object with EXACTLY this structure (no markdown, no extra text):
{{
  "title": "Short descriptive title",
  "description": "Clear description of what the function does",
  "typescript_code": "The full TypeScript function code",
  "python_solution": "The idiomatic Pythonic solution",
  "func_name": "the_python_function_name",
  "example_input": "Human-readable example input",
  "example_output": "Human-readable example output",
  "test_cases": [
    {{"input": "[arg1, arg2]", "expected_output": "expected_result"}},
    {{"input": "[arg1, arg2]", "expected_output": "expected_result"}},
    {{"input": "[arg1, arg2]", "expected_output": "expected_result"}},
    {{"input": "[arg1, arg2]", "expected_output": "expected_result"}},
    {{"input": "[arg1, arg2]", "expected_output": "expected_result"}}
  ]
}}

IMPORTANT rules:
- test_cases input/expected_output must be valid JSON strings
- input is a JSON array of function arguments (even for single arg, wrap in array)
- The Python solution must be idiomatic
- Include at least 5 test cases covering edge cases
- python_solution must define a function named func_name
"""


def generate_problem(
    difficulty: str,
    category: str = "arrays",
    custom_subject: str | None = None,
) -> dict[str, Any]:
    """Generate a problem via BlindBench Arena (2 models compete, 1 picked randomly)."""
    if category == "custom" and custom_subject:
        prompt = _CUSTOM_PROBLEM_PROMPT_TEMPLATE.format(
            difficulty=difficulty, custom_subject=custom_subject
        )
    else:
        prompt = _PROBLEM_PROMPT_TEMPLATE.format(
            difficulty=difficulty, category=category
        )
    return generate_problem_via_arena(prompt)


# ──────────────────────────────────────────────────────────────────────
# Solution explanation — via BlindBench Smart Router
# ──────────────────────────────────────────────────────────────────────


def explain_solution(typescript_code: str, python_solution: str) -> str:
    """Generate explanation via BlindBench Smart Router."""
    return explain_via_blindbench(typescript_code, python_solution)


# ──────────────────────────────────────────────────────────────────────
# Image subject extraction — via BlindBench (vision-capable model)
# ──────────────────────────────────────────────────────────────────────


def extract_subject_from_image(image_data: str, media_type: str) -> str:
    """Analyze an image via BlindBench Smart Router (routes to vision model)."""
    return analyze_image_via_blindbench(image_data)
