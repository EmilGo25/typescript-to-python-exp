import { useState } from 'react';
import type { ArenaReview } from '../api';
import { submitArenaEvaluation } from '../api';

interface Props {
  arenaReview: ArenaReview;
  onEvaluated: () => void;
}

export default function ArenaReviewPanel({ arenaReview, onEvaluated }: Props) {
  const [scores, setScores] = useState<Record<string, number>>({});
  const [bestLabel, setBestLabel] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async () => {
    if (!bestLabel) return;
    setSubmitting(true);
    setError('');

    try {
      const scoreArray = Object.entries(scores).map(([label, score]) => ({
        response_label: label,
        score,
      }));

      await submitArenaEvaluation({
        blind_presentation_id: arenaReview.blind_presentation_id,
        best_response_label: bestLabel,
        scores: scoreArray.length > 0 ? scoreArray : undefined,
      });

      setSubmitted(true);
      onEvaluated();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div className="text-center py-6">
        <div className="text-green-400 text-lg font-semibold mb-2">
          Arena evaluation submitted!
        </div>
        <p className="text-sm text-gray-400">
          You selected <span className="text-white font-medium">{bestLabel}</span> as the better review.
          Your vote helps train the smart model router.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-purple-300 uppercase tracking-wide">
          Arena: Compare AI Reviews
        </h3>
        <span className="text-xs text-gray-500">
          Two anonymous models reviewed your code — pick the better review
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {arenaReview.responses.map((resp) => {
          const isSelected = bestLabel === resp.label;
          return (
            <div
              key={resp.label}
              className={`rounded-lg border p-4 transition-all cursor-pointer ${
                isSelected
                  ? 'border-purple-500 bg-purple-900/20'
                  : 'border-gray-700 bg-gray-800/50 hover:border-gray-500'
              }`}
              onClick={() => setBestLabel(resp.label)}
            >
              {/* Header */}
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-sm">{resp.label}</span>
                  <span className="text-xs text-gray-500">
                    {(resp.latency_ms / 1000).toFixed(1)}s
                  </span>
                </div>
                {isSelected && (
                  <span className="text-xs px-2 py-0.5 rounded bg-purple-600 text-white">
                    Best
                  </span>
                )}
              </div>

              {/* Content */}
              <div className="bg-gray-900 rounded p-3 max-h-64 overflow-y-auto mb-3">
                <pre className="text-xs text-gray-300 whitespace-pre-wrap font-mono leading-relaxed">
                  {resp.content}
                </pre>
              </div>

              {/* Score buttons */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500">Score:</span>
                <div className="flex gap-1">
                  {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
                    <button
                      key={n}
                      onClick={(e) => {
                        e.stopPropagation();
                        setScores((prev) => ({ ...prev, [resp.label]: n }));
                      }}
                      className={`w-6 h-6 rounded text-xs font-medium transition-colors ${
                        scores[resp.label] === n
                          ? 'bg-purple-600 text-white'
                          : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
                      }`}
                    >
                      {n}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {error && (
        <div className="text-sm text-red-400 bg-red-900/20 px-3 py-2 rounded">
          {error}
        </div>
      )}

      <div className="flex justify-end">
        <button
          onClick={handleSubmit}
          disabled={!bestLabel || submitting}
          className="px-6 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 font-medium rounded transition-colors text-sm"
        >
          {submitting
            ? 'Submitting...'
            : bestLabel
              ? 'Submit Arena Vote'
              : 'Select the better review first'}
        </button>
      </div>
    </div>
  );
}
