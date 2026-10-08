import io
import zipfile

from pypdf import PdfReader

from app import generator
from tests.conftest import make_payload

GOOD = [{"name": "Asha Rao", "email": "asha@example.com"},
        {"name": "Ben Carter", "email": "ben@example.com"},
        {"name": "Chitra Devi", "email": "chitra@example.com"}]


# ---- creating a generation job ----
def test_create_job_returns_202_and_job_id(client):
    r = client.post("/jobs", json=make_payload(GOOD))
    assert r.status_code == 202
    body = r.json()
    assert body["id"] and body["status_url"] == f"/jobs/{body['id']}"
    assert body["summary"]["total"] == 3


def test_missing_certificate_info_is_rejected(client):
    r = client.post("/jobs", json={"certificate": {"title": "x"}, "recipients": GOOD})
    assert r.status_code == 422


def test_empty_recipient_list_is_rejected(client):
    assert client.post("/jobs", json=make_payload([])).status_code == 422


# ---- input validation ----
def test_invalid_recipients_are_reported_but_valid_ones_proceed(client):
    recipients = GOOD[:1] + [
        {"name": "", "email": "x@example.com"},
        {"name": "No Email"},
        {"name": "Bad Email", "email": "not-an-email"},
        {"name": "Dup", "email": "ASHA@example.com"},   # duplicate (case-insensitive)
    ]
    r = client.post("/jobs", json=make_payload(recipients))
    assert r.status_code == 202
    assert len(r.json()["rejected_recipients"]) == 4

    job = client.get(f"/jobs/{r.json()['id']}").json()
    assert job["status"] == "completed_with_errors"
    assert job["summary"]["completed"] == 1 and job["summary"]["invalid"] == 4
    assert all(i["error"] for i in job["items"] if i["status"] == "invalid")


def test_all_invalid_recipients_rejected_with_422(client):
    r = client.post("/jobs", json=make_payload([{"name": "", "email": "bad"}]))
    assert r.status_code == 422


# ---- certificate generation ----
def test_certificate_pdf_contains_recipient_details(client):
    job_id = client.post("/jobs", json=make_payload(GOOD[:1])).json()["id"]
    item = client.get(f"/jobs/{job_id}").json()["items"][0]
    pdf = client.get(item["download_url"])
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    text = PdfReader(io.BytesIO(pdf.content)).pages[0].extract_text()
    assert "Asha Rao" in text and "Python Bootcamp" in text and "Tech Academy" in text


def test_very_long_name_still_generates(client):
    long_name = "A" * 150
    job_id = client.post("/jobs", json=make_payload([{"name": long_name, "email": "l@example.com"}])).json()["id"]
    assert client.get(f"/jobs/{job_id}").json()["summary"]["completed"] == 1


# ---- job status / progress ----
def test_job_status_and_progress(client):
    job_id = client.post("/jobs", json=make_payload(GOOD)).json()["id"]
    job = client.get(f"/jobs/{job_id}").json()
    assert job["status"] == "completed"
    assert job["summary"]["completed"] == 3
    assert job["summary"]["progress_percent"] == 100.0
    assert job["completed_at"] is not None


def test_unknown_job_returns_404(client):
    assert client.get("/jobs/doesnotexist").status_code == 404


# ---- an individual certificate failing ----
def test_single_failure_does_not_block_other_certificates(client, monkeypatch):
    real = generator.render_certificate

    def flaky(path, **kw):
        if kw["recipient_name"] == "Ben Carter":
            raise RuntimeError("boom")
        return real(path, **kw)

    monkeypatch.setattr(generator, "render_certificate", flaky)
    job_id = client.post("/jobs", json=make_payload(GOOD)).json()["id"]
    job = client.get(f"/jobs/{job_id}").json()

    assert job["status"] == "completed_with_errors"
    assert job["summary"]["completed"] == 2 and job["summary"]["failed"] == 1
    failed = [i for i in job["items"] if i["status"] == "failed"]
    assert failed[0]["name"] == "Ben Carter" and "boom" in failed[0]["error"]
    assert client.get(f"/jobs/{job_id}/certificates/{failed[0]['id']}").status_code == 409


def test_job_fails_when_every_certificate_fails(client, monkeypatch):
    def always_fail(*a, **k):
        raise RuntimeError("nope")

    monkeypatch.setattr(generator, "render_certificate", always_fail)
    job_id = client.post("/jobs", json=make_payload(GOOD)).json()["id"]
    assert client.get(f"/jobs/{job_id}").json()["status"] == "failed"


# ---- retrieving generated certificates ----
def test_list_and_download_certificates(client):
    job_id = client.post("/jobs", json=make_payload(GOOD)).json()["id"]
    listing = client.get(f"/jobs/{job_id}/certificates").json()
    assert len(listing["certificates"]) == 3
    for cert in listing["certificates"]:
        assert client.get(cert["download_url"]).content.startswith(b"%PDF")


def test_download_all_as_zip(client):
    job_id = client.post("/jobs", json=make_payload(GOOD)).json()["id"]
    r = client.get(f"/jobs/{job_id}/download")
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert len(zf.namelist()) == 3 and all(n.endswith(".pdf") for n in zf.namelist())


def test_certificate_of_other_job_is_not_accessible(client):
    a = client.post("/jobs", json=make_payload(GOOD[:1])).json()["id"]
    b = client.post("/jobs", json=make_payload(GOOD[1:2])).json()["id"]
    item_a = client.get(f"/jobs/{a}").json()["items"][0]["id"]
    assert client.get(f"/jobs/{b}/certificates/{item_a}").status_code == 404
