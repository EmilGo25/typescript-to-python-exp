"""Evaluation orchestrator combining test execution, AST analysis, and LLM feedback."""
from __future__ import annotations

import json
from dataclasses import dataclass

from app.services.ast_compare import compute_ast_similarity
from app.services.llm_service import evaluate_submission
from app.services.sandbox import run_user_code


@dataclass
class EvaluationResult:
    overall_score: float
    correctness_score: float
    ast_score: float
    llm_score: float
    test_results: list[dict]
    llm_feedback: str
    improvements: list[str]
    conventions: list[str]


def _compute_correctness(test_results: list[dict]) -> float:
    """Compute correctness score from test results (0–100)."""
    if not test_results:
        return 0.0
    passed = sum(1 for t in test_results if t.get("passed"))
    return round((passed / len(test_results)) * 100, 1)


def evaluate(
    user_code: str,
    reference_solution: str,
    typescript_code: str,
    func_name: str,
    test_cases: list[dict],
) -> EvaluationResult:
    """Run the full multi-layer evaluation pipeline.

    1. Execute user code against test cases in sandbox
    2. Compare AST structure with reference solution
    3. Get LLM evaluation and feedback

    Weights: correctness 50%, AST 15%, LLM 35%
    """
    # Layer 1: Correctness via sandboxed execution
    sandbox_result = run_user_code(user_code, func_name, test_cases)

    if sandbox_result.error:
        test_results = [{
            "passed": False,
            "input": "N/A",
            "expected": "N/A",
            "actual": "N/A",
            "error": sandbox_result.error,
        }]
        correctness_score = 0.0
    else:
        test_results = sandbox_result.results or []
        correctness_score = _compute_correctness(test_results)

    # Layer 2: AST structural similarity
    ast_score = compute_ast_similarity(user_code, reference_solution)

    # Layer 3: LLM evaluation
    passed_count = sum(1 for t in test_results if t.get("passed"))
    total_count = len(test_results)
    test_summary = f"{passed_count}/{total_count} tests passed"
    if sandbox_result.error:
        test_summary = f"Execution error: {sandbox_result.error}"

    try:
        llm_result = evaluate_submission(
            typescript_code=typescript_code,
            reference_solution=reference_solution,
            user_code=user_code,
            test_summary=test_summary,
        )
        llm_score = float(llm_result.get("score", 0))
        llm_feedback = llm_result.get("explanation", "")
        improvements = llm_result.get("improvements", [])
        conventions = llm_result.get("conventions", [])
    except Exception as e:
        llm_score = 0.0
        llm_feedback = f"LLM evaluation unavailable: {e}"
        improvements = []
        conventions = []

    # Combined score
    overall_score = round(
        correctness_score * 0.50 + ast_score * 0.15 + llm_score * 0.35,
        1,
    )

    return EvaluationResult(
        overall_score=overall_score,
        correctness_score=correctness_score,
        ast_score=ast_score,
        llm_score=llm_score,
        test_results=test_results,
        llm_feedback=llm_feedback,
        improvements=improvements,
        conventions=conventions,
    )
