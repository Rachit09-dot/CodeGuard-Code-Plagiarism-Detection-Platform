# Project Report — CodeGuard Code Plagiarism Detection Platform

**Version:** 2.1.0 · **Stack:** Python 3.11, FastAPI, React 18 + Vite, SQLAlchemy, SQLite / PostgreSQL, Alembic

---

## 1. Project Overview

CodeGuard detects code similarity and plagiarism in Python submissions. Users upload `.py` files; the backend tokenises, fingerprints, and compares every pair, returning Jaccard, containment, AST, and combined similarity scores alongside highlighted diff views.

---

## 2. Architecture

```
React 18 + Vite ──HTTP/JSON──► FastAPI ──► Service Layer ──► Core Engine ──► SQLAlchemy ──► SQLite / PostgreSQL
```

### Frontend (`frontend/src/`)
- React 18, Vite bundler
- API calls centralised in `src/api/` (client.js, sessions.js, submissions.js, analysis.js)
- `VITE_API_URL` env var — no hard-coded URLs
- Accessible: `aria-label`, `role`, `aria-live`, `htmlFor`/`id` pairs, visible focus rings

### Backend (`backend/app.py`)
- FastAPI 0.110+, Pydantic v2 request models
- Lifespan context manager for `ThreadPoolExecutor` lifecycle
- `AppHTTPException` subclass + handler → structured `{ detail, error_code }` responses
- Security headers middleware
- CPU-heavy analysis offloaded to thread pool (`asyncio.get_running_loop().run_in_executor`)
- Structured logging with timing breakdown (preprocessing / comparison / persistence)

### Core Engine (`core/`)
| Module | Responsibility |
|---|---|
| `config.py` | All constants from env vars |
| `normalizer.py` | Full-file tokenisation, keyword preservation |
| `fingerprinter.py` | k-gram hashing + Winnowing |
| `similarity.py` | Jaccard + containment, `clamp()` |
| `ast_similarity.py` | AST node-type fingerprinting |
| `analysis_service.py` | Per-submission caching, combined score, config snapshot |

### Database (`backend/models.py`)
- `AnalysisSession` — threshold, stats
- `Submission` — source content, `content_hash` (SHA-256, NOT NULL), `analysis_status`
- `AnalysisResult` — all 4 metric scores, `suspicious` (Boolean), `is_exact_duplicate`, `analysis_config` JSON snapshot, `UniqueConstraint` on normalised pair `(min_id, max_id)`

---

## 3. Algorithm

### Tokenisation
Full-file single-pass tokenisation using Python's `tokenize` module. Keywords preserved verbatim — `for` and `if` produce distinct token streams, preventing false positives.

### Fingerprinting
k-gram hashing (default k=5) + Winnowing (window=12). Returns empty set for insufficient content — never produces spurious 1.0 similarity from two empty fingerprints.

### Metrics
- **Jaccard**: `|A∩B| / |A∪B|` — returns 0.0 for empty sets
- **Containment**: `|A∩B| / min(|A|,|B|)` — detects when small file is inside larger one
- **AST**: depth-first node-type sequence, same Winnowing pipeline — ignores variable names and literals
- **Combined**: `clamp(0.6×jaccard + 0.4×ast)` — clamped to [0,1]

### Config Snapshot
Every `AnalysisResult` stores the exact `{ threshold, k_gram_size, window_size, token_weight, ast_weight }` used. Old results remain explainable if config changes later.

---

## 4. Security

| Control | Implementation |
|---|---|
| Session isolation | Every lookup validates `session_id`; foreign IDs → 404 |
| Path traversal | `/`, `\`, `..` in filenames rejected before any FS operation |
| Extension validation | Only `.py` accepted |
| Size limit | `MAX_FILE_SIZE_BYTES` (10 MB default); HTTP 413 |
| Max files | `MAX_FILES_PER_SESSION` (30 default) |
| No execution | Source analysed as text only |
| Security headers | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` |
| CORS | Origins from `ALLOWED_ORIGINS` env var |

---

## 5. Performance

- **Fingerprint caching** — each submission tokenised+fingerprinted once; O(N×L) preprocessing
- **Pairwise complexity** — O(N²) comparisons, each O(F) where F = fingerprint size
- **Thread pool** — CPU analysis runs in `ThreadPoolExecutor`; async event loop handles I/O concurrently
- **Timing logged** — `preprocessing_s`, `comparison_s`, `persistence_s` per analysis run
- **Atomic persistence** — single `db.commit()` for all pair results

---

## 6. Database Migrations

Managed by **Alembic 1.13+**. Schema version-controlled; never relies on `create_all` alone in production.

```bash
alembic upgrade head          # apply migrations
alembic revision --autogenerate -m "description"  # generate from model diff
```

---

## 7. Testing

**Total: 152 tests — 152 passed, 0 failed, 0 skipped**

| Suite | Count | Coverage |
|---|---|---|
| `test_normalizer.py` | 28 | keyword preservation, multiline, error handling |
| `test_fingerprinter.py` | 8 | empty sets, determinism, renamed vars |
| `test_similarity.py` | 18 | Jaccard edge cases, containment, end-to-end |
| `test_ast_similarity.py` | 28 | all 6 requirements + error safety |
| `test_adversarial.py` | 17 | 7 false-positive + 9 false-negative + bounds |
| `test_api_integration.py` | 38 | upload, analyze, compare, isolation, multiline |
| `test_api_threshold_and_review.py` | 15 | threshold, session, pair counts |

Isolation: every test uses `tmp_path` SQLite + temp storage. `plagiarism.db` never touched.

---

## 8. Implemented Features (Not Future Scope)

- ✅ FastAPI REST API
- ✅ React + Vite frontend
- ✅ PostgreSQL / SQLite via SQLAlchemy
- ✅ Alembic migrations
- ✅ Token similarity (Jaccard + containment)
- ✅ AST structural similarity
- ✅ Combined weighted score
- ✅ Exact duplicate detection (SHA-256)
- ✅ Session isolation
- ✅ Security headers
- ✅ Structured error contract (`error_code`)
- ✅ Config snapshot per result
- ✅ CLI with `--json`
- ✅ 152 automated tests
- ✅ Docker Compose (postgres + backend + frontend)

## 9. Honest Limitations

- Python only
- No user authentication (session isolation is the security boundary)
- Docker startup not verified in CI (no daemon available)
- Single-instance only — no distributed queue
