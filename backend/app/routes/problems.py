"""API routes for problem generation, solution submission, and solution retrieval."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Problem, Submission, get_session
from app.models.schemas import (
    EvaluationResponse,
    GenerateProblemRequest,
    ProblemResponse,
    SolutionResponse,
    SubmitSolutionRequest,
    TestCase,
)
from app.services.evaluator import evaluate
from app.services.llm_service import explain_solution, generate_problem

router = APIRouter()


@router.post("/generate-problem", response_model=ProblemResponse)
async def generate_problem_endpoint(
    request: GenerateProblemRequest,
    session: AsyncSession = Depends(get_session),
) -> ProblemResponse:
    """Generate a new TypeScript-to-Python translation problem."""
    try:
        problem_data = generate_problem(request.difficulty)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM generation failed: {e}")

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

    # Embed func_name into the test_cases metadata for later use
    test_cases_with_meta = {
        "func_name": problem_data["func_name"],
        "cases": problem_data["test_cases"],
    }

    db_problem = Problem(
        difficulty=request.difficulty,
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
        title=db_problem.title,
        description=db_problem.description,
        typescript_code=db_problem.typescript_code,
        example_input=db_problem.example_input,
        example_output=db_problem.example_output,
        test_cases=[TestCase(**tc) for tc in problem_data["test_cases"]],
    )


@router.post("/submit-solution", response_model=EvaluationResponse)
async def submit_solution_endpoint(
    request: SubmitSolutionRequest,
    session: AsyncSession = Depends(get_session),
) -> EvaluationResponse:
    """Submit a Python solution for evaluation."""
    result = await session.execute(
        select(Problem).where(Problem.id == request.problem_id)
    )
    problem = result.scalar_one_or_none()
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")

    test_data = json.loads(problem.test_cases)
    func_name = test_data["func_name"]
    test_cases = test_data["cases"]

    eval_result = evaluate(
        user_code=request.user_code,
        reference_solution=problem.python_solution,
        typescript_code=problem.typescript_code,
        func_name=func_name,
        test_cases=test_cases,
    )

    submission = Submission(
        problem_id=request.problem_id,
        user_code=request.user_code,
        correctness_score=eval_result.correctness_score,
        ast_score=eval_result.ast_score,
        llm_score=eval_result.llm_score,
        overall_score=eval_result.overall_score,
        feedback=eval_result.llm_feedback,
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
        llm_score=eval_result.llm_score,
        test_results=eval_result.test_results,
        llm_feedback=eval_result.llm_feedback,
        improvements=eval_result.improvements,
        conventions=eval_result.conventions,
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
