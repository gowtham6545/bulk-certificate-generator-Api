"""Per-recipient validation."""
import re

from pydantic import ValidationError

from .schemas import RecipientIn

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_recipient(raw: dict, seen_emails: set[str]) -> tuple[str | None, str | None, str | None]:
    """Return (name, email, error). `error` is None when the recipient is valid.

    Mutates `seen_emails` so duplicates inside one request are rejected.
    """
    name = raw.get("name") if isinstance(raw.get("name"), str) else None
    email = raw.get("email") if isinstance(raw.get("email"), str) else None
    try:
        parsed = RecipientIn(**{k: raw.get(k) for k in ("name", "email")})
    except ValidationError as exc:
        msgs = [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]
        return name, email, "; ".join(msgs)

    clean_name = parsed.name.strip()
    clean_email = parsed.email.strip().lower()
    if not clean_name:
        return name, email, "name: must not be blank"
    if not _EMAIL_RE.match(clean_email):
        return clean_name, parsed.email, "email: not a valid email address"
    if clean_email in seen_emails:
        return clean_name, clean_email, "email: duplicate within this request"
    seen_emails.add(clean_email)
    return clean_name, clean_email, None
