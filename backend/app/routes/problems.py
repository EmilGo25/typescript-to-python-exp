"""API routes for problem generation, solution submission, and solution retrieval."""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.models.database import Problem, Submission, get_session
from app.models.schemas import (
    ArenaEvaluationRequest,
    ArenaEvaluationResponse,
    ArenaReviewResponse,
    CodeVersion,
    EvaluationResponse,
    ExtractSubjectRequest,
    ExtractSubjectResponse,
    GenerateProblemRequest,
    ProblemResponse,
    SolutionResponse,
    SubmitSolutionRequest,
    TestCase,
)
from app.services.blindbench_client import run_arena_review, submit_evaluation, stream_from_router
from app.services.evaluator import evaluate
from app.services.llm_service import (
    explain_solution,
    extract_subject_from_image,
    generate_problem,
)

router = APIRouter()


@router.post("/generate-problem", response_model=ProblemResponse)
async def generate_problem_endpoint(
    request: GenerateProblemRequest,
    session: AsyncSession = Depends(get_session),
) -> ProblemResponse:
    """Generate a new TypeScript-to-Python translation problem."""
    try:
        category = request.category or "arrays"
        custom_subject = request.custom_subject if category == "custom" else None
        # generate_problem returns {primary, code_versions, blind_presentation_id}
        arena_result = await asyncio.to_thread(
            generate_problem, request.difficulty, category, custom_subject
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM generation failed: {e}")

    problem_data = arena_result["primary"]
    code_versions_raw = arena_result["code_versions"]
    blind_presentation_id = arena_result.get("blind_presentation_id")

    # Validate required fields
    required = [
        "title", "description", "typescript_code", "python_solution",
        "func_name", "example_input", "example_output", "test_cases",
    ]
    for field in required:
        if field not in problem_data:
            raise HTTPException(
                status_code=502,
                detail=f"LLM response missing required field: {field}",
            )

    # Normalize test cases
    for tc in problem_data["test_cases"]:
        if not isinstance(tc.get("input"), str):
            tc["input"] = json.dumps(tc["input"])
        if not isinstance(tc.get("expected_output"), str):
            tc["expected_output"] = json.dumps(tc["expected_output"])

    test_cases_with_meta = {
        "func_name": problem_data["func_name"],
        "cases": problem_data["test_cases"],
    }

    db_problem = Problem(
        difficulty=request.difficulty,
        category=category,
        custom_subject=custom_subject,
        title=problem_data["title"],
        description=problem_data["description"],
        typescript_code=problem_data["typescript_code"],
        python_solution=problem_data["python_solution"],
        test_cases=json.dumps(test_cases_with_meta),
        example_input=problem_data["example_input"],
        example_output=problem_data["example_output"],
    )
    session.add(db_problem)
    await session.commit()
    await session.refresh(db_problem)

    return ProblemResponse(
        id=db_problem.id,
        difficulty=db_problem.difficulty,
        category=db_problem.category,
        title=db_problem.title,
        description=db_problem.description,
        typescript_code=db_problem.typescript_code,
        example_input=db_problem.example_input,
        example_output=db_problem.example_output,
        test_cases=[TestCase(**tc) for tc in problem_data["test_cases"]],
        code_versions=[CodeVersion(**cv) for cv in code_versions_raw],
        blind_presentation_id=blind_presentation_id,
    )


_ALT_IMPL_PROMPT = """\
Write a DIFFERENT TypeScript implementation of the same function below. \
Same function name, same parameters, same behavior, but use a different approach or style.

Original implementation:
```typescript
{original_code}
```

Write ONLY the TypeScript code. No markdown fences, no explanation. \
Same function name and signature, different implementation logic.
"""


@router.post("/generate-problem-stream")
async def generate_problem_stream_endpoint(
    request: GenerateProblemRequest,
):
    """Stream problem generation:
    1. Stream Response A: full problem JSON (title, code, tests, solution)
    2. Parse Response A to extract the spec
    3. Stream Response B: a DIFFERENT implementation of the same function
    """

    async def event_stream():
        category = request.category or "arrays"
        custom_subject = request.custom_subject if category == "custom" else None

        from app.services.blindbench_client import _try_parse_json
        from app.services.llm_service import (
            _PROBLEM_PROMPT_TEMPLATE,
            _CUSTOM_PROBLEM_PROMPT_TEMPLATE,
        )

        # Build the problem generation prompt (same as non-streaming)
        if custom_subject:
            gen_prompt = _CUSTOM_PROBLEM_PROMPT_TEMPLATE.format(
                difficulty=request.difficulty, custom_subject=custom_subject
            )
        else:
            gen_prompt = _PROBLEM_PROMPT_TEMPLATE.format(
                difficulty=request.difficulty, category=category
            )

        # Step 1: Stream Response A (full problem with code)
        yield f"event: code_start\ndata: {json.dumps({'label': 'Response A'})}\n\n"

        full_text_a = ""
        try:
            for event_type, data in stream_from_router(gen_prompt, category="coding"):
                if event_type == "token":
                    parsed = json.loads(data)
                    token = parsed.get("token", "")
                    full_text_a += token
                    yield f"event: code_token\ndata: {json.dumps({'label': 'Response A', 'token': token})}\n\n"
                elif event_type == "done":
                    break
                elif event_type == "error":
                    yield f"event: error\ndata: {data}\n\n"
                    return
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"
            return

        yield f"event: code_end\ndata: {json.dumps({'label': 'Response A'})}\n\n"

        # Parse Response A to extract problem spec
        # Strip all markdown fence variants
        parse_text = full_text_a.strip()
        for fence in ["```json", "```typescript", "```"]:
            if parse_text.startswith(fence):
                parse_text = parse_text[len(fence):]
                break
        if parse_text.endswith("```"):
            parse_text = parse_text[:-3]
        parse_text = parse_text.strip()

        problem_a = _try_parse_json(parse_text)
        if not problem_a or "typescript_code" not in problem_a:
            # Retry: try parsing the raw text directly
            problem_a = _try_parse_json(full_text_a)

        if not problem_a or "typescript_code" not in problem_a:
            logger.error("Failed to parse Response A. Length=%d, first 200: %s",
                         len(full_text_a), full_text_a[:200])
            yield f"event: error\ndata: {json.dumps({'message': 'Could not parse problem from Response A. Try again.'})}\n\n"
            return

        # Normalize test cases
        for tc in problem_a.get("test_cases", []):
            if not isinstance(tc.get("input"), str):
                tc["input"] = json.dumps(tc["input"])
            if not isinstance(tc.get("expected_output"), str):
                tc["expected_output"] = json.dumps(tc["expected_output"])

        # Emit metadata from Response A
        meta = {
            "title": problem_a.get("title", ""),
            "description": problem_a.get("description", ""),
            "example_input": problem_a.get("example_input", ""),
            "example_output": problem_a.get("example_output", ""),
            "func_name": problem_a.get("func_name", ""),
            "test_cases": problem_a.get("test_cases", []),
            "blind_presentation_id": None,
        }
        yield f"event: meta\ndata: {json.dumps(meta)}\n\n"

        # Replace raw JSON in Response A panel with just the clean TypeScript code
        code_a = problem_a["typescript_code"]
        yield f"event: code_versions\ndata: {json.dumps({'Response A': code_a})}\n\n"

        # Step 2: Stream Response B — different implementation of the SAME function
        alt_prompt = _ALT_IMPL_PROMPT.format(original_code=code_a)

        yield f"event: code_start\ndata: {json.dumps({'label': 'Response B'})}\n\n"

        full_text_b = ""
        try:
            for event_type, data in stream_from_router(alt_prompt, category="coding"):
                if event_type == "token":
                    parsed = json.loads(data)
                    token = parsed.get("token", "")
                    full_text_b += token
                    yield f"event: code_token\ndata: {json.dumps({'label': 'Response B', 'token': token})}\n\n"
                elif event_type == "done":
                    break
                elif event_type == "error":
                    yield f"event: error\ndata: {data}\n\n"
                    return
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"
            return

        # Strip markdown fences
        code_b = full_text_b.strip()
        if code_b.startswith("```"):
            code_b = code_b.split("\n", 1)[1] if "\n" in code_b else code_b[3:]
            if code_b.endswith("```"):
                code_b = code_b[:-3]
            code_b = code_b.strip()

        yield f"event: code_end\ndata: {json.dumps({'label': 'Response B'})}\n\n"
        yield f"event: code_versions\ndata: {json.dumps({'Response B': code_b})}\n\n"

        # Send Python solution from Response A
        py_code = problem_a.get("python_solution", "")
        solutions = {"Response A": py_code, "Response B": py_code}
        yield f"event: solutions\ndata: {json.dumps(solutions)}\n\n"
        yield f"event: done\ndata: {json.dumps({'status': 'complete'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/extract-subject", response_model=ExtractSubjectResponse)
async def extract_subject_endpoint(
    request: ExtractSubjectRequest,
) -> ExtractSubjectResponse:
    """Analyze an uploaded image to extract a programming subject."""
    try:
        subject = extract_subject_from_image(request.image_data, request.media_type)
        return ExtractSubjectResponse(subject=subject)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Image analysis failed: {e}")


@router.post("/submit-solution", response_model=EvaluationResponse)
async def submit_solution_endpoint(
    request: SubmitSolutionRequest,
    session: AsyncSession = Depends(get_session),
) -> EvaluationResponse:
    """Submit a Python solution for evaluation.

    Runs correctness + AST locally, then sends code review to BlindBench Arena
    to get 2 blind reviews from competing models.
    """
    result = await session.execute(
        select(Problem).where(Problem.id == request.problem_id)
    )
    problem = result.scalar_one_or_none()
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")

    test_data = json.loads(problem.test_cases)
    func_name = test_data["func_name"]
    test_cases = test_data["cases"]

    # Layer 1+2: Correctness + AST (local, fast)
    eval_result = evaluate(
        user_code=request.user_code,
        reference_solution=problem.python_solution,
        typescript_code=problem.typescript_code,
        func_name=func_name,
        test_cases=test_cases,
    )

    # Build test summary for arena review prompt
    passed_count = sum(1 for t in eval_result.test_results if t.get("passed"))
    total_count = len(eval_result.test_results)
    test_summary = f"{passed_count}/{total_count} tests passed"
    if total_count == 1 and eval_result.test_results[0].get("error"):
        test_summary = f"Execution error: {eval_result.test_results[0]['error']}"

    # Layer 3: Arena review via BlindBench (2 blind reviews)
    # run_arena_review is sync (uses httpx + time.sleep polling),
    # so run it in a thread to avoid blocking the async event loop
    arena = None
    try:
        arena_data = await asyncio.to_thread(
            run_arena_review,
            typescript_code=problem.typescript_code,
            reference_solution=problem.python_solution,
            user_code=request.user_code,
            test_summary=test_summary,
        )
        arena = ArenaReviewResponse(**arena_data)
        logger.info("Arena review: %d responses received", len(arena_data.get("responses", [])))
    except Exception as e:
        logger.error("Arena review failed: %s", e, exc_info=True)

    # Persist submission
    submission = Submission(
        problem_id=request.problem_id,
        user_code=request.user_code,
        correctness_score=eval_result.correctness_score,
        ast_score=eval_result.ast_score,
        llm_score=0,
        overall_score=eval_result.overall_score,
        feedback="",
    )
    session.add(submission)
    await session.commit()
    await session.refresh(submission)

    return EvaluationResponse(
        submission_id=submission.id,
        problem_id=request.problem_id,
        overall_score=eval_result.overall_score,
        correctness_score=eval_result.correctness_score,
        ast_score=eval_result.ast_score,
        test_results=eval_result.test_results,
        arena=arena,
    )


@router.get("/solution/{problem_id}", response_model=SolutionResponse)
async def get_solution_endpoint(
    problem_id: int,
    session: AsyncSession = Depends(get_session),
) -> SolutionResponse:
    """Retrieve the reference solution for a problem with explanation."""
    result = await session.execute(
        select(Problem).where(Problem.id == problem_id)
    )
    problem = result.scalar_one_or_none()
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")

    try:
        explanation = explain_solution(
            typescript_code=problem.typescript_code,
            python_solution=problem.python_solution,
        )
    except Exception:
        explanation = "Explanation unavailable — check your API key configuration."

    return SolutionResponse(
        problem_id=problem.id,
        typescript_code=problem.typescript_code,
        python_solution=problem.python_solution,
        explanation=explanation,
    )


# ---------- BlindBench Arena endpoints ----------


@router.post("/arena-review/{problem_id}", response_model=ArenaReviewResponse)
async def arena_review_endpoint(
    problem_id: int,
    request: SubmitSolutionRequest,
    session: AsyncSession = Depends(get_session),
) -> ArenaReviewResponse:
    """Send the code review to BlindBench Arena and return 2 blind reviews."""
    result = await session.execute(
        select(Problem).where(Problem.id == problem_id)
    )
    problem = result.scalar_one_or_none()
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")

    test_data = json.loads(problem.test_cases)
    func_name = test_data["func_name"]
    test_cases = test_data["cases"]

    # Run correctness tests to build the test summary
    from app.services.sandbox import run_user_code

    sandbox_result = run_user_code(request.user_code, func_name, test_cases)
    if sandbox_result.error:
        test_summary = f"Execution error: {sandbox_result.error}"
    else:
        results = sandbox_result.results or []
        passed = sum(1 for t in results if t.get("passed"))
        test_summary = f"{passed}/{len(results)} tests passed"

    try:
        arena_data = run_arena_review(
            typescript_code=problem.typescript_code,
            reference_solution=problem.python_solution,
            user_code=request.user_code,
            test_summary=test_summary,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"BlindBench Arena unavailable: {e}",
        )

    return ArenaReviewResponse(**arena_data)


@router.post("/arena-evaluate", response_model=ArenaEvaluationResponse)
async def arena_evaluate_endpoint(
    request: ArenaEvaluationRequest,
) -> ArenaEvaluationResponse:
    """Submit the user's arena evaluation (best pick + scores) to BlindBench."""
    scores = None
    if request.scores:
        scores = [
            {"responseLabel": s.response_label, "score": s.score}
            for s in request.scores
        ]

    try:
        result = submit_evaluation(
            blind_presentation_id=request.blind_presentation_id,
            best_label=request.best_response_label,
            scores=scores,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"BlindBench evaluation failed: {e}",
        )

    return ArenaEvaluationResponse(id=result["id"])
