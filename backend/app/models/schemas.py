from typing import List, Optional

from pydantic import BaseModel, Field


# ---------- Request schemas ----------

class GenerateProblemRequest(BaseModel):
    difficulty: str = Field(
        default="medium",
        pattern="^(easy|medium|hard)$",
        description="Problem difficulty: easy, medium, or hard",
    )


class SubmitSolutionRequest(BaseModel):
    problem_id: int
    user_code: str = Field(..., min_length=1, max_length=10_000)


# ---------- Response schemas ----------

class TestCase(BaseModel):
    input: str
    expected_output: str


class ProblemResponse(BaseModel):
    id: int
    difficulty: str
    title: str
    description: str
    typescript_code: str
    example_input: str
    example_output: str
    test_cases: List[TestCase]


class TestResult(BaseModel):
    passed: bool
    input: str
    expected: str
    actual: str
    error: Optional[str] = None


class EvaluationResponse(BaseModel):
    submission_id: int
    problem_id: int
    overall_score: float = Field(..., ge=0, le=100)
    correctness_score: float = Field(..., ge=0, le=100)
    ast_score: float = Field(..., ge=0, le=100)
    llm_score: float = Field(..., ge=0, le=100)
    test_results: List[TestResult]
    llm_feedback: str
    improvements: List[str]
    conventions: List[str]


class SolutionResponse(BaseModel):
    problem_id: int
    typescript_code: str
    python_solution: str
    explanation: str
