const BASE = '/api';

export interface TestCase {
  input: string;
  expected_output: string;
}

export const CATEGORIES = [
  'arrays', 'objects', 'strings', 'classes', 'recursion', 'async', 'functions', 'custom',
] as const;
export type Category = typeof CATEGORIES[number];

export interface CodeVersion {
  label: string;
  typescript_code: string;
  python_solution: string;
}

export interface Problem {
  id: number;
  difficulty: string;
  category: string;
  title: string;
  description: string;
  typescript_code: string;
  example_input: string;
  example_output: string;
  test_cases: TestCase[];
  code_versions: CodeVersion[];
  blind_presentation_id: string | null;
}

export interface TestResult {
  passed: boolean;
  input: string;
  expected: string;
  actual: string;
  error: string | null;
}

export interface Evaluation {
  submission_id: number;
  problem_id: number;
  overall_score: number;
  correctness_score: number;
  ast_score: number;
  test_results: TestResult[];
  arena: ArenaReview | null;
}

export interface Solution {
  problem_id: number;
  typescript_code: string;
  python_solution: string;
  explanation: string;
}

export async function generateProblem(
  difficulty: string,
  category: string,
  customSubject?: string,
): Promise<Problem> {
  const res = await fetch(`${BASE}/generate-problem`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      difficulty,
      category,
      ...(customSubject ? { custom_subject: customSubject } : {}),
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to generate problem');
  }
  return res.json();
}

export async function submitSolution(problemId: number, userCode: string): Promise<Evaluation> {
  const res = await fetch(`${BASE}/submit-solution`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ problem_id: problemId, user_code: userCode }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to submit solution');
  }
  return res.json();
}

export async function getSolution(problemId: number): Promise<Solution> {
  const res = await fetch(`${BASE}/solution/${problemId}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to get solution');
  }
  return res.json();
}

// ---------- BlindBench Arena ----------

export interface ArenaBlindResponse {
  label: string;
  content: string;
  latency_ms: number;
}

export interface ArenaReview {
  prompt_id: string;
  blind_presentation_id: string;
  responses: ArenaBlindResponse[];
}

export async function submitArenaEvaluation(data: {
  blind_presentation_id: string;
  best_response_label: string;
  scores?: { response_label: string; score: number }[];
}): Promise<{ id: string }> {
  const res = await fetch(`${BASE}/arena-evaluate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to submit arena evaluation');
  }
  return res.json();
}

// ---------- Image ----------

export async function extractSubjectFromImage(
  imageData: string,
  mediaType: string,
): Promise<string> {
  const res = await fetch(`${BASE}/extract-subject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image_data: imageData, media_type: mediaType }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to extract subject from image');
  }
  const data = await res.json();
  return data.subject;
}
