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

export interface StreamCallbacks {
  onMeta: (meta: {
    title: string;
    description: string;
    example_input: string;
    example_output: string;
    func_name: string;
    test_cases: TestCase[];
    blind_presentation_id: string | null;
  }) => void;
  onCodeStart: (label: string) => void;
  onCodeToken: (label: string, token: string) => void;
  onCodeEnd: (label: string) => void;
  onSolutions: (solutions: Record<string, string>) => void;
  onCodeVersions: (codeVersions: Record<string, string>) => void;
  onDone: () => void;
  onError: (message: string) => void;
}

export async function generateProblemStream(
  difficulty: string,
  category: string,
  callbacks: StreamCallbacks,
  customSubject?: string,
): Promise<void> {
  const res = await fetch(`${BASE}/generate-problem-stream`, {
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
    callbacks.onError(err.detail || 'Failed to start generation');
    return;
  }

  const reader = res.body?.getReader();
  if (!reader) { callbacks.onError('No response body'); return; }

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    while (buffer.includes('\n\n')) {
      const idx = buffer.indexOf('\n\n');
      const eventStr = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);

      if (!eventStr.trim()) continue;

      let eventType: string | null = null;
      let data: string | null = null;
      for (const line of eventStr.split('\n')) {
        if (line.startsWith('event:')) eventType = line.slice(6).trim();
        else if (line.startsWith('data:')) data = line.slice(5).trim();
      }
      if (!eventType || !data) continue;

      const parsed = JSON.parse(data);
      switch (eventType) {
        case 'meta': callbacks.onMeta(parsed); break;
        case 'code_start': callbacks.onCodeStart(parsed.label); break;
        case 'code_token': callbacks.onCodeToken(parsed.label, parsed.token); break;
        case 'code_end': callbacks.onCodeEnd(parsed.label); break;
        case 'solutions': callbacks.onSolutions(parsed); break;
        case 'code_versions': callbacks.onCodeVersions(parsed); break;
        case 'done': callbacks.onDone(); break;
        case 'error': callbacks.onError(parsed.message); break;
      }
    }
  }
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
