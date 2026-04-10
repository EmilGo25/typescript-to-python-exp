from typing import List, Optional

from pydantic import BaseModel, Field


# ---------- Request schemas ----------

CATEGORIES = [
    "arrays",
    "objects",
    "strings",
    "classes",
    "recursion",
    "async",
    "functions",
]


class GenerateProblemRequest(BaseModel):
    difficulty: str = Field(
        default="medium",
        pattern="^(easy|medium|hard)$",
        description="Problem difficulty: easy, medium, or hard",
    )
    category: Optional[str] = Field(
        default=None,
        description="Language category: arrays, objects, strings, classes, recursion, async, functions, custom",
    )
    custom_subject: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Custom subject text when category is 'custom'",
    )


class SubmitSolutionRequest(BaseModel):
    problem_id: int
    user_code: str = Field(..., min_length=1, max_length=10_000)


# ---------- Response schemas ----------

class TestCase(BaseModel):
    input: str
    expected_output: str


class CodeVersion(BaseModel):
    label: str  # "Response A" / "Response B"
    typescript_code: str
    python_solution: str


class ProblemResponse(BaseModel):
    id: int
    difficulty: str
    category: str
    title: str
    description: str
    typescript_code: str  # primary version (used for tests)
    example_input: str
    example_output: str
    test_cases: List[TestCase]
    # Two code versions from BlindBench Arena
    code_versions: List[CodeVersion]
    blind_presentation_id: Optional[str] = None


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
    test_results: List[TestResult]
    # Arena review data (2 blind reviews from BlindBench)
    arena: Optional["ArenaReviewResponse"] = None


class SolutionResponse(BaseModel):
    problem_id: int
    typescript_code: str
    python_solution: str
    explanation: str


# ---------- Arena review schemas ----------


class ArenaBlindResponse(BaseModel):
    label: str
    content: str
    latency_ms: int


class ArenaReviewResponse(BaseModel):
    prompt_id: str
    blind_presentation_id: str
    responses: List[ArenaBlindResponse]


class ArenaScoreInput(BaseModel):
    response_label: str
    score: int = Field(..., ge=1, le=10)


class ArenaEvaluationRequest(BaseModel):
    blind_presentation_id: str
    best_response_label: str
    scores: Optional[List[ArenaScoreInput]] = None


class ArenaEvaluationResponse(BaseModel):
    id: str
    status: str = "submitted"


# ---------- Image schemas ----------


class ExtractSubjectRequest(BaseModel):
    image_data: str = Field(..., description="Base64-encoded image data")
    media_type: str = Field(
        default="image/png",
        pattern=r"^image/(png|jpeg|gif|webp)$",
        description="Image MIME type",
    )


class ExtractSubjectResponse(BaseModel):
    subject: str
