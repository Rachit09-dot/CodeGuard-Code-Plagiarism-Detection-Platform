from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from backend.database import Base, SessionLocal, engine
from backend.models import AnalysisResult, AnalysisSession, Submission
from backend.services.plagiarism_engine import compare_code_pair, find_matching_regions
from backend.services.storage_service import save_uploaded_file

ALLOWED_EXTENSIONS = {".py"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024


def ensure_database_schema() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    if "analysis_sessions" not in tables:
        Base.metadata.create_all(bind=engine)
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())

    with SessionLocal() as db:
        if "analysis_sessions" in tables:
            session_count = db.query(AnalysisSession).count()
            if session_count == 0:
                legacy_session = AnalysisSession(
                    threshold=0.6,
                    total_submissions=0,
                    total_comparisons=0,
                    suspicious_pairs=0,
                    average_similarity=0.0,
                )
                db.add(legacy_session)
                db.commit()
                db.refresh(legacy_session)
                legacy_session_id = legacy_session.id
            else:
                legacy_session_id = db.query(AnalysisSession).order_by(AnalysisSession.id.asc()).first().id

            if "submissions" in tables:
                submission_columns = {column["name"] for column in inspector.get_columns("submissions")}
                if "session_id" not in submission_columns:
                    db.execute(text("ALTER TABLE submissions ADD COLUMN session_id INTEGER"))
                    db.execute(
                        text("UPDATE submissions SET session_id = :session_id WHERE session_id IS NULL"),
                        {"session_id": legacy_session_id},
                    )

            if "analysis_results" in tables:
                result_columns = {column["name"] for column in inspector.get_columns("analysis_results")}
                if "session_id" not in result_columns:
                    db.execute(text("ALTER TABLE analysis_results ADD COLUMN session_id INTEGER"))
                    db.execute(
                        text("UPDATE analysis_results SET session_id = :session_id WHERE session_id IS NULL"),
                        {"session_id": legacy_session_id},
                    )
            db.commit()


ensure_database_schema()

app = FastAPI(title="Code Plagiarism Platform", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000", "http://localhost:3002"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _coerce_threshold(raw_value: Any) -> float:
    if raw_value is None:
        return 0.6
    try:
        threshold = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Similarity threshold must be numeric.") from exc
    if not 0.0 <= threshold <= 1.0:
        raise HTTPException(status_code=400, detail="Similarity threshold must be between 0 and 1.")
    return threshold


def _build_pair_explanation(score: float, threshold: float) -> str:
    percent = score * 100
    threshold_percent = threshold * 100
    if score >= threshold:
        return (
            f"This pair exceeded the configured similarity threshold. The normalized similarity is {percent:.1f}% "
            f"which is at or above the current threshold of {threshold_percent:.1f}%. "
            "This should be manually reviewed as a screening result only."
        )
    return (
        f"This pair is below the configured threshold. Similarity is {percent:.1f}% against a threshold of "
        f"{threshold_percent:.1f}%, so it is classified as low similarity and not automatically flagged."
    )


def _validate_submission_name(filename: str) -> str:
    clean_name = (filename or "submission.py").strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="No Python file name was provided.")

    if clean_name in {".", ".."} or "/" in clean_name or "\\" in clean_name:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type for '{clean_name}'. Only Python (.py) files are allowed.",
        )

    basename = Path(clean_name).name
    if basename != clean_name:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type for '{clean_name}'. Only Python (.py) files are allowed.",
        )

    suffix = Path(clean_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type for '{clean_name}'. Only Python (.py) files are allowed.",
        )
    return clean_name


def _find_session_for_payload(db: Any, payload: dict[str, Any], submission_ids: list[int] | None = None) -> AnalysisSession | None:
    session_id = payload.get("session_id")
    if session_id is not None:
        return db.query(AnalysisSession).filter(AnalysisSession.id == int(session_id)).first()
    if submission_ids:
        submission = db.query(Submission).filter(Submission.id.in_(submission_ids)).first()
        if submission:
            return db.query(AnalysisSession).filter(AnalysisSession.id == submission.session_id).first()
    return None


@app.get("/health")
@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "code-plagiarism-platform"}


@app.post("/api/upload")
async def upload_files(files: list[UploadFile] = File(...)) -> dict[str, Any]:
    if not files:
        raise HTTPException(status_code=400, detail="No Python files were uploaded.")

    validated_files: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for upload in files:
        filename = _validate_submission_name(upload.filename or "submission.py")
        if filename in seen_names:
            raise HTTPException(status_code=400, detail=f"Duplicate filename found: {filename}")
        seen_names.add(filename)

        upload.file.seek(0)
        content = upload.file.read()
        upload.file.seek(0)
        if not content or not content.strip():
            raise HTTPException(status_code=400, detail=f"File is empty: {filename}. Please upload Python code with content.")
        if len(content) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(status_code=413, detail=f"File too large: {filename}. Maximum size is 10 MB.")
        try:
            text_content = content.decode("utf-8")
        except UnicodeDecodeError:
            text_content = content.decode("utf-8", errors="ignore")
        validated_files.append({"filename": filename, "content": text_content})

    db = SessionLocal()
    session: AnalysisSession | None = None
    created_paths: list[str] = []
    saved: list[dict[str, Any]] = []
    try:
        session = AnalysisSession(
            threshold=0.6,
            total_submissions=0,
            total_comparisons=0,
            suspicious_pairs=0,
            average_similarity=0.0,
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        for item in validated_files:
            safe_path, display_name = save_uploaded_file(item["filename"], item["content"].encode("utf-8"), directory=f"session_{session.id}")
            created_paths.append(safe_path)
            submission = Submission(
                session_id=session.id,
                filename=display_name,
                content=item["content"],
                language="py",
                analysis_status="uploaded",
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
            })

        session.total_submissions = len(saved)
        db.add(session)
        db.commit()
        return {"success": True, "session_id": session.id, "total_submissions": len(saved), "submissions": saved}
    except Exception:
        db.rollback()
        for path_text in created_paths:
            try:
                Path(path_text).unlink(missing_ok=True)
            except OSError:
                pass
        if session is not None:
            db.query(Submission).filter(Submission.session_id == session.id).delete()
            db.query(AnalysisSession).filter(AnalysisSession.id == session.id).delete()
            db.commit()
        raise
    finally:
        db.close()


@app.get("/api/submissions")
async def list_submissions(session_id: int | None = None) -> dict[str, Any]:
    db = SessionLocal()
    try:
        query = db.query(Submission)
        if session_id is not None:
            query = query.filter(Submission.session_id == int(session_id))
        submissions = query.order_by(Submission.id.asc()).all()
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
                }
                for item in submissions
            ],
        }
    finally:
        db.close()


@app.post("/api/analyze")
async def analyze_submission(payload: dict[str, Any] | None) -> dict[str, Any]:
    db = SessionLocal()
    try:
        request = payload or {}
        session_id_raw = request.get("session_id")
        threshold = _coerce_threshold(request.get("threshold", 0.6))

        if session_id_raw is None:
            raise HTTPException(status_code=400, detail="Current session_id is required for analysis.")

        try:
            session_id = int(session_id_raw)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="session_id must be an integer.") from exc

        session = db.query(AnalysisSession).filter(AnalysisSession.id == session_id).first()
        if session is None:
            raise HTTPException(status_code=404, detail=f"Analysis session {session_id} was not found.")

        submission_ids = request.get("submission_ids") or []
        try:
            target_ids = sorted({int(item) for item in submission_ids})
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Submission IDs must be integers.") from exc

        allowed_ids = {
            row[0]
            for row in db.query(Submission.id)
            .filter(Submission.session_id == session.id)
            .filter(Submission.id.in_(target_ids))
            .all()
        }
        filtered_ids = sorted(allowed_ids)

        if not filtered_ids:
            raise HTTPException(status_code=404, detail="No submissions were found for the selected session.")
        if len(filtered_ids) < 2:
            raise HTTPException(status_code=400, detail="At least two submissions are required for comparison.")

        submissions = (
            db.query(Submission)
            .filter(Submission.id.in_(filtered_ids), Submission.session_id == session.id)
            .order_by(Submission.id.asc())
            .all()
        )

        if len(submissions) < 2:
            raise HTTPException(status_code=400, detail="At least two submissions are required for comparison.")

        compared: list[dict[str, Any]] = []
        for index, left in enumerate(submissions):
            for right in submissions[index + 1 :]:
                if left.id == right.id:
                    continue
                score = compare_code_pair(left.content, right.content)
                suspicious = score >= threshold
                compared.append(
                    {
                        "file_a": left.filename,
                        "file_b": right.filename,
                        "score": round(score, 4),
                        "similarity_score": round(score, 4),
                        "suspicious": suspicious,
                        "status": "SUSPICIOUS" if suspicious else "LOW SIMILARITY",
                    }
                )

        compared.sort(key=lambda item: (item["score"], item["file_a"], item["file_b"]), reverse=True)

        suspicious_pair_count = sum(1 for item in compared if item["suspicious"])
        average_similarity = (
            round(sum(item["score"] for item in compared) / len(compared), 4) if compared else 0.0
        )

        for item in compared:
            left_submission = db.query(Submission).filter(
                Submission.filename == item["file_a"],
                Submission.session_id == session.id,
            ).first()
            right_submission = db.query(Submission).filter(
                Submission.filename == item["file_b"],
                Submission.session_id == session.id,
            ).first()
            if left_submission and right_submission:
                result = AnalysisResult(
                    session_id=session.id,
                    submission_a_id=left_submission.id,
                    submission_b_id=right_submission.id,
                    score=item["score"],
                    threshold=threshold,
                    suspicious="true" if item["suspicious"] else "false",
                    comparison=json.dumps(item),
                )
                db.add(result)

        session.threshold = threshold
        session.total_submissions = len(submissions)
        session.total_comparisons = len(compared)
        session.suspicious_pairs = suspicious_pair_count
        session.average_similarity = average_similarity
        db.add(session)
        db.commit()

        return {
            "session_id": session.id,
            "threshold": threshold,
            "total_submissions": len(submissions),
            "total_comparisons": len(compared),
            "checked_pairs": len(compared),
            "suspicious_pair_count": suspicious_pair_count,
            "flagged_pairs": suspicious_pair_count,
            "average_similarity": average_similarity,
            "results": compared,
        }
    finally:
        db.close()


@app.get("/api/compare")
async def get_comparison_results(session_id: int | None = None) -> dict[str, Any]:
    if session_id is None:
        raise HTTPException(status_code=400, detail="session_id is required.")

    db = SessionLocal()
    try:
        session = db.query(AnalysisSession).filter(AnalysisSession.id == int(session_id)).first()
        if session is None:
            raise HTTPException(status_code=404, detail=f"Analysis session {session_id} was not found.")

        results = (
            db.query(AnalysisResult)
            .filter(AnalysisResult.session_id == session.id)
            .order_by(AnalysisResult.id.asc())
            .all()
        )
        payload = []
        for row in results:
            if row.comparison:
                try:
                    payload.append(json.loads(row.comparison))
                    continue
                except json.JSONDecodeError:
                    pass
            payload.append(
                {
                    "file_a": row.submission_a.filename if row.submission_a else "unknown",
                    "file_b": row.submission_b.filename if row.submission_b else "unknown",
                    "score": row.score,
                    "threshold": row.threshold,
                    "suspicious": row.suspicious.lower() == "true",
                    "status": "SUSPICIOUS" if row.suspicious.lower() == "true" else "LOW SIMILARITY",
                }
            )

        return {
            "session_id": session.id,
            "total_comparisons": len(payload),
            "results": payload,
        }
    finally:
        db.close()


@app.post("/api/compare")
async def compare_pair_post(payload: dict[str, Any] | None) -> dict[str, Any]:
    request = payload or {}
    left_id = request.get("left_id")
    right_id = request.get("right_id")
    threshold = _coerce_threshold(request.get("threshold", 0.6))
    if left_id is None or right_id is None:
        raise HTTPException(status_code=400, detail="left_id and right_id are required.")
    if int(left_id) == int(right_id):
        raise HTTPException(status_code=400, detail="A submission cannot be compared with itself.")

    db = SessionLocal()
    try:
        left = db.query(Submission).filter(Submission.id == int(left_id)).first()
        right = db.query(Submission).filter(Submission.id == int(right_id)).first()
        if not left or not right:
            raise HTTPException(status_code=404, detail="One or both submissions were not found.")

        session_id = request.get("session_id")
        if session_id is not None:
            try:
                session_id = int(session_id)
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail="session_id must be an integer.") from exc
            if left.session_id != session_id or right.session_id != session_id:
                raise HTTPException(status_code=400, detail="Comparison must stay within the current session.")

        score = compare_code_pair(left.content, right.content)
        regions = find_matching_regions(left.content, right.content)
        suspicious = score >= threshold
        explanation = _build_pair_explanation(score, threshold)
        return {
            "file_a": left.filename,
            "file_b": right.filename,
            "score": round(score, 4),
            "threshold": threshold,
            "suspicious": suspicious,
            "status": "SUSPICIOUS" if suspicious else "LOW SIMILARITY",
            "explanation": explanation,
            "left_lines": regions["left_lines"],
            "right_lines": regions["right_lines"],
            "matches": regions["matches"],
        }
    finally:
        db.close()
