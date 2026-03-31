import Editor from '@monaco-editor/react';
import type { Solution } from '../api';

export default function SolutionPanel({ solution }: { solution: Solution }) {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-green-300 mb-2">Reference Solution</h3>
        <div className="rounded-lg overflow-hidden border border-gray-700">
          <Editor
            height="250px"
            language="python"
            value={solution.python_solution}
            theme="vs-dark"
            options={{ readOnly: true, minimap: { enabled: false }, fontSize: 13, scrollBeyondLastLine: false }}
          />
        </div>
      </div>
      <div>
        <h3 className="text-sm font-semibold text-gray-300 mb-2">Explanation</h3>
        <p className="text-sm text-gray-400 whitespace-pre-wrap">{solution.explanation}</p>
      </div>
    </div>
  );
}
