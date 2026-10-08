import os
import shutil
import tempfile

_tmp = tempfile.mkdtemp(prefix="certtests_")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["CERT_STORAGE_DIR"] = f"{_tmp}/storage"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config, database  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    database.Base.metadata.drop_all(database.engine)
    database.Base.metadata.create_all(database.engine)
    shutil.rmtree(config.STORAGE_DIR, ignore_errors=True)
    config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    with TestClient(app) as c:  # background tasks run before the response returns
        yield c


CERT = {"title": "Certificate of Completion", "event_name": "Python Bootcamp",
        "issued_by": "Tech Academy", "issue_date": "2026-10-01"}


def make_payload(recipients):
    return {"certificate": CERT, "recipients": recipients}
