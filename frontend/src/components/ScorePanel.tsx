import type { Evaluation } from '../api';

function ScoreBadge({ label, score, color }: { label: string; score: number; color: string }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <div className={`text-2xl font-bold ${color}`}>
        {Math.round(score)}
      </div>
      <div className="text-xs text-gray-400 uppercase tracking-wide">{label}</div>
    </div>
  );
}

function scoreColor(score: number): string {
  if (score >= 80) return 'text-green-400';
  if (score >= 50) return 'text-yellow-400';
  return 'text-red-400';
}

export default function ScorePanel({ evaluation }: { evaluation: Evaluation }) {
  return (
    <div className="space-y-6">
      {/* Overall score */}
      <div className="text-center">
        <div className={`text-5xl font-bold ${scoreColor(evaluation.overall_score)}`}>
          {Math.round(evaluation.overall_score)}
        </div>
        <div className="text-sm text-gray-400 mt-1">Overall Score</div>
        <div className="text-xs text-gray-600 mt-0.5">Tests 70% + Structure 30%</div>
      </div>

      {/* Breakdown */}
      <div className="flex justify-around">
        <ScoreBadge label="Tests" score={evaluation.correctness_score} color={scoreColor(evaluation.correctness_score)} />
        <ScoreBadge label="Structure" score={evaluation.ast_score} color={scoreColor(evaluation.ast_score)} />
      </div>

      {/* Test results */}
      <div>
        <h3 className="text-sm font-semibold text-gray-300 mb-2">Test Results</h3>
        <div className="space-y-1">
          {evaluation.test_results.map((t, i) => (
            <div key={i} className={`text-xs px-2 py-1 rounded font-mono ${t.passed ? 'bg-green-900/30 text-green-300' : 'bg-red-900/30 text-red-300'}`}>
              {t.passed ? 'PASS' : 'FAIL'} — Input: {t.input}
              {!t.passed && t.error && <div className="text-red-400 mt-0.5">Error: {t.error}</div>}
              {!t.passed && !t.error && <div className="text-red-400 mt-0.5">Expected: {t.expected} | Got: {t.actual}</div>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
