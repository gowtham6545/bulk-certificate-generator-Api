"""Background job processing."""
import logging
from datetime import datetime, timezone

from . import config, database, generator
from .models import (ITEM_COMPLETED, ITEM_FAILED, ITEM_INVALID, ITEM_PENDING,
                     ITEM_PROCESSING, JOB_COMPLETED, JOB_COMPLETED_WITH_ERRORS,
                     JOB_FAILED, JOB_PROCESSING, Job, JobItem)

log = logging.getLogger(__name__)


def process_job(job_id: str) -> None:
    """Generate every pending item of a job.

    Each item is handled in its own try/except and committed immediately, so
    (a) one failure never stops the others and (b) status polling shows live
    progress.
    """
    db = database.SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            return
        job.status = JOB_PROCESSING
        db.commit()

        pending = (db.query(JobItem)
                   .filter(JobItem.job_id == job_id, JobItem.status == ITEM_PENDING)
                   .order_by(JobItem.position).all())

        for item in pending:
            item.status = ITEM_PROCESSING
            db.commit()
            try:
                path = (config.STORAGE_DIR / job_id /
                        f"{item.position:04d}_{generator.slugify(item.name)}_{item.id[:8]}.pdf")
                generator.render_certificate(
                    path, recipient_name=item.name, title=job.title,
                    event_name=job.event_name, issued_by=job.issued_by,
                    issue_date=job.issue_date, description=job.description)
                item.file_path = str(path)
                item.status = ITEM_COMPLETED
                item.error = None
            except Exception as exc:  # noqa: BLE001 - isolate any per-item failure
                log.exception("Certificate generation failed for item %s", item.id)
                item.status = ITEM_FAILED
                item.error = f"{type(exc).__name__}: {exc}"
            db.commit()

        db.refresh(job)
        any_problem = any(i.status in (ITEM_FAILED, ITEM_INVALID) for i in job.items)
        none_ok = not any(i.status == ITEM_COMPLETED for i in job.items)
        job.status = (JOB_FAILED if none_ok else
                      JOB_COMPLETED_WITH_ERRORS if any_problem else JOB_COMPLETED)
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:  # noqa: BLE001 - unexpected, job-level failure
        log.exception("Job %s crashed", job_id)
        db.rollback()
        job = db.get(Job, job_id)
        if job:
            job.status = JOB_FAILED
            job.error = f"{type(exc).__name__}: {exc}"
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()
