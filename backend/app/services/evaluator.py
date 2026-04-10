"""Evaluation orchestrator — test execution + AST analysis.

LLM review is handled separately via BlindBench Arena (2 blind reviews shown to user).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.ast_compare import compute_ast_similarity
from app.services.sandbox import run_user_code


@dataclass
class EvaluationResult:
    overall_score: float
    correctness_score: float
    ast_score: float
    test_results: list[dict]


def _compute_correctness(test_results: list[dict]) -> float:
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
    """Run correctness + AST evaluation.

    Weights: correctness 70%, AST 30%.
    LLM review is provided separately by BlindBench Arena.
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

    # Combined score (no LLM layer — arena handles review separately)
    overall_score = round(
        correctness_score * 0.70 + ast_score * 0.30,
        1,
    )

    return EvaluationResult(
        overall_score=overall_score,
        correctness_score=correctness_score,
        ast_score=ast_score,
        test_results=test_results,
    )
