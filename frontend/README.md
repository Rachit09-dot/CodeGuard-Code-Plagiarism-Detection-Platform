# Frontend README

This frontend is a React + Vite client for the Python-only CodeGuard plagiarism detector.

## Responsibilities

- upload `.py` submission files
- create an analysis session with the backend
- send `session_id`, `submission_ids`, and threshold to `/api/analyze`
- render the returned summary and comparison rows
- allow manual inspection of a file pair comparison view

## Main backend flows

The frontend interacts with these FastAPI endpoints:

- `POST /api/upload`
- `POST /api/analyze`
- `POST /api/compare`

The app uses session-based analysis and never mixes submissions from prior sessions.

## Supported files

Only Python source files are accepted:

- `.py`

Other file types such as `.txt`, `.java`, `.cpp`, and `.exe` are rejected by the backend.

## Threshold behavior

The threshold is stored and sent as a decimal value in the range `0.0` to `1.0`.

Example:

- `0.60` = `60%`
- similarity `>= 0.60` → `SUSPICIOUS`
- similarity `< 0.60` → `LOW SIMILARITY`

## UI behavior

- upload button is enabled only when Python files are selected
- analyze button is enabled only when at least two valid submissions are available
- the frontend displays backend-provided summary values and comparison results
- no hardcoded or fake statistics are used

## Notes

This project uses SQLite on the backend and does not implement Java or C++ parsing.
