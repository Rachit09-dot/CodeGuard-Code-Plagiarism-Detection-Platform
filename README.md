# Code Plagiarism Detection Platform

A full-stack web application that detects code similarity and potential plagiarism in Python submissions.  Upload files, run analysis, inspect highlighted diff views — all from a browser.

---

## Features

- **Code upload** — batch-upload multiple `.py` files per session
- **Session isolation** — each upload creates an isolated session; no cross-session data leakage
- **Pairwise comparison** — all `N(N-1)/2` pairs compared automatically
- **Token normalisation** — Python keywords preserved (`for`, `if`, `return`, …); user identifiers normalised to `ID`
- **k-gram hashing** — contiguous windows of k normalised tokens → SHA-1 hash
- **Winnowing** — compact representative fingerprint via sliding-window minimum selection
- **Jaccard similarity** — `|A ∩ B| / |A ∪ B|` on fingerprint sets
- **Containment similarity** — `|A ∩ B| / min(|A|, |B|)` — detects when a small file is entirely inside a larger one
- **AST structural similarity** — depth-first node-type walk, fingerprinted with the same winnowing pipeline
- **Combined score** — configurable weighted average: `TOKEN_WEIGHT * jaccard + AST_WEIGHT * ast`
- **Exact duplicate detection** — SHA-256 content hash; flagged independently of fingerprint similarity
- **Insufficient-content detection** — submissions too short to fingerprint return `status=insufficient_content`, never falsely flagged
- **Invalid-Python isolation** — one file with syntax errors does not crash analysis of valid files
- **Session-scoped highlighting** — matching k-gram positions mapped back to source lines; only non-blank lines highlighted
- **CLI tool** — folder analysis with table or `--json` output
- **Automated tests** — 118 tests covering algorithm unit tests, API integration, security, and multiline regressions

---

## Architecture

```
React + Vite  (frontend)
      │
      │  HTTP / JSON
      ▼
FastAPI  (backend/app.py)
      │
      │  Python calls
      ▼
Service Layer  (backend/services/plagiarism_engine.py)
      │
      │  core package
      ▼
Analysis Engine  (core/)
  ├─ normalizer.py      token normalisation
  ├─ fingerprinter.py   k-gram hashing + winnowing
  ├─ similarity.py      Jaccard + containment metrics
  ├─ ast_similarity.py  AST structural similarity
  ├─ analysis_service.py  caching, per-file error handling, combined score
  └─ config.py          centralised constants / env-var overrides
      │
      │  SQLAlchemy ORM
      ▼
SQLite (dev) / PostgreSQL (Docker / production)
```

---

## Algorithm

### 1. Tokenisation

The complete source file is tokenised in one pass using Python's `tokenize` module.  Physical lines are **never** processed individually, so multiline constructs (`foo(\n    1,\n    2\n)`) are handled correctly.

Token normalisation rules:

| Token type | Output |
|---|---|
| Python keyword (`for`, `if`, `return`, …) | kept verbatim |
| Soft keyword (`match`, `case`, …) | kept verbatim |
| User identifier | `ID` |
| Integer / float literal | `NUM` |
| String literal | `STR` |
| Operator / punctuation | kept verbatim |
| Comment, whitespace, indent | discarded |

Preserving keywords means `for x in y` and `if x in y` produce distinct token streams and cannot be incorrectly scored as identical.

### 2. Fingerprinting (Winnowing)

1. Build all k-grams (k consecutive tokens, default k=5).
2. Hash each k-gram: `SHA-1("|".join(gram))[:8]` → `uint64`.
3. Slide a window of size `W` (default 12) over the hash sequence; select the minimum hash in each position.
4. The union of selected hashes is the fingerprint — a compact set of integers.

An empty fingerprint (fewer than k tokens) means `status=insufficient_content`; the submission is never compared.

### 3. Similarity Metrics

```
jaccard     = |A ∩ B| / |A ∪ B|
containment = |A ∩ B| / min(|A|, |B|)
```

Two empty fingerprints → `jaccard = 0.0` (not 1.0).

### 4. AST Similarity

Python's built-in `ast.walk` produces a depth-first sequence of node type names (`FunctionDef`, `For`, `If`, …).  This sequence is fingerprinted with the same k-gram / winnowing pipeline.  Variable names and literal values are ignored — only structural shape matters.

### 5. Combined Score

```
combined = TOKEN_WEIGHT × jaccard + AST_WEIGHT × ast_similarity
```

Default weights: `TOKEN_WEIGHT=0.6`, `AST_WEIGHT=0.4`.  Both weights are configurable via environment variables.  A pair is flagged suspicious when `combined ≥ threshold` **or** `containment ≥ threshold`.

### 6. Exact Duplicate Detection

SHA-256 of the raw source bytes is computed on upload.  Two submissions with identical hashes are flagged as `is_exact_duplicate=true` regardless of threshold.

### Complexity

- Fingerprint generation: `O(N × L)` where `N` = number of submissions, `L` = average token count.  Each file is fingerprinted **once** and cached for the session.
- Pairwise comparison: `O(N²)` pairs, each comparison `O(F)` where `F` = fingerprint set size.

---

## Security

- **Session isolation** — every resource lookup (`/api/submissions`, `/api/compare`) requires a `session_id` and validates that the requested submission belongs to that session.  Cross-session access returns 404.
- **Path traversal protection** — filenames containing `/`, `\`, or `..` are rejected before any filesystem operation.
- **Extension validation** — only `.py` files accepted.
- **Upload size limit** — configurable `MAX_FILE_SIZE_BYTES` (default 10 MB); oversized uploads return HTTP 413.
- **No code execution** — uploaded source is analysed as text; it is never `exec()`-ed or imported.
- **No credentials in repository** — `.env.example` contains only placeholder values; real `.env` is git-ignored.
- **CORS** — allowed origins driven by `ALLOWED_ORIGINS` environment variable; no hard-coded `localhost` URLs in application code.

---

## Getting Started

### Local development (SQLite, no Docker)

```bash
# 1. Install Python deps
pip install -r requirements.txt

# 2. Start backend (SQLite database created automatically)
uvicorn api:app --reload

# 3. In another terminal, start frontend
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000` (frontend) and `http://localhost:8000/api/health` (backend).

Copy `.env.example` to `.env` for environment-variable overrides.

### Docker Compose (PostgreSQL)

```bash
docker compose up --build
```

Services:

| Service | Port |
|---|---|
| PostgreSQL | 5432 |
| FastAPI backend | 8000 |
| React frontend | 5173 |

### CLI

```bash
# Table output
python plagiarism_detector.py submissions/ 0.5

# JSON output (pipe-friendly)
python plagiarism_detector.py submissions/ 0.5 --json
```

---

## Configuration

All tuneable values have sensible defaults and can be overridden with environment variables (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./plagiarism.db` | SQLAlchemy connection string |
| `UPLOAD_DIR` | `./storage` | Directory for uploaded files |
| `ALLOWED_ORIGINS` | `http://localhost:3000,...` | CORS allowed origins |
| `K_GRAM_SIZE` | `5` | k-gram width |
| `WINDOW_SIZE` | `12` | Winnowing window |
| `SIMILARITY_THRESHOLD` | `0.6` | Default suspicious threshold |
| `MIN_TOKENS_FOR_FINGERPRINT` | `5` | Minimum tokens before fingerprinting |
| `TOKEN_WEIGHT` | `0.6` | Token similarity weight in combined score |
| `AST_WEIGHT` | `0.4` | AST similarity weight in combined score |
| `MAX_FILE_SIZE_BYTES` | `10485760` | 10 MB upload limit |

---

## Testing

```bash
python -m pytest tests/ -v
```

Test breakdown:

| File | Count | Coverage |
|---|---|---|
| `test_normalizer.py` | 28 | keyword preservation, identifier normalisation, multiline, errors |
| `test_fingerprinter.py` | 8 | empty inputs, identical/different fingerprints, renamed vars |
| `test_similarity.py` | 18 | Jaccard edge cases, containment, end-to-end real Python |
| `test_ast_similarity.py` | 11 | AST tokens, identical, renamed, invalid Python |
| `test_api_integration.py` | 38 | upload, analyze, compare, security, multiline regression |
| `test_api_threshold_and_review.py` | 15 | threshold, session, pair counts, highlighting |
| **Total** | **118** | |

All tests use an isolated file-based SQLite database and temporary storage directory; the development `plagiarism.db` and `storage/` are never touched.

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/upload` | Upload `.py` files, create session |
| `GET` | `/api/submissions?session_id=N` | List submissions in session |
| `POST` | `/api/analyze` | Run pairwise analysis |
| `GET` | `/api/compare?session_id=N` | Retrieve persisted results |
| `POST` | `/api/compare` | Detailed pair comparison with highlighting |

All endpoints return JSON.  Errors use standard HTTP status codes (400 validation, 404 not found, 413 too large, 422 Pydantic validation, 500 unexpected).

---

## Project Structure

```
.
├── api.py                         # ASGI entry point
├── plagiarism_detector.py         # CLI
├── requirements.txt
├── .env.example
├── Dockerfile.backend
├── docker-compose.yml
│
├── backend/
│   ├── app.py                     # FastAPI routes
│   ├── database.py                # SQLAlchemy engine + session factory
│   ├── models.py                  # ORM models
│   └── services/
│       ├── plagiarism_engine.py   # Bridge: FastAPI ↔ core engine
│       └── storage_service.py     # Safe file storage
│
├── core/
│   ├── config.py                  # Centralised constants
│   ├── normalizer.py              # Token normalisation
│   ├── fingerprinter.py           # k-gram hashing + winnowing
│   ├── similarity.py              # Jaccard + containment
│   ├── ast_similarity.py          # AST structural similarity
│   └── analysis_service.py        # High-level service with caching
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   └── index.css
│   ├── vite.config.js
│   ├── .env.example
│   └── Dockerfile.frontend
│
├── submissions/                   # Sample .py files for testing / CLI demo
└── tests/
    ├── conftest.py                # Isolated DB + storage fixtures
    ├── test_normalizer.py
    ├── test_fingerprinter.py
    ├── test_similarity.py
    ├── test_ast_similarity.py
    ├── test_api_integration.py
    └── test_api_threshold_and_review.py
```
