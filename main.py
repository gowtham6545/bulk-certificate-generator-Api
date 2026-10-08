import io
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from . import config, database
from .database import get_db
from .models import (ITEM_COMPLETED, ITEM_FAILED, ITEM_INVALID, ITEM_PENDING,
                     ITEM_PROCESSING, Job, JobItem)
from .processor import process_job
from .schemas import ItemOut, JobAccepted, JobCreate, JobOut, JobSummary
from .validation import validate_recipient


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.Base.metadata.create_all(database.engine)
    config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Bulk Certificate Generator", version="1.0.0", lifespan=lifespan)


# ---------- helpers ----------
def _summary(job: Job) -> JobSummary:
    counts = {s: 0 for s in (ITEM_PENDING, ITEM_PROCESSING, ITEM_COMPLETED, ITEM_FAILED, ITEM_INVALID)}
    for i in job.items:
        counts[i.status] = counts.get(i.status, 0) + 1
    valid = len(job.items) - counts[ITEM_INVALID]
    done = counts[ITEM_COMPLETED] + counts[ITEM_FAILED]
    return JobSummary(
        total=len(job.items), pending=counts[ITEM_PENDING], processing=counts[ITEM_PROCESSING],
        completed=counts[ITEM_COMPLETED], failed=counts[ITEM_FAILED], invalid=counts[ITEM_INVALID],
        progress_percent=round(100 * done / valid, 1) if valid else 100.0)


def _item_out(job_id: str, i: JobItem) -> ItemOut:
    url = (f"/jobs/{job_id}/certificates/{i.id}" if i.status == ITEM_COMPLETED else None)
    return ItemOut(id=i.id, position=i.position, name=i.name, email=i.email,
                   status=i.status, error=i.error, download_url=url)


def _get_job(db: Session, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


# ---------- endpoints ----------
@app.post("/jobs", status_code=202, response_model=JobAccepted)
def create_job(payload: JobCreate, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Submit one request containing many recipients. Returns immediately (202);
    certificates are generated in the background."""
    if len(payload.recipients) > config.MAX_RECIPIENTS_PER_JOB:
        raise HTTPException(422, f"Too many recipients (max {config.MAX_RECIPIENTS_PER_JOB} per job)")

    cert = payload.certificate
    job = Job(title=cert.title, event_name=cert.event_name, issued_by=cert.issued_by,
              issue_date=cert.issue_date.isoformat(), description=cert.description)
    seen: set[str] = set()
    for pos, raw in enumerate(payload.recipients):
        name, email, error = validate_recipient(raw, seen)
        job.items.append(JobItem(
            position=pos, name=name, email=email,
            status=ITEM_INVALID if error else ITEM_PENDING, error=error))

    if all(i.status == ITEM_INVALID for i in job.items):
        raise HTTPException(422, {
            "message": "No valid recipients in request",
            "errors": [{"position": i.position, "error": i.error} for i in job.items]})

    db.add(job)
    db.commit()
    background.add_task(process_job, job.id)
    return JobAccepted(
        id=job.id, status=job.status, status_url=f"/jobs/{job.id}", summary=_summary(job),
        rejected_recipients=[_item_out(job.id, i) for i in job.items if i.status == ITEM_INVALID])


@app.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)):
    """Job status, progress counts and per-recipient results."""
    job = _get_job(db, job_id)
    s = _summary(job)
    return JobOut(
        id=job.id, status=job.status, title=job.title, event_name=job.event_name,
        issued_by=job.issued_by, issue_date=job.issue_date, error=job.error,
        created_at=job.created_at.isoformat(),
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        summary=s, items=[_item_out(job.id, i) for i in job.items],
        download_all_url=f"/jobs/{job.id}/download" if s.completed else None)


@app.get("/jobs/{job_id}/certificates")
def list_certificates(job_id: str, db: Session = Depends(get_db)):
    """List certificates generated so far (completed items only)."""
    job = _get_job(db, job_id)
    return {"job_id": job.id, "status": job.status,
            "certificates": [_item_out(job.id, i) for i in job.items if i.status == ITEM_COMPLETED]}


@app.get("/jobs/{job_id}/certificates/{item_id}")
def download_certificate(job_id: str, item_id: str, db: Session = Depends(get_db)):
    """Download a single certificate PDF."""
    item = db.get(JobItem, item_id)
    if item is None or item.job_id != job_id:
        raise HTTPException(404, "Certificate not found")
    if item.status != ITEM_COMPLETED or not item.file_path or not Path(item.file_path).exists():
        raise HTTPException(409, f"Certificate not available (status: {item.status})")
    return FileResponse(item.file_path, media_type="application/pdf",
                        filename=Path(item.file_path).name)


@app.get("/jobs/{job_id}/download")
def download_all(job_id: str, db: Session = Depends(get_db)):
    """Download every generated certificate of the job as one ZIP."""
    job = _get_job(db, job_id)
    files = [Path(i.file_path) for i in job.items
             if i.status == ITEM_COMPLETED and i.file_path and Path(i.file_path).exists()]
    if not files:
        raise HTTPException(409, "No certificates available yet")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, arcname=f.name)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="job_{job.id}.zip"'})


@app.get("/health")
def health():
    return {"status": "ok"}
