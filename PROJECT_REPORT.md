# Project Report — Code Plagiarism Detection Platform

**Version:** 2.0.0  
**Stack:** Python 3.11, FastAPI, React 18 + Vite, SQLAlchemy, SQLite / PostgreSQL

---

## 1. Project Overview

This platform detects code similarity and potential plagiarism in Python source submissions.  A user uploads `.py` files through a browser interface; the backend tokenises, fingerprints, and compares every pair, returning similarity scores, highlighting, and a suspicious/not-suspicious verdict.

The same engine is also available as a command-line tool for batch processing.

---

## 2. System Architecture

```
React + Vite  ──HTTP/JSON──►  FastAPI  ──Python──►  core engine  ──ORM──►  SQLite / PostgreSQL
```

### 2.1 Frontend

- React 18 with Vite bundler.
- Single-page application with upload, threshold slider, results table, and side-by-side highlighted diff view.
- API base URL read from `VITE_API_URL` environment variable (no hard-coded `localhost`).
- Displays all four metrics: combined score, Jaccard, containment, and AST similarity.
- Exact duplicates shown with a distinct `EXACT COPY` badge.
- Invalid/insufficient submissions shown with per-file status pills.

### 2.2 Backend

- FastAPI with Pydantic v2 request/response models.
- Every request validated before any database work.
- CPU-heavy analysis runs in a `ThreadPoolExecutor` so the async event loop remains responsive.
- Structured logging at every key step (upload, analysis start/end, duration, pair count).
- CORS origins driven by `ALLOWED_ORIGINS` environment variable.

### 2.3 Service Layer

`backend/services/plagiarism_engine.py` adapts the core engine to the HTTP layer:
- `prepare_submission` — tokenise + fingerprint once; returns a `SubmissionResult` with status, tokens, fingerprint, and SHA-256 hash.
- `compare_pair_detail` — compares two pre-built `SubmissionResult` objects; reuses cached fingerprints.
- `find_matching_regions` — maps matching k-gram positions back to source line numbers for highlighting; uses the same normalised token representation as similarity scoring.

### 2.4 Analysis Engine (`core/`)

See Section 3 (Algorithm) for details.

### 2.5 Database

SQLAlchemy ORM with:
- `AnalysisSession` — created on upload; tracks threshold, submission count, stats.
- `Submission` — stores source text, filename, language, SHA-256 hash, analysis status.
- `AnalysisResult` — stores all four metric scores, `suspicious` (Boolean), `is_exact_duplicate`, and a JSON snapshot of the comparison result.
- `UniqueConstraint` on `(session_id, submission_a_id, submission_b_id)` — pairs are normalised so `a_id < b_id`, making the constraint order-independent (A-B ≡ B-A).  Re-running analysis replaces existing rows (delete + insert) rather than appending duplicates.

---

## 3. Algorithm

### 3.1 Tokenisation

Python's built-in `tokenize` module processes the **complete source file in one pass**.  Per-line tokenisation was removed as it breaks multiline constructs.

Normalisation rules:

- Python keywords → kept verbatim (preserves control-flow semantics)
- User-defined identifiers → `ID` (removes irrelevant naming differences)
- Numeric literals → `NUM`
- String literals → `STR`
- Operators / punctuation → kept verbatim
- Comments, whitespace, indent / dedent → discarded

**Why keywords must be preserved:** if `for` and `if` both collapsed to `ID`, then `for x in y: print(x)` and `if x in y: print(x)` would be indistinguishable.  The fix ensures changed control flow produces a meaningfully lower score.

### 3.2 Fingerprinting — k-Gram Hashing + Winnowing

1. Build all k-grams of width `k` (default 5) from the normalised token stream.
2. Hash each k-gram: `SHA-1("|".join(gram))[:8 bytes]` converted to `uint64`.
3. Winnowing: slide a window of width `W` (default 12) over the hash sequence; for each window position select the minimum hash.
4. The **set** of selected hashes is the fingerprint — compact and robust to local reorderings.

Submissions producing fewer than `k` tokens return an empty fingerprint and status `insufficient_content`.  They are never compared, avoiding the false-positive `1.0` similarity that arises when two empty sets are compared naively.

### 3.3 Jaccard Similarity

```
jaccard(A, B) = |A ∩ B| / |A ∪ B|
```

Returns `0.0` when either set is empty (not `1.0`).

### 3.4 Containment Similarity

```
containment(A, B) = |A ∩ B| / min(|A|, |B|)
```

Detects the case where a small submission is entirely contained inside a larger one — a scenario where Jaccard alone gives a misleadingly moderate score because the larger submission inflates the union.

### 3.5 AST Structural Similarity

Python's built-in `ast` module parses each source into an AST.  A depth-first `ast.walk` produces a sequence of node-type names (`Module`, `FunctionDef`, `For`, `If`, `Return`, …).  This sequence is fingerprinted with the same k-gram / winnowing pipeline, producing an AST fingerprint.  Jaccard similarity on the two AST fingerprints gives a structural score that is insensitive to variable names and literal values.

### 3.6 Combined Score

```
combined = TOKEN_WEIGHT × jaccard + AST_WEIGHT × ast_similarity
```

Default: `TOKEN_WEIGHT=0.6`, `AST_WEIGHT=0.4`.  A pair is marked suspicious when `combined ≥ threshold` **or** `containment ≥ threshold`.  All four component scores are returned in the API response and stored in the database.

### 3.7 Exact Duplicate Detection

SHA-256 of the raw source bytes is computed at upload time.  Identical hashes mean byte-for-byte copy; flagged independently of the threshold.

### 3.8 Fingerprint Caching

Each submission is tokenised and fingerprinted **exactly once** per analysis run; the result is stored in a dict keyed by submission ID.  All `N(N-1)/2` pairwise comparisons reuse these cached representations, giving `O(N × L)` preprocessing and `O(N²)` comparison, where `L` is the average token stream length.

---

## 4. Security

| Control | Implementation |
|---|---|
| Session isolation | Every resource lookup validates `session_id` ownership; cross-session access → 404 |
| Path traversal | Filenames with `/`, `\`, `..` rejected before any filesystem operation |
| Extension validation | Only `.py` accepted |
| Upload size limit | `MAX_FILE_SIZE_BYTES` env var (default 10 MB); HTTP 413 on violation |
| No code execution | Source analysed as text only; never `exec()`-ed |
| No secrets in repo | `.env` is `.gitignore`-d; `.env.example` uses placeholder values |
| CORS | `ALLOWED_ORIGINS` env var; no hard-coded origins in source |
| Input validation | Pydantic models validate all request fields including `0 ≤ threshold ≤ 1` |

---

## 5. Performance

| Metric | Approach |
|---|---|
| Fingerprint reuse | Computed once per submission; cached for all pairs |
| Pairwise complexity | `O(N²)` comparisons, each `O(F)` where `F` = fingerprint size |
| Event loop | CPU-heavy analysis runs in `ThreadPoolExecutor`; async loop handles I/O concurrently |
| Database | `UniqueConstraint` + delete-before-insert prevents unbounded result accumulation |

---

## 6. Testing

```
python -m pytest tests/ -v
```

**Total: 118 tests — 118 passed, 0 failed, 0 skipped**

| Suite | Tests | What it covers |
|---|---|---|
| `test_normalizer.py` | 28 | keyword preservation, identifier normalisation, multiline constructs, error handling |
| `test_fingerprinter.py` | 8 | empty inputs, determinism, identical/different streams, renamed identifiers |
| `test_similarity.py` | 18 | Jaccard edge cases (empty sets), containment, end-to-end on real Python |
| `test_ast_similarity.py` | 11 | node extraction, identical/renamed source, invalid Python, formatting changes |
| `test_api_integration.py` | 38 | upload, analyze, compare, session isolation, security, multiline regression, exact duplicate |
| `test_api_threshold_and_review.py` | 15 | threshold logic, session creation, pair counts, error messages |

All tests run against an isolated file-based SQLite database in a `tmp_path` directory.  The development `plagiarism.db` and `storage/` are never touched.

---

## 7. Bugs Fixed

| Bug | Fix |
|---|---|
| Keywords collapsed to `ID` → false positives | `keyword.iskeyword()` check; keywords kept verbatim |
| `jaccard({}, {}) == 1.0` → empty files flagged | Returns `0.0` when either set is empty |
| Per-line tokenisation → multiline crashes / wrong highlights | Full-file tokenisation in one pass |
| Highlighting inconsistent with score | Both derived from same k-gram hashes; positions mapped back to lines |
| One bad submission crashes whole analysis | `prepare_submission` catches `TokenizeError`; status set per file |
| Re-analysis creates duplicate DB rows | Normalised pair order + delete-before-insert |
| `suspicious` stored as String `"true"/"false"` | Changed to SQLAlchemy `Boolean` |
| `datetime.utcnow()` deprecated | Replaced with `datetime.now(tz=timezone.utc)` |
| Hard-coded `localhost` API URL in frontend | `VITE_API_URL` env var |
| Root `package.json` served raw JSX via `http.server` | Removed; frontend uses Vite |
| No Containment metric | `containment_similarity()` added to `core/similarity.py` |
| No AST similarity | `core/ast_similarity.py` using `ast.walk` + same winnowing pipeline |
| No fingerprint caching | Per-submission `SubmissionResult` built once, reused for all pairs |
| No SHA-256 exact duplicate detection | Computed at upload; stored on `Submission` model |
| Magic numbers scattered throughout code | `core/config.py` with env-var overrides |
| Docker only had PostgreSQL, no backend/frontend | Added `backend` + `frontend` services with healthcheck |
| Tests used real `plagiarism.db` | `conftest.py` isolates each test with `tmp_path` SQLite + temp storage |
| Dead code (`_find_session_for_payload`, `analyze_submission_files`) | Removed |
| CORS origins hard-coded | Driven by `ALLOWED_ORIGINS` env var |
| Legacy migration code ran on every startup | Removed; replaced with clean `Base.metadata.create_all` |

---

## 8. Files Changed

**Core engine**
- `core/config.py` — new; centralised constants
- `core/normalizer.py` — keyword preservation, full-file tokenisation, `TokenizeError` propagation
- `core/fingerprinter.py` — uses config constants; empty-set for insufficient content
- `core/similarity.py` — `jaccard` returns 0 for empty; `containment_similarity` added
- `core/ast_similarity.py` — new; AST structural similarity
- `core/analysis_service.py` — full rewrite with caching, per-file errors, all metrics
- `core/__init__.py` — updated exports

**Backend**
- `backend/app.py` — Pydantic models, session isolation, upsert, threadpool, logging, `_get_session()` indirection
- `backend/models.py` — `Boolean` suspicious, tz-aware datetimes, `UniqueConstraint`, new metric columns
- `backend/services/plagiarism_engine.py` — full rewrite; full-file tokenisation in highlighting

**Frontend**
- `frontend/src/App.jsx` — `VITE_API_URL`, metric pills, exact-duplicate badge, loading states
- `frontend/src/index.css` — new classes for metric pills, status badges
- `frontend/.env.example` — new

**Infrastructure**
- `docker-compose.yml` — added `backend` + `frontend` services, healthcheck
- `Dockerfile.backend` — new
- `frontend/Dockerfile.frontend` — new
- `.env.example` — all config vars documented
- `package.json` — removed invalid `http.server` scripts

**CLI**
- `plagiarism_detector.py` — `--json` flag, uses `DEFAULT_THRESHOLD` from config

**Tests**
- `tests/conftest.py` — isolated `tmp_path` SQLite + storage per test
- `tests/test_normalizer.py` — 28 tests (new)
- `tests/test_fingerprinter.py` — 8 tests (new)
- `tests/test_similarity.py` — 18 tests (new)
- `tests/test_ast_similarity.py` — 11 tests (new)
- `tests/test_api_integration.py` — 38 tests (new)
- `tests/test_api_threshold_and_review.py` — 15 tests (refactored to use fixtures)

**Documentation**
- `README.md` — rewritten; matches actual implementation
- `PROJECT_REPORT.md` — this document

---

## 9. Remaining Limitations

- **PostgreSQL in production** — the Docker Compose configuration works but has not been tested end-to-end in this environment (no Docker daemon available in the build environment).  The SQLAlchemy layer is identical; only the connection string changes.
- **Language support** — only Python is supported.  The normaliser is tightly coupled to Python's `tokenize` module.
- **Scale** — the `ThreadPoolExecutor` approach is suitable for single-instance deployments.  Horizontal scaling would require an external task queue, but adding one was intentionally out of scope.
- **Authentication** — the platform relies on session isolation rather than user accounts.  This is appropriate for controlled classroom use; a public deployment would need proper user authentication.
