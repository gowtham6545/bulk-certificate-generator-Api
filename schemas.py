from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class CertificateInfo(BaseModel):
    title: str = Field("Certificate of Participation", min_length=1, max_length=200)
    event_name: str = Field(..., min_length=1, max_length=200)
    issued_by: str = Field(..., min_length=1, max_length=200)
    issue_date: date = Field(default_factory=date.today)
    description: str | None = Field(None, max_length=500)


class JobCreate(BaseModel):
    certificate: CertificateInfo
    # Recipients are deliberately loose dicts: one bad row must not reject the
    # whole request. Each row is validated individually (see app/validation.py).
    recipients: list[dict[str, Any]] = Field(..., min_length=1)


class RecipientIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    email: str = Field(..., max_length=320)


class ItemOut(BaseModel):
    id: str
    position: int
    name: str | None
    email: str | None
    status: str
    error: str | None
    download_url: str | None = None


class JobSummary(BaseModel):
    total: int
    pending: int
    processing: int
    completed: int
    failed: int
    invalid: int
    progress_percent: float


class JobOut(BaseModel):
    id: str
    status: str
    title: str
    event_name: str
    issued_by: str
    issue_date: str
    error: str | None
    created_at: str
    completed_at: str | None
    summary: JobSummary
    items: list[ItemOut]
    download_all_url: str | None = None


class JobAccepted(BaseModel):
    id: str
    status: str
    status_url: str
    summary: JobSummary
    rejected_recipients: list[ItemOut]
