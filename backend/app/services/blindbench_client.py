"""Client for BlindBench API — ALL LLM calls route through BlindBench."""
from __future__ import annotations

import json
import random
import time
from typing import Any

import httpx

BLINDBENCH_URL = "http://localhost:3001"
POLL_INTERVAL = 1.5
POLL_TIMEOUT = 180


# ── Low-level helpers ──────────────────────────────────────────────────────────


def _submit_prompt(prompt: str, category: str = "coding") -> dict:
    """Submit a prompt to BlindBench Arena."""
    with httpx.Client(base_url=BLINDBENCH_URL, timeout=30.0) as client:
        r = client.post(
            "/api/prompts",
            json={"content": prompt, "category": category},
        )
        r.raise_for_status()
        return r.json()


def _poll_until_ready(prompt_id: str) -> dict:
    """Poll until all model runs complete."""
    with httpx.Client(base_url=BLINDBENCH_URL, timeout=10.0) as client:
        elapsed = 0.0
        while elapsed < POLL_TIMEOUT:
            r = client.get(f"/api/prompts/{prompt_id}/status")
            r.raise_for_status()
            status = r.json()
            if status.get("ready"):
                return status
            time.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL
        raise TimeoutError(
            f"BlindBench responses not ready after {POLL_TIMEOUT}s"
        )


def _get_blind_responses(prompt_id: str) -> dict:
    """Fetch anonymous responses."""
    with httpx.Client(base_url=BLINDBENCH_URL, timeout=10.0) as client:
        r = client.get(f"/api/responses/blind/{prompt_id}")
        r.raise_for_status()
        return r.json()


def _call_router(prompt: str, category: str = "coding") -> str:
    """Use BlindBench Smart Router for a single best response."""
    with httpx.Client(base_url=BLINDBENCH_URL, timeout=180.0) as client:
        r = client.post(
            "/api/router/complete",
            json={"content": prompt, "category": category},
        )
        r.raise_for_status()
        data = r.json()
        return data["response"]["content"]


def stream_from_router(
    prompt: str,
    category: str = "coding",
    image_base64: str | None = None,
):
    """Stream tokens from BlindBench router. Yields (event_type, data) tuples.

    event_type is one of: 'routing', 'token', 'done', 'error'
    """
    payload: dict = {"content": prompt, "category": category}
    if image_base64:
        payload["imageBase64"] = image_base64

    with httpx.Client(base_url=BLINDBENCH_URL, timeout=300.0) as client:
        with client.stream(
            "POST", "/api/router/stream", json=payload,
        ) as response:
            response.raise_for_status()
            buffer = ""
            for chunk in response.iter_text():
                buffer += chunk
                while "\n\n" in buffer:
                    event_str, buffer = buffer.split("\n\n", 1)
                    if not event_str.strip():
                        continue
                    event_type = None
                    data = None
                    for line in event_str.strip().split("\n"):
                        if line.startswith("event:"):
                            event_type = line[6:].strip()
                        elif line.startswith("data:"):
                            data = line[5:].strip()
                    if event_type and data:
                        yield event_type, data


def submit_evaluation(
    blind_presentation_id: str,
    best_label: str,
    scores: list[dict] | None = None,
) -> dict:
    """Submit the user's arena evaluation back to BlindBench."""
    payload: dict = {
        "blindPresentationId": blind_presentation_id,
        "bestResponseLabel": best_label,
    }
    if scores:
        payload["scores"] = scores
    with httpx.Client(base_url=BLINDBENCH_URL, timeout=10.0) as client:
        r = client.post("/api/evaluations", json=payload)
        r.raise_for_status()
        return r.json()


# ── JSON parsing ───────────────────────────────────────────────────────────────


def _try_parse_json(text: str) -> dict | None:
    """Best-effort JSON extraction from LLM text."""
    text = text.strip()

    # Strip markdown fences
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    # Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find outermost { ... } respecting string quoting
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


# ── Problem generation via Arena ───────────────────────────────────────────────


def generate_problem_via_arena(prompt: str) -> dict[str, Any]:
    """Send problem-generation prompt to Arena, get 2 responses.

    Returns dict with:
      - "primary": the parsed problem JSON (picked randomly from valid responses)
      - "code_versions": list of {label, typescript_code, python_solution} for each valid response
      - "blind_presentation_id": for later voting
    """
    prompt_data = _submit_prompt(prompt, category="coding")
    prompt_id = prompt_data["id"]

    _poll_until_ready(prompt_id)
    blind_data = _get_blind_responses(prompt_id)

    responses = blind_data["responses"]
    blind_presentation_id = blind_data["blindPresentationId"]

    # Try to parse each response as JSON
    valid: list[tuple[str, dict]] = []
    for resp in responses:
        parsed = _try_parse_json(resp["content"])
        if parsed is not None and "typescript_code" in parsed:
            valid.append((resp["label"], parsed))

    if not valid:
        raise ValueError(
            "Neither BlindBench response produced valid problem JSON. "
            f"Response A ({len(responses[0]['content'])} chars), "
            f"Response B ({len(responses[1]['content'])} chars)"
        )

    # Pick one randomly as the primary (used for test cases / reference)
    primary_label, primary = random.choice(valid)

    # Build code versions for all valid responses
    code_versions = [
        {
            "label": label,
            "typescript_code": data.get("typescript_code", ""),
            "python_solution": data.get("python_solution", ""),
        }
        for label, data in valid
    ]

    return {
        "primary": primary,
        "code_versions": code_versions,
        "blind_presentation_id": blind_presentation_id,
    }


# ── Code review via Arena ──────────────────────────────────────────────────────


def run_arena_review(
    typescript_code: str,
    reference_solution: str,
    user_code: str,
    test_summary: str,
) -> dict:
    """Full Arena flow: submit review prompt -> poll -> return 2 blind responses."""
    prompt = f"""\
You are a senior Python code reviewer. Evaluate the user's Python translation \
of a TypeScript function.

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

Provide a detailed code review covering:
- Correctness relative to test results
- Pythonic idioms (comprehensions, built-ins, unpacking, enumerate, dict.get)
- Code readability and simplicity
- Performance considerations
- Python naming conventions (snake_case, etc.)

Be specific and actionable. Reference exact lines or patterns from the user's code.
At the end, give a score from 0-100.
"""

    prompt_data = _submit_prompt(prompt, category="coding")
    prompt_id = prompt_data["id"]

    _poll_until_ready(prompt_id)
    blind_data = _get_blind_responses(prompt_id)

    return {
        "prompt_id": prompt_id,
        "blind_presentation_id": blind_data["blindPresentationId"],
        "responses": blind_data["responses"],
    }


# ── Solution explanation via Smart Router ──────────────────────────────────────


def explain_via_blindbench(typescript_code: str, python_solution: str) -> str:
    """Generate solution explanation using BlindBench Smart Router."""
    prompt = f"""\
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
"""
    return _call_router(prompt, category="coding")


# ── Image analysis via Smart Router ────────────────────────────────────────────


def analyze_image_via_blindbench(
    image_base64: str,
    prompt: str = (
        "What programming topic or subject does this image show? "
        "Describe it concisely in 1-2 sentences so it can be used to "
        "generate a TypeScript-to-Python coding problem."
    ),
) -> str:
    """Send an image + prompt to BlindBench Smart Router (uses vision-capable model)."""
    with httpx.Client(base_url=BLINDBENCH_URL, timeout=120.0) as client:
        r = client.post(
            "/api/router/complete",
            json={
                "content": prompt,
                "imageBase64": image_base64,
                "category": "image_analysis",
            },
        )
        r.raise_for_status()
        data = r.json()
        return data["response"]["content"]
