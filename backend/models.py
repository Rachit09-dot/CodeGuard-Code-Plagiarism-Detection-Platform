from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .database import Base


class AnalysisSession(Base):
    __tablename__ = "analysis_sessions"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    threshold = Column(Float, default=0.6, nullable=False)
    total_submissions = Column(Integer, default=0, nullable=False)
    total_comparisons = Column(Integer, default=0, nullable=False)
    suspicious_pairs = Column(Integer, default=0, nullable=False)
    average_similarity = Column(Float, default=0.0, nullable=False)

    submissions = relationship("Submission", back_populates="session")
    results = relationship("AnalysisResult", back_populates="session")


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("analysis_sessions.id"), nullable=False, index=True)
    filename = Column(String, nullable=False)
    language = Column(String, default="python")
    content = Column(Text, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
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
    submission_a_id = Column(Integer, ForeignKey("submissions.id"), nullable=False)
    submission_b_id = Column(Integer, ForeignKey("submissions.id"), nullable=False)
    score = Column(Float, nullable=False)
    threshold = Column(Float, nullable=False)
    suspicious = Column(String, default="false")
    created_at = Column(DateTime, default=datetime.utcnow)
    comparison = Column(Text, nullable=True)

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
