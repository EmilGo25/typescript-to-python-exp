# TS → Python Translator Trainer

A training tool for experienced TypeScript developers learning Python. The app presents TypeScript functions and challenges you to rewrite them in idiomatic Python, then provides multi-layered feedback.

## Features

- **Dynamic problem generation** — LLM-generated problems at easy/medium/hard difficulty
- **Split-panel editor** — TypeScript (read-only) + Python (Monaco Editor) side by side
- **Multi-layer evaluation**:
  - **Correctness** — sandboxed test execution (50% of score)
  - **Structural similarity** — AST comparison with reference solution (15%)
  - **AI code review** — LLM-based evaluation with detailed feedback (35%)
- **Reference solutions** with explanations of Pythonic idioms
- **Python convention coaching** — specific suggestions for comprehensions, unpacking, built-ins, etc.

## Prerequisites

- Python 3.9+
- Node.js 18+
- An [Anthropic API key](https://console.anthropic.com/)

## Setup

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure API key
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# Start the server
uvicorn app.main:app --reload
```

The API runs at `http://localhost:8000`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The UI runs at `http://localhost:5173` and proxies API requests to the backend.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/generate-problem` | Generate a new translation problem |
| POST | `/api/submit-solution` | Submit Python code for evaluation |
| GET | `/api/solution/{id}` | Get reference solution with explanation |
| GET | `/api/health` | Health check |

## Architecture

```
backend/
  app/
    main.py              # FastAPI app + CORS + lifespan
    models/
      database.py        # SQLAlchemy models + SQLite
      schemas.py         # Pydantic request/response schemas
    routes/
      problems.py        # API endpoints
    services/
      sandbox.py         # Sandboxed code execution (subprocess + restricted builtins)
      ast_compare.py     # AST structural similarity scoring
      llm_service.py     # Claude API: problem gen, evaluation, explanations
      evaluator.py       # Orchestrates sandbox + AST + LLM scoring

frontend/
  src/
    App.tsx              # Main app with split-panel layout
    api.ts               # API client
    components/
      ScorePanel.tsx     # Score breakdown + test results + feedback
      SolutionPanel.tsx  # Reference solution + explanation viewer
```

## Security

User-submitted Python code runs in a sandboxed subprocess with:
- Restricted `__builtins__` (no `open`, `exec`, `eval`, `__import__` for unsafe modules)
- Allowlisted imports only (math, itertools, collections, etc.)
- 5-second execution timeout
- Empty environment variables
- Stdout size limit
