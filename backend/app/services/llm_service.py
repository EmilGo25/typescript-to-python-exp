"""LLM service for problem generation, solution generation, and evaluation feedback."""
from __future__ import annotations

import json
import os
from typing import Any

import anthropic
from dotenv import load_dotenv

load_dotenv()

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Copy backend/.env.example to backend/.env "
                "and add your key."
            )
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


MODEL = "claude-sonnet-4-20250514"


def _call_llm(system: str, prompt: str) -> str:
    """Send a prompt to Claude and return the text response."""
    client = _get_client()
    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


# ──────────────────────────────────────────────────────────────────────
# Problem generation
# ──────────────────────────────────────────────────────────────────────

_PROBLEM_SYSTEM = """\
You are an expert TypeScript and Python instructor. Generate coding problems \
that help TypeScript developers learn Python. Return valid JSON only."""

_PROBLEM_PROMPT_TEMPLATE = """\
Generate a TypeScript-to-Python translation problem at {difficulty} difficulty.

Difficulty guidelines:
- easy: array operations (map/filter/reduce), string manipulation, simple math
- medium: object/dictionary transformations, nested data, multiple functions
- hard: recursion, async patterns, class-based logic, generators

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


def generate_problem(difficulty: str) -> dict[str, Any]:
    """Generate a problem using the LLM."""
    prompt = _PROBLEM_PROMPT_TEMPLATE.format(difficulty=difficulty)
    response = _call_llm(_PROBLEM_SYSTEM, prompt)

    # Strip markdown code fences if present
    text = response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    return json.loads(text)


# ──────────────────────────────────────────────────────────────────────
# Evaluation feedback
# ──────────────────────────────────────────────────────────────────────

_EVAL_SYSTEM = """\
You are a senior Python code reviewer. Evaluate the user's Python translation \
of a TypeScript function. Return valid JSON only."""

_EVAL_PROMPT_TEMPLATE = """\
The user was asked to translate this TypeScript code to Python:

```typescript
{typescript_code}
```

Reference Python solution:
```python
{reference_solution}
```

User's Python submission:
```python
{user_code}
```

Test results: {test_summary}

Evaluate the user's code and return JSON with EXACTLY this structure:
{{
  "score": <0-100 integer>,
  "explanation": "Brief overall assessment",
  "improvements": [
    "Specific improvement suggestion 1",
    "Specific improvement suggestion 2"
  ],
  "conventions": [
    "Python convention the user should follow 1",
    "Python convention the user should follow 2"
  ]
}}

Focus on:
- Correctness relative to test results
- Pythonic idioms (comprehensions, built-ins, unpacking, enumerate, dict.get)
- Code readability and simplicity
- Performance considerations
- Python naming conventions (snake_case, etc.)

Be specific and actionable. Reference exact lines or patterns from the user's code.
"""


def evaluate_submission(
    typescript_code: str,
    reference_solution: str,
    user_code: str,
    test_summary: str,
) -> dict[str, Any]:
    """Use the LLM to evaluate a user's submission."""
    prompt = _EVAL_PROMPT_TEMPLATE.format(
        typescript_code=typescript_code,
        reference_solution=reference_solution,
        user_code=user_code,
        test_summary=test_summary,
    )
    response = _call_llm(_EVAL_SYSTEM, prompt)

    text = response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    return json.loads(text)


# ──────────────────────────────────────────────────────────────────────
# Solution explanation
# ──────────────────────────────────────────────────────────────────────

_EXPLAIN_SYSTEM = """\
You are a Python educator helping TypeScript developers understand Python idioms."""

_EXPLAIN_PROMPT = """\
Explain this Python solution that translates the following TypeScript code:

TypeScript:
```typescript
{typescript_code}
```

Python solution:
```python
{python_solution}
```

Write a clear, concise explanation (2-4 paragraphs) covering:
1. How the TypeScript constructs map to Python equivalents
2. Which Pythonic idioms are used and why
3. Key differences a TypeScript developer should note

Do NOT wrap your response in JSON — just return plain text.
"""


def explain_solution(typescript_code: str, python_solution: str) -> str:
    """Generate a plain-text explanation of the Python solution."""
    prompt = _EXPLAIN_PROMPT.format(
        typescript_code=typescript_code,
        python_solution=python_solution,
    )
    return _call_llm(_EXPLAIN_SYSTEM, prompt)
