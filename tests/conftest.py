"""pytest configuration: isolated test database and temp storage.

Every test that uses ``test_client`` gets:
* A fresh file-based SQLite database in a tmp directory.
* A temporary storage directory.
* The FastAPI TestClient pointing to that isolated state.

We use a **file-based** SQLite (in tmp_path) rather than in-memory because
in-memory SQLite connections do not share tables between connections; every
call to ``engine.connect()`` would see an empty DB.  A file-based DB in
``tmp_path`` is automatically cleaned up after the test by pytest.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SUBMISSIONS_DIR = Path(__file__).parent.parent / "submissions"


@pytest.fixture()
def sample_files_bytes() -> dict[str, bytes]:
    """Content of the four sample submission files."""
    result: dict[str, bytes] = {}
    for name in ["alice.py", "bob.py", "carol.py", "dave.py"]:
        result[name] = (SUBMISSIONS_DIR / name).read_bytes()
    return result


@pytest.fixture()
def test_client(tmp_path):
    """TestClient backed by an isolated file-based SQLite DB + temp storage.

    Patches ``backend.database.engine`` and ``backend.database.SessionLocal``
    so ``backend.app._get_session()`` picks up the test engine at call time.
    """
    import backend.database as db_module
    import backend.app as app_module
    import backend.services.storage_service as storage_module
    from backend.models import Base

    # ── 1. File-based SQLite in tmp_path ──────────────────────────────────
    db_path = tmp_path / "test_plagiarism.db"
    test_engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    TestSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_engine
    )

    # ── 2. Temp storage dir ────────────────────────────────────────────────
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()

    # ── 3. Create schema on the test engine ───────────────────────────────
    Base.metadata.create_all(bind=test_engine)

    # ── 4. Swap module-level references ───────────────────────────────────
    orig_engine   = db_module.engine
    orig_session  = db_module.SessionLocal
    orig_storage  = storage_module.UPLOAD_DIR

    db_module.engine        = test_engine
    db_module.SessionLocal  = TestSessionLocal
    storage_module.UPLOAD_DIR = storage_dir

    try:
        with TestClient(app_module.app) as client:
            yield client
    finally:
        db_module.engine        = orig_engine
        db_module.SessionLocal  = orig_session
        storage_module.UPLOAD_DIR = orig_storage
        test_engine.dispose()


@pytest.fixture()
def uploaded_session(test_client, sample_files_bytes):
    """Upload all 4 sample files; return upload response JSON."""
    files = [
        ("files", (name, data, "text/x-python"))
        for name, data in sample_files_bytes.items()
    ]
    resp = test_client.post("/api/upload", files=files)
    assert resp.status_code == 200, resp.text
    return resp.json()
