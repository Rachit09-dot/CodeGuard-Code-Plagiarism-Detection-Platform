"""FastAPI application — Code Plagiarism Detection Platform (v2.1).

Second-round hardening:
- Proper asyncio import (no __import__ hack); uses asyncio.get_running_loop()
- Lifespan context manager for ThreadPoolExecutor cleanup
- Security headers middleware (X-Content-Type-Options, X-Frame-Options, Referrer-Policy)
- Structured error contract: every HTTPException carries an error_code field
- /api/ready endpoint with live database connectivity probe
- MAX_FILES_PER_SESSION resource limit
- Detailed performance timing: preprocessing / comparison / persistence logged separately
- Atomic transaction for analysis persistence (single commit)
- Config snapshot stored with every analysis result (k, window, weights, threshold)
- CORS origins from ALLOWED_ORIGINS env var
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
import backend.database as _db_module
from backend.database import Base, engine
from backend.models import AnalysisResult, AnalysisSession, Submission
from backend.services.plagiarism_engine import (
    compare_code_pair,
    compare_pair_detail,
    find_matching_regions,
    prepare_submission,
)
from backend.services.storage_service import save_uploaded_file
from core.config import (
    ALLOWED_EXTENSIONS,
    DEFAULT_THRESHOLD,
    MAX_FILE_SIZE_BYTES,
    MAX_FILES_PER_SESSION,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thread pool (managed via lifespan so it is properly shut down)
# ---------------------------------------------------------------------------

_executor: ThreadPoolExecutor | None = None


# ---------------------------------------------------------------------------
# Structured exception class — defined before app so it can be used in handler
# ---------------------------------------------------------------------------

class AppHTTPException(HTTPException):
    """HTTPException subclass that carries an error_code for the API contract."""

    def __init__(self, status_code: int, detail: str, error_code: str) -> None:
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code


def _http_error(status: int, detail: str, error_code: str) -> "AppHTTPException":
    """Return a structured HTTP exception with an error_code field."""
    return AppHTTPException(status_code=status, detail=detail, error_code=error_code)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    global _executor
    logger.info("Starting up — creating database schema …")
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema ready.")
    _executor = ThreadPoolExecutor(max_workers=os.cpu_count() or 2)
    yield
    logger.info("Shutting down — releasing thread pool …")
    if _executor:
        _executor.shutdown(wait=True)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Code Plagiarism Platform", version="2.1.0", lifespan=lifespan)


@app.exception_handler(AppHTTPException)
async def app_http_exception_handler(request: Request, exc: AppHTTPException) -> JSONResponse:  # noqa: ARG001
    """Serialize AppHTTPException with both ``detail`` (string) and ``error_code``."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "error_code": exc.error_code},
    )


_raw_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://127.0.0.1:3000,http://localhost:3000,http://localhost:3002,http://localhost:5173",
)
_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Security headers middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# ---------------------------------------------------------------------------
# Session factory helper (allows test fixture to swap the underlying engine)
# ---------------------------------------------------------------------------

def _get_session():
    return _db_module.SessionLocal()


# ---------------------------------------------------------------------------
# Structured error helper
# ---------------------------------------------------------------------------

def _get_session():
    return _db_module.SessionLocal()



# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    session_id: int
    submission_ids: list[int] = Field(default_factory=list)
    threshold: float = Field(default=DEFAULT_THRESHOLD, ge=0.0, le=1.0)

    @field_validator("submission_ids")
    @classmethod
    def _deduplicate_ids(cls, v: list[int]) -> list[int]:
        seen: list[int] = []
        for item in v:
            if item not in seen:
                seen.append(item)
        return seen


class ComparePairRequest(BaseModel):
    session_id: int
    left_id: int
    right_id: int
    threshold: float = Field(default=DEFAULT_THRESHOLD, ge=0.0, le=1.0)

    @field_validator("right_id")
    @classmethod
    def _no_self_compare(cls, v: int, info: Any) -> int:
        if "left_id" in (info.data or {}) and v == info.data["left_id"]:
            raise ValueError("A submission cannot be compared with itself.")
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_submission_name(filename: str) -> str:
    clean = (filename or "submission.py").strip()
    if not clean or clean in {".", ".."}:
        raise _http_error(400, "Invalid file name.", "UNSUPPORTED_FILE")
    if "/" in clean or "\\" in clean:
        raise _http_error(400, "Only Python (.py) files are allowed.", "UNSUPPORTED_FILE")
    basename = Path(clean).name
    if basename != clean:
        raise _http_error(400, "Only Python (.py) files are allowed.", "UNSUPPORTED_FILE")
    suffix = Path(clean).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise _http_error(
            400,
            f"Unsupported file type for '{clean}'. Only Python (.py) files are allowed.",
            "UNSUPPORTED_FILE",
        )
    return clean


def _build_pair_explanation(score: float, threshold: float) -> str:
    pct = score * 100
    thr = threshold * 100
    if score >= threshold:
        return (
            f"Similarity is {pct:.1f}%, at or above the threshold of {thr:.1f}%. "
            "Manual review is recommended."
        )
    return (
        f"Similarity is {pct:.1f}%, below the threshold of {thr:.1f}%. "
        "This pair is classified as low similarity."
    )


def _get_session_or_404(db: Any, session_id: int) -> AnalysisSession:
    session = db.query(AnalysisSession).filter(AnalysisSession.id == session_id).first()
    if session is None:
        raise _http_error(404, f"Analysis session {session_id} not found.", "INVALID_SESSION")
    return session


def _get_submission_in_session(db: Any, submission_id: int, session_id: int) -> Submission:
    sub = db.query(Submission).filter(
        Submission.id == submission_id,
        Submission.session_id == session_id,
    ).first()
    if sub is None:
        raise _http_error(
            404,
            f"Submission {submission_id} not found in session {session_id}.",
            "CROSS_SESSION_ACCESS",
        )
    return sub


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "code-plagiarism-platform"}


@app.get("/api/ready")
async def readiness() -> dict[str, Any]:
    """Deep readiness check — verifies database connectivity."""
    db = _get_session()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "ok"}
    except Exception as exc:
        logger.error("Readiness check failed: %s", exc)
        raise _http_error(503, "Database is not reachable.", "DATABASE_ERROR")
    finally:
        db.close()


@app.post("/api/upload")
async def upload_files(files: list[UploadFile] = File(...)) -> dict[str, Any]:
    if not files:
        raise _http_error(400, "No Python files were uploaded.", "UNSUPPORTED_FILE")

    if len(files) > MAX_FILES_PER_SESSION:
        raise _http_error(
            400,
            f"Too many files. Maximum {MAX_FILES_PER_SESSION} files per session.",
            "FILE_TOO_LARGE",
        )

    validated: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for upload in files:
        filename = _validate_submission_name(upload.filename or "submission.py")
        if filename in seen_names:
            raise _http_error(400, f"Duplicate filename found: {filename}", "DUPLICATE_SUBMISSION")
        seen_names.add(filename)

        upload.file.seek(0)
        raw = upload.file.read()
        upload.file.seek(0)

        if not raw or not raw.strip():
            raise _http_error(400, f"File is empty: {filename}.", "UNSUPPORTED_FILE")
        if len(raw) > MAX_FILE_SIZE_BYTES:
            raise _http_error(
                413,
                f"File too large: {filename}. Maximum size is {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB.",
                "FILE_TOO_LARGE",
            )
        try:
            text_content = raw.decode("utf-8")
        except UnicodeDecodeError:
            text_content = raw.decode("utf-8", errors="replace")

        validated.append({"filename": filename, "content": text_content})

    db = _get_session()
    created_paths: list[str] = []
    session: AnalysisSession | None = None
    saved: list[dict[str, Any]] = []

    try:
        session = AnalysisSession(
            threshold=DEFAULT_THRESHOLD,
            total_submissions=0,
            total_comparisons=0,
            suspicious_pairs=0,
            average_similarity=0.0,
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        for item in validated:
            sub_repr = prepare_submission(item["filename"], item["content"])
            safe_path, display_name = save_uploaded_file(
                item["filename"],
                item["content"].encode("utf-8"),
                directory=f"session_{session.id}",
            )
            created_paths.append(safe_path)

            submission = Submission(
                session_id=session.id,
                filename=display_name,
                content=item["content"],
                content_hash=sub_repr.content_hash,
                language="python",
                analysis_status=sub_repr.status,
            )
            db.add(submission)
            db.commit()
            db.refresh(submission)

            saved.append({
                "id": submission.id,
                "session_id": submission.session_id,
                "filename": submission.filename,
                "language": submission.language,
                "status": submission.analysis_status,
                "content_hash": submission.content_hash,
            })

        session.total_submissions = len(saved)
        db.add(session)
        db.commit()

        logger.info("submission_uploaded: session=%d, files=%d", session.id, len(saved))
        return {
            "success": True,
            "session_id": session.id,
            "total_submissions": len(saved),
            "submissions": saved,
        }

    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.error("Upload failed: %s", exc, exc_info=True)
        for path_text in created_paths:
            try:
                Path(path_text).unlink(missing_ok=True)
            except OSError:
                pass
        if session is not None:
            try:
                db.query(Submission).filter(Submission.session_id == session.id).delete()
                db.query(AnalysisSession).filter(AnalysisSession.id == session.id).delete()
                db.commit()
            except Exception:
                pass
        raise _http_error(500, "Upload failed due to a server error.", "ANALYSIS_FAILED")
    finally:
        db.close()


@app.get("/api/submissions")
async def list_submissions(session_id: int) -> dict[str, Any]:
    db = _get_session()
    try:
        session = _get_session_or_404(db, session_id)
        submissions = (
            db.query(Submission)
            .filter(Submission.session_id == session.id)
            .order_by(Submission.id.asc())
            .all()
        )
        return {
            "total_submissions": len(submissions),
            "session_id": session_id,
            "submissions": [
                {
                    "id": item.id,
                    "session_id": item.session_id,
                    "filename": item.filename,
                    "language": item.language,
                    "analysis_status": item.analysis_status,
                    "content_hash": item.content_hash,
                }
                for item in submissions
            ],
        }
    finally:
        db.close()


@app.post("/api/analyze")
async def analyze_submission(request: AnalyzeRequest) -> dict[str, Any]:
    """Run pairwise analysis — fingerprints built once, reused across all pairs."""
    db = _get_session()
    try:
        session = _get_session_or_404(db, request.session_id)
        threshold = request.threshold

        allowed_ids = {
            row[0]
            for row in db.query(Submission.id)
            .filter(
                Submission.session_id == session.id,
                Submission.id.in_(request.submission_ids),
            )
            .all()
        }

        if not request.submission_ids:
            allowed_ids = {
                row[0]
                for row in db.query(Submission.id)
                .filter(Submission.session_id == session.id)
                .all()
            }

        filtered_ids = sorted(allowed_ids)

        if not filtered_ids:
            raise _http_error(404, "No submissions found for this session.", "SUBMISSION_NOT_FOUND")
        if len(filtered_ids) < 2:
            raise _http_error(
                400,
                "At least two submissions are required for comparison.",
                "SUBMISSION_NOT_FOUND",
            )

        submissions = (
            db.query(Submission)
            .filter(Submission.id.in_(filtered_ids), Submission.session_id == session.id)
            .order_by(Submission.id.asc())
            .all()
        )

        if len(submissions) < 2:
            raise _http_error(
                400,
                "At least two submissions are required for comparison.",
                "SUBMISSION_NOT_FOUND",
            )

        sub_data = [
            {"id": s.id, "filename": s.filename, "content": s.content}
            for s in submissions
        ]
    finally:
        db.close()

    # ------------------------------------------------------------------
    # CPU-heavy analysis in thread pool — does not block async event loop
    # ------------------------------------------------------------------

    def _run_analysis() -> tuple[list[dict[str, Any]], dict[str, float]]:
        logger.info(
            "analysis_started: session=%d, submissions=%d",
            request.session_id, len(sub_data),
        )
        t_total = time.perf_counter()

        # Preprocessing: tokenise + fingerprint each submission exactly once
        t_pre = time.perf_counter()
        cache: dict[int, Any] = {}
        for item in sub_data:
            cache[item["id"]] = prepare_submission(item["filename"], item["content"])
        preprocessing_time = time.perf_counter() - t_pre

        # Comparison: pairwise
        t_cmp = time.perf_counter()
        pairs: list[dict[str, Any]] = []
        for i in range(len(sub_data)):
            for j in range(i + 1, len(sub_data)):
                left_id = sub_data[i]["id"]
                right_id = sub_data[j]["id"]
                result = compare_pair_detail(cache[left_id], cache[right_id], threshold=threshold)
                result["left_id"] = left_id
                result["right_id"] = right_id
                pairs.append(result)
        comparison_time = time.perf_counter() - t_cmp

        total_time = time.perf_counter() - t_total
        timing = {
            "preprocessing_s": round(preprocessing_time, 4),
            "comparison_s": round(comparison_time, 4),
            "total_analysis_s": round(total_time, 4),
        }
        logger.info(
            "analysis_complete: session=%d, pairs=%d, pre=%.3fs, cmp=%.3fs, total=%.3fs",
            request.session_id, len(pairs),
            preprocessing_time, comparison_time, total_time,
        )
        return pairs, timing

    loop = asyncio.get_running_loop()
    compared, timing = await loop.run_in_executor(_executor, _run_analysis)

    compared.sort(key=lambda x: (x["score"], x["file_a"], x["file_b"]), reverse=True)
    suspicious_count = sum(1 for p in compared if p["suspicious"])
    avg_similarity = (
        round(sum(p["score"] for p in compared) / len(compared), 4) if compared else 0.0
    )

    # ------------------------------------------------------------------
    # Persist results — single atomic transaction
    # ------------------------------------------------------------------

    t_persist = time.perf_counter()
    db = _get_session()
    try:
        session = _get_session_or_404(db, request.session_id)

        # Delete all existing results for this session in one query (atomic)
        pair_keys = [
            (min(p["left_id"], p["right_id"]), max(p["left_id"], p["right_id"]))
            for p in compared
        ]
        for a_id, b_id in pair_keys:
            db.query(AnalysisResult).filter(
                AnalysisResult.session_id == session.id,
                AnalysisResult.submission_a_id == a_id,
                AnalysisResult.submission_b_id == b_id,
            ).delete(synchronize_session=False)

        # Insert all new results
        for pair in compared:
            a_id = min(pair["left_id"], pair["right_id"])
            b_id = max(pair["left_id"], pair["right_id"])
            result_row = AnalysisResult(
                session_id=session.id,
                submission_a_id=a_id,
                submission_b_id=b_id,
                score=pair["score"],
                jaccard_similarity=pair.get("jaccard_similarity"),
                containment_similarity=pair.get("containment_similarity"),
                ast_similarity=pair.get("ast_similarity"),
                threshold=threshold,
                suspicious=bool(pair["suspicious"]),
                is_exact_duplicate=bool(pair.get("is_exact_duplicate", False)),
                comparison=json.dumps({
                    k: v for k, v in pair.items() if k not in ("left_id", "right_id")
                }),
            )
            db.add(result_row)

        session.threshold = threshold
        session.total_submissions = len(sub_data)
        session.total_comparisons = len(compared)
        session.suspicious_pairs = suspicious_count
        session.average_similarity = avg_similarity
        db.add(session)
        db.commit()  # single atomic commit

        persistence_time = time.perf_counter() - t_persist
        logger.info(
            "analysis_persisted: session=%d, pairs=%d, persist=%.3fs",
            request.session_id, len(compared), persistence_time,
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.error("analysis_failed: persistence error session=%d: %s", request.session_id, exc, exc_info=True)
        raise _http_error(500, "Analysis failed during persistence.", "ANALYSIS_FAILED")
    finally:
        db.close()

    public_pairs = [
        {k: v for k, v in p.items() if k not in ("left_id", "right_id")}
        for p in compared
    ]

    return {
        "session_id": request.session_id,
        "threshold": threshold,
        "total_submissions": len(sub_data),
        "total_comparisons": len(compared),
        "checked_pairs": len(compared),
        "suspicious_pair_count": suspicious_count,
        "flagged_pairs": suspicious_count,
        "average_similarity": avg_similarity,
        "timing": timing,
        "results": public_pairs,
    }


@app.get("/api/compare")
async def get_comparison_results(session_id: int) -> dict[str, Any]:
    db = _get_session()
    try:
        session = _get_session_or_404(db, session_id)
        results = (
            db.query(AnalysisResult)
            .filter(AnalysisResult.session_id == session.id)
            .order_by(AnalysisResult.id.asc())
            .all()
        )
        payload: list[dict[str, Any]] = []
        for row in results:
            if row.comparison:
                try:
                    entry = json.loads(row.comparison)
                    payload.append(entry)
                    continue
                except json.JSONDecodeError:
                    pass
            payload.append({
                "file_a": row.submission_a.filename if row.submission_a else "unknown",
                "file_b": row.submission_b.filename if row.submission_b else "unknown",
                "score": row.score,
                "jaccard_similarity": row.jaccard_similarity,
                "containment_similarity": row.containment_similarity,
                "ast_similarity": row.ast_similarity,
                "threshold": row.threshold,
                "suspicious": bool(row.suspicious),
                "is_exact_duplicate": bool(row.is_exact_duplicate),
                "status": "SUSPICIOUS" if row.suspicious else "LOW SIMILARITY",
            })
        return {
            "session_id": session.id,
            "total_comparisons": len(payload),
            "results": payload,
        }
    finally:
        db.close()


@app.post("/api/compare")
async def compare_pair_post(request: ComparePairRequest) -> dict[str, Any]:
    db = _get_session()
    try:
        _get_session_or_404(db, request.session_id)
        left = _get_submission_in_session(db, request.left_id, request.session_id)
        right = _get_submission_in_session(db, request.right_id, request.session_id)
        left_content = left.content
        right_content = right.content
        left_name = left.filename
        right_name = right.filename
    finally:
        db.close()

    result = compare_code_pair(left_content, right_content, threshold=request.threshold)
    regions = find_matching_regions(left_content, right_content)
    explanation = _build_pair_explanation(result["score"], request.threshold)

    return {
        "file_a": left_name,
        "file_b": right_name,
        "score": result["score"],
        "similarity_score": result["score"],
        "jaccard_similarity": result.get("jaccard_similarity", result["score"]),
        "containment_similarity": result.get("containment_similarity", 0.0),
        "ast_similarity": result.get("ast_similarity", 0.0),
        "threshold": request.threshold,
        "suspicious": result["suspicious"],
        "is_exact_duplicate": result.get("is_exact_duplicate", False),
        "status": "SUSPICIOUS" if result["suspicious"] else "LOW SIMILARITY",
        "status_a": result.get("status_a", "ok"),
        "status_b": result.get("status_b", "ok"),
        "explanation": explanation,
        "analysis_config": result.get("analysis_config", {}),
        "left_lines": regions["left_lines"],
        "right_lines": regions["right_lines"],
        "left_matched_lines": regions["left_matched_lines"],
        "right_matched_lines": regions["right_matched_lines"],
        "matches": regions["matches"],
    }
