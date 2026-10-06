# CodeGuard — Code Plagiarism Detection Platform

A full-stack web application for detecting code similarity and plagiarism in Python submissions.

---

## Features

- Batch upload of `.py` files per isolated session
- Pairwise similarity analysis for all N(N-1)/2 pairs
- **Token normalisation** — Python keywords preserved (`for` ≠ `if`); identifiers → `ID`
- **k-gram hashing + Winnowing** fingerprints
- **Jaccard similarity** and **Containment similarity**
- **AST structural similarity** via Python's built-in `ast` module
- **Combined score** = `TOKEN_WEIGHT × jaccard + AST_WEIGHT × ast`
- **SHA-256 exact duplicate detection**
- **Insufficient-content detection** — tiny files never falsely flagged
- **Per-file error isolation** — invalid Python in one file never crashes analysis
- Session-scoped security — cross-session access always returns 404
- Structured API errors with `error_code` field
- Analysis config snapshot stored with every result
- `/api/ready` readiness probe with live DB check
- Security headers: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`
- CLI tool with `--json` output
- **Alembic** database migrations
- **152 automated tests**

---

## Architecture

```
React + Vite  (frontend/src/api/ client layer)
      │  HTTP/JSON
FastAPI  (backend/app.py)
      │  Python
Service Layer  (backend/services/plagiarism_engine.py)
      │
Analysis Engine  (core/)
  ├─ config.py          centralised constants / env-var overrides
  ├─ normalizer.py      full-file tokenisation, keyword preservation
  ├─ fingerprinter.py   k-gram hashing + Winnowing
  ├─ similarity.py      Jaccard + containment, clamped [0,1]
  ├─ ast_similarity.py  AST node-type fingerprinting
  └─ analysis_service.py  per-submission caching, combined score
      │  SQLAlchemy ORM
SQLite (dev) / PostgreSQL (Docker/prod)
```

---

## Algorithm

### 1. Tokenisation
Complete source tokenised in **one pass** — never per-line. Python keywords (`for`, `if`, `return`, …) are preserved verbatim. User identifiers → `ID`, numbers → `NUM`, strings → `STR`.

### 2. k-gram Fingerprinting (Winnowing)
1. Build k-grams of width `k` (default 5).  
2. Hash each: `SHA-1("|".join(gram))[:8 bytes]` → uint64.  
3. Slide window of width `W` (default 12), select minimum per window → fingerprint set.

### 3. Similarity Metrics
| Metric | Formula | Notes |
|---|---|---|
| Jaccard | `\|A∩B\| / \|A∪B\|` | Returns 0.0 for empty sets |
| Containment | `\|A∩B\| / min(\|A\|,\|B\|)` | Detects subset plagiarism |
| AST | Jaccard on AST node-type k-grams | Structural, ignores names |
| Combined | `0.6×jaccard + 0.4×ast` | Clamped to [0,1] |

Pair flagged suspicious when `combined ≥ threshold` OR `containment ≥ threshold`.

### 4. Fingerprint Caching
Each submission fingerprinted **once** per analysis session. All N(N-1)/2 pairs reuse the cached result → O(N²) comparisons, O(N×L) preprocessing.

---

## Quick Start

### Local (SQLite, no Docker)
```bash
pip install -r requirements.txt
uvicorn api:app --reload          # backend on :8000
cd frontend && npm install && npm run dev   # frontend on :3000
```

### Docker Compose (PostgreSQL)
```bash
docker compose up --build
# Frontend → http://localhost:5173
# Backend  → http://localhost:8000
```

### CLI
```bash
python plagiarism_detector.py submissions/ 0.5
python plagiarism_detector.py submissions/ 0.5 --json
```

---

## Database Migrations (Alembic)

```bash
# Apply all migrations to current DB
alembic upgrade head

# Generate a new migration after model changes
alembic revision --autogenerate -m "description"

# Check current revision
alembic current
```

Set `DATABASE_URL` env var before running migrations. Default: `sqlite:///./plagiarism.db`.

---

## Configuration

All values overridable via environment variables (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./plagiarism.db` | SQLAlchemy connection string |
| `UPLOAD_DIR` | `./storage` | Upload directory |
| `ALLOWED_ORIGINS` | `http://localhost:3000,...` | CORS allowed origins |
| `K_GRAM_SIZE` | `5` | k-gram width |
| `WINDOW_SIZE` | `12` | Winnowing window |
| `SIMILARITY_THRESHOLD` | `0.6` | Default suspicious threshold |
| `TOKEN_WEIGHT` | `0.6` | Token score weight in combined |
| `AST_WEIGHT` | `0.4` | AST score weight in combined |
| `MAX_FILE_SIZE_BYTES` | `10485760` | 10 MB per file |
| `MAX_FILES_PER_SESSION` | `30` | Max files per upload |
| `HIGHLIGHT_MATCH_CAP` | `50` | Max highlighted line pairs |

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/health` | Liveness check |
| GET | `/api/ready` | Readiness — probes DB |
| POST | `/api/upload` | Upload `.py` files, create session |
| GET | `/api/submissions?session_id=N` | List submissions (session-scoped) |
| POST | `/api/analyze` | Run pairwise analysis |
| GET | `/api/compare?session_id=N` | Retrieve persisted results |
| POST | `/api/compare` | Detailed pair comparison + highlighting |

All errors return `{ "detail": "...", "error_code": "INVALID_SESSION" }`.

Error codes: `INVALID_SESSION` · `SUBMISSION_NOT_FOUND` · `INVALID_SOURCE` · `UNSUPPORTED_FILE` · `FILE_TOO_LARGE` · `DUPLICATE_SUBMISSION` · `CROSS_SESSION_ACCESS` · `ANALYSIS_FAILED`

---

## Testing

```bash
python -m pytest tests/ -v
```

**Total: 152 tests — 152 passed, 0 failed, 0 skipped**

| Suite | Tests |
|---|---|
| `test_normalizer.py` | 28 |
| `test_fingerprinter.py` | 8 |
| `test_similarity.py` | 18 |
| `test_ast_similarity.py` | 28 |
| `test_adversarial.py` | 17 (false-positive + false-negative) |
| `test_api_integration.py` | 38 |
| `test_api_threshold_and_review.py` | 15 |

All tests use isolated file-based SQLite + `tmp_path` storage. Never touches `plagiarism.db`.

---

## Security

- **Session isolation** — every lookup validates session ownership; cross-session → 404
- **Path traversal** — filenames with `/`, `\`, `..` rejected before any FS operation
- **Extension validation** — only `.py` accepted
- **Size limits** — `MAX_FILE_SIZE_BYTES` enforced; HTTP 413 on violation
- **No code execution** — source analysed as text only
- **Security headers** — `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`
- **CORS** — origins from `ALLOWED_ORIGINS` env var

---

## Limitations

- Python only (tokeniser is language-specific)
- Single-instance deployment (no distributed task queue)
- No user authentication (session isolation is the security boundary)
- Docker not verified in CI (no Docker daemon in build environment)
