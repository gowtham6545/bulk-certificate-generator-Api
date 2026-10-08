# Bulk Certificate Generator (Backend API)

A FastAPI + SQLite service. A client submits **one request** containing many recipients; the
backend validates each recipient, generates a PDF certificate per valid recipient from a single
predefined template, tracks progress, and lets the client retrieve the results.

**Stack:** Python 3.10+, FastAPI, SQLAlchemy 2 (SQLite by default, any SQL DB via `DATABASE_URL`), ReportLab (PDF), pytest.

## Setup
```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run
```bash
uvicorn app.main:app --reload
```
Interactive docs: http://127.0.0.1:8000/docs. Tables are created automatically on startup.

Optional environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./certificates.db` | SQLAlchemy DB URL |
| `CERT_STORAGE_DIR` | `./storage` | Where PDFs are written |
| `MAX_RECIPIENTS_PER_JOB` | `1000` | Upper bound per request |

## Run tests
```bash
pytest -q
```
Tests use a temporary database/storage directory, so they never touch real data.

## API

| Method & path | Purpose |
|---|---|
| `POST /jobs` | Submit a bulk generation request (returns `202`) |
| `GET /jobs/{id}` | Job status, progress counts, per-recipient result/error |
| `GET /jobs/{id}/certificates` | List certificates generated so far |
| `GET /jobs/{id}/certificates/{item_id}` | Download one certificate (PDF) |
| `GET /jobs/{id}/download` | Download all generated certificates as a ZIP |

### Submit a request
```bash
curl -X POST http://127.0.0.1:8000/jobs -H "Content-Type: application/json" -d '{
  "certificate": {
    "title": "Certificate of Completion",
    "event_name": "Python Bootcamp",
    "issued_by": "Tech Academy",
    "issue_date": "2026-10-01"
  },
  "recipients": [
    {"name": "Asha Rao",   "email": "asha@example.com"},
    {"name": "Ben Carter", "email": "ben@example.com"}
  ]
}'
```
Response (`202 Accepted`): `{"id": "<job_id>", "status": "pending", "status_url": "/jobs/<job_id>", "summary": {...}, "rejected_recipients": [...]}`

`title` (default "Certificate of Participation"), `issue_date` (default today) and `description` are optional.

### Check progress
```bash
curl http://127.0.0.1:8000/jobs/<job_id>
```
Job `status`: `pending` → `processing` → `completed` | `completed_with_errors` | `failed`.
`summary` has `total / pending / processing / completed / failed / invalid / progress_percent`;
`items` lists every recipient with its own `status` and `error`.

### Retrieve certificates
```bash
curl -O -J http://127.0.0.1:8000/jobs/<job_id>/certificates/<item_id>   # one PDF
curl -O -J http://127.0.0.1:8000/jobs/<job_id>/download                 # all as ZIP
```
Certificates can be retrieved as soon as they are done, even while the job is still running.

## Design decisions

**Background processing (not synchronous).** `POST /jobs` stores the job and returns `202`
immediately; generation runs afterwards via FastAPI `BackgroundTasks`. A request with hundreds of
recipients could otherwise hold the HTTP connection open for a long time and hit client/proxy
timeouts. Clients poll `GET /jobs/{id}`. Each certificate is committed as soon as it finishes, so
progress is live. *Trade-off:* `BackgroundTasks` runs in the API process, so a server restart
mid-job leaves that job unfinished and there is no retry queue. In production I would swap
`process_job` for a Celery/RQ/Arq worker; the `process_job(job_id)` function is already
self-contained and only reads/writes through the database, so that swap is a small change.
It avoids needing Redis/RabbitMQ to run this assignment.

**Validation: per recipient, not all-or-nothing.** Request-level problems (missing certificate
info, empty list, over `MAX_RECIPIENTS_PER_JOB`, or *no* valid recipient at all) return `422`.
Otherwise a bad row (blank name, missing/invalid email, duplicate email within the request,
case-insensitive) is stored with status `invalid` and an explanatory `error`, is reported
immediately in `rejected_recipients`, and the valid rows are still generated.

**Failure isolation.** Each certificate is generated in its own `try/except` and committed
individually, so one failure marks only that item `failed` (with the error message) and the rest
continue. Final job status: `completed` (all good), `completed_with_errors` (some invalid/failed),
`failed` (nothing succeeded, or an unexpected job-level crash).

**Template.** One fixed landscape-A4 PDF layout drawn with ReportLab (no external assets). Long
names/event names automatically shrink to fit. PDFs are stored under `CERT_STORAGE_DIR/<job_id>/`;
the database stores jobs, per-recipient status/errors and file paths.

**Security/consistency.** Downloads look up files by DB id (never by user-supplied path) and verify
the item belongs to the requested job.

## Project layout
```
app/
  main.py        routes
  models.py      Job / JobItem tables and status constants
  schemas.py     request/response models
  validation.py  per-recipient validation
  generator.py   PDF template rendering
  processor.py   background job runner
  config.py, database.py
tests/           14 tests (creation, validation, generation, status, failure isolation, retrieval)
```
