"""API routes for problem generation, solution submission, and solution retrieval."""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
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
from app.services.blindbench_client import run_arena_review, submit_evaluation
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
