import { useState } from 'react';
import Editor from '@monaco-editor/react';
import {
  generateProblem,
  submitSolution,
  getSolution,
  extractSubjectFromImage,
  submitArenaEvaluation,
  CATEGORIES,
  type Problem,
  type Evaluation,
  type Solution,
  type Category,
} from './api';
import ScorePanel from './components/ScorePanel';
import SolutionPanel from './components/SolutionPanel';
import ArenaReviewPanel from './components/ArenaReviewPanel';

type Difficulty = 'easy' | 'medium' | 'hard';

const DIFFICULTY_STYLES: Record<Difficulty, string> = {
  easy: 'bg-green-600 hover:bg-green-700',
  medium: 'bg-yellow-600 hover:bg-yellow-700',
  hard: 'bg-red-600 hover:bg-red-700',
};

const PYTHON_STARTER = '# Write your Python solution here\n\n';

export default function App() {
  const [difficulty, setDifficulty] = useState<Difficulty>('medium');
  const [category, setCategory] = useState<Category>('arrays');
  const [problem, setProblem] = useState<Problem | null>(null);
  const [userCode, setUserCode] = useState(PYTHON_STARTER);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [solution, setSolution] = useState<Solution | null>(null);
  const [customSubject, setCustomSubject] = useState('');
  const [imageFileName, setImageFileName] = useState('');
  const [codeVote, setCodeVote] = useState<string | null>(null);
  const [codeVoteSubmitted, setCodeVoteSubmitted] = useState(false);
  const [loading, setLoading] = useState('');
  const [error, setError] = useState('');

  async function handleGenerate() {
    setLoading('Generating problem...');
    setError('');
    setEvaluation(null);
    setSolution(null);
    setCodeVote(null);
    setCodeVoteSubmitted(false);
    setUserCode(PYTHON_STARTER);
    try {
      const subject = category === 'custom' ? customSubject : undefined;
      const p = await generateProblem(difficulty, category, subject);
      setProblem(p);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading('');
    }
  }

  function fileToBase64(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result as string;
        resolve(result.split(',')[1]);
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  async function handleImageUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setImageFileName(file.name);
    setLoading('Analyzing image...');
    setError('');
    try {
      const base64 = await fileToBase64(file);
      const subject = await extractSubjectFromImage(base64, file.type);
      setCustomSubject(subject);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading('');
    }
  }

  async function handleSubmit() {
    if (!problem) return;
    setLoading('Evaluating via BlindBench Arena...');
    setError('');
    setSolution(null);
    try {
      // Runs correctness + AST locally, then gets 2 blind reviews from BlindBench
      const ev = await submitSolution(problem.id, userCode);
      setEvaluation(ev);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading('');
    }
  }

  async function handleShowSolution() {
    if (!problem) return;
    setLoading('Loading solution...');
    setError('');
    try {
      const sol = await getSolution(problem.id);
      setSolution(sol);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading('');
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold tracking-tight">
              TS &rarr; Python <span className="text-blue-400">Translator Trainer</span>
            </h1>
            <p className="text-xs text-gray-500 mt-0.5">Master Python by translating TypeScript</p>
          </div>
          <div className="flex items-center gap-3">
            {/* Difficulty selector */}
            <div className="flex gap-1">
              {(['easy', 'medium', 'hard'] as Difficulty[]).map((d) => (
                <button
                  key={d}
                  onClick={() => setDifficulty(d)}
                  className={`px-3 py-1 text-xs font-medium rounded capitalize transition-colors ${
                    difficulty === d
                      ? DIFFICULTY_STYLES[d] + ' text-white'
                      : 'bg-gray-800 text-gray-400 hover:text-gray-200'
                  }`}
                >
                  {d}
                </button>
              ))}
            </div>
            {/* Category selector */}
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value as Category)}
              className="px-3 py-1 text-xs font-medium rounded bg-gray-800 text-gray-300 border border-gray-700 capitalize cursor-pointer hover:border-gray-500 transition-colors"
            >
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
            <button
              onClick={handleGenerate}
              disabled={!!loading || (category === 'custom' && !customSubject.trim())}
              className="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-sm font-medium rounded transition-colors"
            >
              {loading === 'Generating problem...' ? 'Generating...' : 'New Problem'}
            </button>
          </div>
        </div>
        {category === 'custom' && (
          <div className="max-w-7xl mx-auto mt-3 flex items-center gap-3">
            <input
              type="text"
              placeholder="Describe a custom subject (e.g. binary search trees, graph algorithms)..."
              value={customSubject}
              onChange={(e) => setCustomSubject(e.target.value)}
              className="flex-1 px-3 py-1.5 text-sm rounded bg-gray-800 text-gray-300 border border-gray-700 placeholder-gray-600 focus:border-blue-500 focus:outline-none transition-colors"
            />
            <span className="text-xs text-gray-600">or</span>
            <label className="px-3 py-1.5 text-xs font-medium rounded bg-gray-800 text-gray-300 border border-gray-700 cursor-pointer hover:border-gray-500 transition-colors whitespace-nowrap">
              Upload Image
              <input
                type="file"
                accept="image/png,image/jpeg,image/gif,image/webp"
                className="hidden"
                onChange={handleImageUpload}
              />
            </label>
            {imageFileName && (
              <span className="text-xs text-green-400 truncate max-w-[150px]">{imageFileName}</span>
            )}
          </div>
        )}
      </header>

      <main className="max-w-7xl mx-auto p-6">
        {error && (
          <div className="mb-4 px-4 py-2 bg-red-900/40 border border-red-700 rounded text-sm text-red-300">
            {error}
          </div>
        )}

        {loading && (
          <div className="mb-4 px-4 py-2 bg-blue-900/30 border border-blue-700 rounded text-sm text-blue-300 animate-pulse">
            {loading}
          </div>
        )}

        {!problem && !loading && (
          <div className="flex items-center justify-center h-96 text-gray-600">
            <div className="text-center">
              <p className="text-lg mb-2">Select a difficulty and click "New Problem" to start</p>
              <p className="text-sm">You'll get a TypeScript function to translate into Python</p>
            </div>
          </div>
        )}

        {problem && (
          <>
            {/* Problem description */}
            <div className="mb-4 p-4 bg-gray-900 rounded-lg border border-gray-800">
              <div className="flex items-center gap-3 mb-2">
                <h2 className="text-lg font-semibold">{problem.title}</h2>
                <span className={`text-xs px-2 py-0.5 rounded capitalize ${
                  problem.difficulty === 'easy' ? 'bg-green-900 text-green-300' :
                  problem.difficulty === 'medium' ? 'bg-yellow-900 text-yellow-300' :
                  'bg-red-900 text-red-300'
                }`}>
                  {problem.difficulty}
                </span>
                <span className="text-xs px-2 py-0.5 rounded capitalize bg-blue-900 text-blue-300">
                  {problem.category}
                </span>
              </div>
              <p className="text-sm text-gray-400 mb-2">{problem.description}</p>
              <div className="text-xs text-gray-500 font-mono">
                <span className="text-gray-600">Example:</span> {problem.example_input} &rarr; {problem.example_output}
              </div>
            </div>

            {/* Code panels — 2 arena versions + user solution */}
            {(problem.code_versions?.length ?? 0) >= 2 ? (
              <>
                {/* Two arena code versions side by side */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
                  {problem.code_versions!.map((cv) => (
                    <div key={cv.label}>
                      <div className="text-xs font-medium text-purple-400 mb-1 uppercase tracking-wide flex items-center gap-2">
                        {cv.label}
                        <span className="text-gray-600 normal-case">(read-only)</span>
                      </div>
                      <div className="rounded-lg overflow-hidden border border-purple-800/40">
                        <Editor
                          height="350px"
                          language="typescript"
                          value={cv.typescript_code}
                          theme="vs-dark"
                          options={{
                            readOnly: true,
                            minimap: { enabled: false },
                            fontSize: 13,
                            scrollBeyondLastLine: false,
                            lineNumbers: 'on',
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>

                {/* User's Python solution — full width */}
                <div className="mb-4">
                  <div className="text-xs font-medium text-green-400 mb-1 uppercase tracking-wide">
                    Your Python Solution
                  </div>
                  <div className="rounded-lg overflow-hidden border border-green-800/40">
                    <Editor
                      height="350px"
                      language="python"
                      value={userCode}
                      theme="vs-dark"
                      onChange={(v) => setUserCode(v ?? '')}
                      options={{
                        minimap: { enabled: false },
                        fontSize: 13,
                        scrollBeyondLastLine: false,
                        lineNumbers: 'on',
                        tabSize: 4,
                      }}
                    />
                  </div>
                </div>
              </>
            ) : (
              /* Fallback: single TypeScript + user solution */
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
                <div>
                  <div className="text-xs font-medium text-gray-500 mb-1 uppercase tracking-wide">TypeScript (read-only)</div>
                  <div className="rounded-lg overflow-hidden border border-gray-800">
                    <Editor
                      height="400px"
                      language="typescript"
                      value={problem.typescript_code}
                      theme="vs-dark"
                      options={{
                        readOnly: true,
                        minimap: { enabled: false },
                        fontSize: 13,
                        scrollBeyondLastLine: false,
                        lineNumbers: 'on',
                      }}
                    />
                  </div>
                </div>
                <div>
                  <div className="text-xs font-medium text-gray-500 mb-1 uppercase tracking-wide">Your Python Solution</div>
                  <div className="rounded-lg overflow-hidden border border-gray-800">
                    <Editor
                      height="400px"
                      language="python"
                      value={userCode}
                      theme="vs-dark"
                      onChange={(v) => setUserCode(v ?? '')}
                      options={{
                        minimap: { enabled: false },
                        fontSize: 13,
                        scrollBeyondLastLine: false,
                        lineNumbers: 'on',
                        tabSize: 4,
                      }}
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Vote: which code version is better */}
            {(problem.code_versions?.length ?? 0) >= 2 && (
              <div className="mb-4 p-3 bg-gray-900 rounded-lg border border-purple-800/30">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-purple-300 uppercase tracking-wide font-medium">
                    Which code version is better?
                  </span>
                  <div className="flex gap-2">
                    {problem.code_versions!.map((cv) => (
                      <button
                        key={cv.label}
                        onClick={async () => {
                          setCodeVote(cv.label);
                          if (problem.blind_presentation_id && !codeVoteSubmitted) {
                            try {
                              await submitArenaEvaluation({
                                blind_presentation_id: problem.blind_presentation_id,
                                best_response_label: cv.label,
                              });
                              setCodeVoteSubmitted(true);
                            } catch { /* best effort */ }
                          }
                        }}
                        disabled={codeVoteSubmitted}
                        className={`px-4 py-1.5 text-xs font-medium rounded transition-colors ${
                          codeVote === cv.label
                            ? 'bg-purple-600 text-white'
                            : 'bg-gray-800 text-gray-400 hover:text-gray-200'
                        }`}
                      >
                        {cv.label}
                        {codeVote === cv.label && codeVoteSubmitted && ' ✓'}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Action buttons */}
            <div className="flex gap-3 mb-6">
              <button
                onClick={handleSubmit}
                disabled={!!loading}
                className="px-6 py-2 bg-green-600 hover:bg-green-700 disabled:opacity-50 font-medium rounded transition-colors"
              >
                {loading && loading.startsWith('Evaluating') ? 'Evaluating...' : 'Submit Solution'}
              </button>
              <button
                onClick={handleShowSolution}
                disabled={!!loading}
                className="px-6 py-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 font-medium rounded transition-colors"
              >
                {loading === 'Loading solution...' ? 'Loading...' : 'Show Solution'}
              </button>
            </div>

            {/* Results */}
            {evaluation && (
              <div className="p-5 bg-gray-900 rounded-lg border border-gray-800 mb-4">
                <ScorePanel evaluation={evaluation} />
              </div>
            )}
            {evaluation?.arena && (
              <div className="p-5 bg-gray-900 rounded-lg border border-purple-800/50 mb-4">
                <ArenaReviewPanel
                  arenaReview={evaluation.arena}
                  onEvaluated={() => {}}
                />
              </div>
            )}
            {solution && (
              <div className="p-5 bg-gray-900 rounded-lg border border-gray-800">
                <SolutionPanel solution={solution} />
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
