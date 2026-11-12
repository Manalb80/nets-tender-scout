"""
Database models for NETS Tender Scout.
SQLAlchemy ORM with SQLite (swap DATABASE_URL for PostgreSQL in production).
"""
import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text, Float, DateTime, JSON
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tender_scout.db")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {"sslmode": "require"} if "supabase" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Tender(Base):
    __tablename__ = "tenders"

    id = Column(String(100), primary_key=True)          # e.g. S-26080803636
    title = Column(String(500), nullable=False)
    department = Column(String(100))
    advertised = Column(String(50))                      # date string from portal
    closing = Column(String(50))                         # date string from portal
    closing_date = Column(DateTime, nullable=True)       # parsed closing date
    is_open = Column(Boolean, default=True)
    days_remaining = Column(Integer, nullable=True)
    score = Column(Integer, default=0)
    verdict = Column(String(20))                         # BID, REVIEW, NOGO, SKIP
    qual_verdict = Column(String(20), nullable=True)     # GO, NOGO, REVIEW (from qualification gates)
    qual_gates = Column(JSON, nullable=True)             # {gate: {pass, status, detail}}
    disqualification_reason = Column(Text, nullable=True)  # Why NOGO, if applicable
    matched_keywords = Column(JSON, default=list)        # ["firewall", "server"]
    matched_solutions = Column(JSON, default=list)       # [{"id":"...", "name":"...", "group":"..."}]
    document_url = Column(String(1000), nullable=True)   # RFP PDF link
    source_url = Column(String(1000), nullable=True)
    source_portal = Column(String(50), nullable=True)    # "PPRA" or "Sindh Bank"
    detail_url = Column(String(1000), nullable=True)     # tender detail page URL
    acquisition_status = Column(String(30), default="PENDING")  # PENDING, AUTO_DOWNLOADED, MANUAL_DOWNLOAD_REQUIRED, DROPPED
    doc_accessible = Column(Boolean, default=True)       # False if password protected or restricted
    local_folder = Column(String(500), nullable=True)    # D:\ path where RFP is saved
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ScanLog(Base):
    __tablename__ = "scan_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(50), nullable=False)
    total_on_portal = Column(Integer, default=0)
    qualified_count = Column(Integer, default=0)
    open_qualified_count = Column(Integer, default=0)
    new_count = Column(Integer, default=0)
    duration_seconds = Column(Float, nullable=True)
    status = Column(String(20), default="success")       # success, error
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Proposal(Base):
    __tablename__ = "proposals"

    id = Column(String(100), primary_key=True)           # same as tender id
    rfp_title = Column(String(500))
    client = Column(String(200), default="Sindh Bank")
    solutions = Column(JSON, default=list)
    proposal_text = Column(Text)
    proposal_words = Column(Integer, default=0)
    audit_score = Column(Integer, default=0)
    audit_verdict = Column(String(20))                   # PASS, REVISE, FAIL
    audit_requirements_met = Column(Integer, default=0)
    audit_requirements_total = Column(Integer, default=0)
    iterations = Column(Integer, default=0)
    status = Column(String(20), default="draft")
    generated_at = Column(DateTime, default=datetime.utcnow)


class Config(Base):
    __tablename__ = "config"

    key = Column(String(100), primary_key=True)
    value = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def init_db():
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)
    print(f"Database ready: {DATABASE_URL}")


def get_db():
    """FastAPI dependency: yields a DB session, closes after request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
