"""SQLAlchemy ORM models.

Changes from the original
-------------------------
* ``suspicious`` is now a proper ``Boolean`` column (was ``String("true"/"false")``).
* ``datetime.utcnow`` replaced with a timezone-aware UTC lambda so the field
  always stores tz-aware datetimes (compatible with both SQLite and PostgreSQL).
* ``AnalysisResult`` has a ``UniqueConstraint`` on
  ``(session_id, submission_a_id, submission_b_id)`` so that re-running
  analysis on the same session does not create duplicate rows.  The application
  normalises pairs so that ``submission_a_id < submission_b_id`` before
  inserting, making the constraint order-independent (A-B == B-A).
* Added ``content_hash`` (SHA-256 hex) to ``Submission`` for exact-duplicate
  detection.
* Added ``jaccard_similarity``, ``containment_similarity``, ``ast_similarity``
  columns to ``AnalysisResult`` so all metrics persist.
* Added an index on ``Submission.content_hash`` for efficient exact-duplicate
  look-ups.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


def _utcnow() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(tz=timezone.utc)


class AnalysisSession(Base):
    __tablename__ = "analysis_sessions"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=_utcnow)
    threshold = Column(Float, default=0.6, nullable=False)
    total_submissions = Column(Integer, default=0, nullable=False)
    total_comparisons = Column(Integer, default=0, nullable=False)
    suspicious_pairs = Column(Integer, default=0, nullable=False)
    average_similarity = Column(Float, default=0.0, nullable=False)

    submissions = relationship("Submission", back_populates="session", cascade="all, delete-orphan")
    results = relationship("AnalysisResult", back_populates="session", cascade="all, delete-orphan")


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("analysis_sessions.id"), nullable=False, index=True)
    filename = Column(String, nullable=False)
    language = Column(String, default="python")
    content = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False, index=True)  # SHA-256 hex
    uploaded_at = Column(DateTime, default=_utcnow)
    analysis_status = Column(String, default="pending")

    session = relationship("AnalysisSession", back_populates="submissions")
    results_as_left = relationship(
        "AnalysisResult",
        foreign_keys="AnalysisResult.submission_a_id",
        back_populates="submission_a",
    )
    results_as_right = relationship(
        "AnalysisResult",
        foreign_keys="AnalysisResult.submission_b_id",
        back_populates="submission_b",
    )


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("analysis_sessions.id"), nullable=False, index=True)
    # submission_a_id is always the numerically smaller of the two IDs
    # so (session_id, submission_a_id, submission_b_id) is a canonical key.
    submission_a_id = Column(Integer, ForeignKey("submissions.id"), nullable=False)
    submission_b_id = Column(Integer, ForeignKey("submissions.id"), nullable=False)

    # All similarity metrics stored individually
    score = Column(Float, nullable=False)                          # combined score
    jaccard_similarity = Column(Float, nullable=True)
    containment_similarity = Column(Float, nullable=True)
    ast_similarity = Column(Float, nullable=True)

    threshold = Column(Float, nullable=False)
    suspicious = Column(Boolean, default=False, nullable=False)    # was String
    is_exact_duplicate = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=_utcnow)
    comparison = Column(Text, nullable=True)                       # JSON snapshot

    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "submission_a_id",
            "submission_b_id",
            name="uq_analysis_result_pair",
        ),
    )

    session = relationship("AnalysisSession", back_populates="results")
    submission_a = relationship(
        "Submission",
        foreign_keys=[submission_a_id],
        back_populates="results_as_left",
    )
    submission_b = relationship(
        "Submission",
        foreign_keys=[submission_b_id],
        back_populates="results_as_right",
    )
