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


_FULL_PROBLEM_PROMPT = """\
You are an expert TypeScript and Python instructor. \
Generate a TypeScript-to-Python translation problem at {difficulty} difficulty \
focused on "{category}".

Write:
1. A short title
2. A description of what the function does
3. The full TypeScript function
4. The equivalent idiomatic Python function
5. An example input and output
6. 5 test cases

Return valid JSON with this structure:
{{"title":"...","description":"...","typescript_code":"...","python_solution":"...","func_name":"...","example_input":"...","example_output":"...","test_cases":[{{"input":"[arg]","expected_output":"result"}}]}}
"""


@router.post("/generate-problem-stream")
async def generate_problem_stream_endpoint(
    request: GenerateProblemRequest,
):
    """Stream problem generation directly — no arena wait.

    Streams two code implementations token-by-token from two different models
    via BlindBench router/stream. First token arrives in ~1-2s.
    """

    async def event_stream():
        category = request.category or "arrays"
        custom_subject = request.custom_subject if category == "custom" else None

        if custom_subject:
            base_prompt = _FULL_PROBLEM_PROMPT.replace(
                '"{category}"', f'the custom subject: {custom_subject}'
            ).format(difficulty=request.difficulty, category=custom_subject)
        else:
            base_prompt = _FULL_PROBLEM_PROMPT.format(
                difficulty=request.difficulty, category=category,
            )

        labels = ["Response A", "Response B"]
        full_texts: dict[str, str] = {}

        # Stream both versions sequentially (Ollama can only run one at a time)
        for label in labels:
            yield f"event: code_start\ndata: {json.dumps({'label': label})}\n\n"
            full_text = ""
            try:
                for event_type, data in stream_from_router(base_prompt, category="coding"):
                    if event_type == "token":
                        parsed = json.loads(data)
                        token = parsed.get("token", "")
                        full_text += token
                        yield f"event: code_token\ndata: {json.dumps({'label': label, 'token': token})}\n\n"
                    elif event_type == "done":
                        break
                    elif event_type == "error":
                        yield f"event: error\ndata: {data}\n\n"
                        break
            except Exception as e:
                yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"
                return

            full_texts[label] = full_text
            yield f"event: code_end\ndata: {json.dumps({'label': label})}\n\n"

        # Parse JSON from both responses to extract metadata
        from app.services.blindbench_client import _try_parse_json

        parsed_problems = {}
        for label, text in full_texts.items():
            parsed = _try_parse_json(text)
            if parsed and "typescript_code" in parsed:
                parsed_problems[label] = parsed

        if not parsed_problems:
            yield f"event: error\ndata: {json.dumps({'message': 'Could not parse problem JSON from responses'})}\n\n"
            return

        # Use first valid response for metadata
        primary_label = next(iter(parsed_problems))
        primary = parsed_problems[primary_label]

        # Normalize test cases
        for tc in primary.get("test_cases", []):
            if not isinstance(tc.get("input"), str):
                tc["input"] = json.dumps(tc["input"])
            if not isinstance(tc.get("expected_output"), str):
                tc["expected_output"] = json.dumps(tc["expected_output"])

        meta = {
            "title": primary.get("title", ""),
            "description": primary.get("description", ""),
            "example_input": primary.get("example_input", ""),
            "example_output": primary.get("example_output", ""),
            "func_name": primary.get("func_name", ""),
            "test_cases": primary.get("test_cases", []),
            "blind_presentation_id": None,
        }
        yield f"event: meta\ndata: {json.dumps(meta)}\n\n"

        # Send extracted code + solutions
        solutions = {}
        code_versions = {}
        for label, parsed in parsed_problems.items():
            solutions[label] = parsed.get("python_solution", "")
            code_versions[label] = parsed.get("typescript_code", "")

        yield f"event: solutions\ndata: {json.dumps(solutions)}\n\n"
        yield f"event: code_versions\ndata: {json.dumps(code_versions)}\n\n"
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
