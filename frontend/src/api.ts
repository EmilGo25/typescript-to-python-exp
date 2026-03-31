const BASE = '/api';

export interface TestCase {
  input: string;
  expected_output: string;
}

export interface Problem {
  id: number;
  difficulty: string;
  title: string;
  description: string;
  typescript_code: string;
  example_input: string;
  example_output: string;
  test_cases: TestCase[];
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
  llm_score: number;
  test_results: TestResult[];
  llm_feedback: string;
  improvements: string[];
  conventions: string[];
}

export interface Solution {
  problem_id: number;
  typescript_code: string;
  python_solution: string;
  explanation: string;
}

export async function generateProblem(difficulty: string): Promise<Problem> {
  const res = await fetch(`${BASE}/generate-problem`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ difficulty }),
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
