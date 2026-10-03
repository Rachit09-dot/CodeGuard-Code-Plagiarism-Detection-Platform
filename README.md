# Code Plagiarism Detection Platform

Python-only plagiarism detection system for comparing uploaded Python submissions with token normalization, k-gram hashing, and MOSS-style winnowing.

## Overview

This project contains:

- a FastAPI backend for uploads, analysis sessions, and comparison results
- a React/Vite frontend for selecting Python submissions and viewing the summary
- a Python similarity engine that compares normalized token streams
- SQLite persistence for analysis sessions, submissions, and result records

The implementation is intentionally Python-only. The upload flow accepts only `.py` files and rejects other extensions such as `.txt`, `.java`, `.cpp`, and `.exe`.

## Setup

### 1. Install Python dependencies

```bash
cd "c:\Users\Rachit kumar\Downloads\code plagrism"
python -m pip install -r requirements.txt
```

### 2. Start the backend

```bash
cd "c:\Users\Rachit kumar\Downloads\code plagrism"
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
```

### 3. Start the frontend

```bash
cd "c:\Users\Rachit kumar\Downloads\code plagrism\frontend"
npm install
npm run dev -- --host 0.0.0.0 --port 3000
```

Then open:

```text
http://127.0.0.1:3000
```

## API endpoints

- `GET /api/health` — health check
- `POST /api/upload` — upload Python files and create a new analysis session
- `GET /api/submissions` — list submissions for a given session
- `POST /api/analyze` — analyze submissions for the current session only
- `POST /api/compare` — compare two submissions and return matching regions

## Upload and analyze flow

1. Select one or more Python files in the frontend.
2. Click Upload.
3. The backend creates a new `AnalysisSession` and stores the uploaded submissions with that `session_id`.
4. The frontend sends the current `session_id` and threshold to `/api/analyze`.
5. The backend filters submissions by that session and compares only the current set.
6. The frontend renders the real results returned by the API.

If fewer than two valid submissions are available, the API returns:

```text
At least two submissions are required for comparison.
```

## Threshold

The similarity threshold is a float between `0` and `1`.

- `0.60` is displayed as `60%`
- `score >= threshold` is considered suspicious
- `score < threshold` is displayed as `LOW SIMILARITY`

Examples:

- `0.60` means 60% or above is `SUSPICIOUS`
- `0.59` is below threshold and is not auto-flagged

## Algorithm

The plagiarism engine preserves the existing Python implementation:

- Python tokenization via the standard library token stream
- normalization of identifiers, numbers, and strings
- k-gram generation with `K = 5`
- hashing of k-grams
- MOSS-style winnowing with window size `W = 12`
- fingerprint creation and pairwise similarity scoring

This is not an AST-based checker and it does not claim exact fingerprint visualization beyond normalized line/region matching.

## Database

The project stores data in SQLite with session-based records:

- `analysis_sessions`
- `submissions`
- `analysis_results`

Every submission and result is associated with its corresponding `AnalysisSession`, and historical sessions remain in the database without influencing new analyses.

## Testing

Run the backend tests with:

```bash
cd "c:\Users\Rachit kumar\Downloads\code plagrism"
python -m unittest discover -s tests -p "test_*.py" -q
```

The test suite covers session isolation, unique pair generation, duplicate rejection, invalid threshold detection, and review status handling.

## Limitations

- The system supports Python source files only.
- It is intended for lightweight educational or assignment screening.
- It is not a production-scale code plagiarism system with benchmarking or multi-language parsing.
- Matching visualization is line/region based after normalization rather than AST-level comparison.

