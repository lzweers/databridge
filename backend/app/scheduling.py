"""Persistent single-connector scheduler with observable retries.

Designed for one Docker worker. PostgreSQL row-locks protect the claim between
multiple workers, but ingestion itself is not designed for parallel writers.
A short lease permits recovery from a worker process dying mid-attempt.
"""
from datetime import datetime, timedelta, timezone
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from .connectors import dummyjson
from .database import SessionLocal
from .ingestion import persist_rows
from .models import PipelineExecution, PipelineSchedule

LOG = logging.getLogger(__name__)
CONNECTOR_ID = "dummyjson"
LEASE_SECONDS = 120


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:  # SQLite drops the timezone.
        return value.replace(tzinfo=timezone.utc)
    return value


def iso(value: datetime | None) -> str | None:
    value = aware(value)
    return value.isoformat() if value else None


def serialize_schedule(schedule: PipelineSchedule | None) -> dict:
    if schedule is None:
        return {"configured": False, "connector": CONNECTOR_ID, "enabled": False,
                "interval_minutes": 60, "status": "not_configured", "next_run_at": None,
                "last_attempt_at": None, "last_success_at": None, "last_error": None,
                "consecutive_failures": 0, "last_import_id": None}
    return {"configured": True, "connector": schedule.connector, "enabled": schedule.enabled,
            "interval_minutes": schedule.interval_minutes, "status": schedule.status,
            "next_run_at": iso(schedule.next_run_at),
            "last_attempt_at": iso(schedule.last_attempt_at),
            "last_success_at": iso(schedule.last_success_at),
            "last_error": schedule.last_error,
            "consecutive_failures": schedule.consecutive_failures,
            "last_import_id": schedule.last_import_id}


def serialize_execution(exec_: PipelineExecution) -> dict:
    return {"id": exec_.id, "status": exec_.status,
            "started_at": iso(exec_.started_at), "finished_at": iso(exec_.finished_at),
            "error": exec_.error, "import_id": exec_.import_id}


def update_schedule(db: Session, enabled: bool, interval_minutes: int) -> dict:
    """User opt-in only; no automatic activity immediately after update."""
    schedule = db.scalar(select(PipelineSchedule).where(PipelineSchedule.connector == CONNECTOR_ID))
    if schedule is None:
        schedule = PipelineSchedule(connector=CONNECTOR_ID)
        db.add(schedule)
    if schedule.status == "running":
        raise ValueError("Eine Pipeline wird gerade ausgeführt. Bitte danach ändern.")
    schedule.interval_minutes = interval_minutes
    schedule.enabled = enabled
    schedule.status = "idle"
    schedule.last_error = None
    schedule.consecutive_failures = 0
    schedule.lease_until = None
    schedule.next_run_at = utcnow() + timedelta(minutes=interval_minutes) if enabled else None
    db.commit()
    db.refresh(schedule)
    return serialize_schedule(schedule)


def trigger_now(db: Session) -> dict:
    schedule = db.scalar(select(PipelineSchedule).where(PipelineSchedule.connector == CONNECTOR_ID))
    if schedule is None or not schedule.enabled:
        raise ValueError("Bitte zuerst die automatische Pipeline aktivieren.")
    if schedule.status == "running":
        raise ValueError("Diese Pipeline wird gerade ausgeführt.")
    schedule.next_run_at = utcnow()
    db.commit()
    db.refresh(schedule)
    return serialize_schedule(schedule)


def claim_one(db: Session, now: datetime) -> tuple[int, int] | None:
    """Claim a due run; lock row on PostgreSQL. Transaction is committed before HTTP fetch."""
    schedule = db.scalar(select(PipelineSchedule)
                         .where(PipelineSchedule.connector == CONNECTOR_ID)
                         .with_for_update(skip_locked=True))
    if schedule is None or not schedule.enabled:
        db.commit()
        return None
    if schedule.status == "running":
        if schedule.lease_until is not None and aware(schedule.lease_until) > now:
            db.commit()
            return None
        # The prior process died or timed out. Close that orphaned attempt.
        old = db.scalar(select(PipelineExecution)
                        .where(PipelineExecution.schedule_id == schedule.id,
                               PipelineExecution.status == "running")
                        .order_by(PipelineExecution.id.desc()).limit(1))
        if old is not None:
            old.status = "failed"
            old.error = "Worker-Lease abgelaufen; Wiederholung geplant."
            old.finished_at = now
        schedule.status = "failed"
        schedule.consecutive_failures += 1
        schedule.last_error = "Worker-Lease abgelaufen."
        schedule.next_run_at = now + timedelta(seconds=backoff(schedule.consecutive_failures))
        schedule.lease_until = None
        db.commit()
        return None
    if schedule.next_run_at is None or aware(schedule.next_run_at) > now:
        db.commit()
        return None
    attempt = PipelineExecution(schedule_id=schedule.id, status="running", started_at=now)
    db.add(attempt)
    schedule.status = "running"
    schedule.last_attempt_at = now
    schedule.lease_until = now + timedelta(seconds=LEASE_SECONDS)
    schedule.next_run_at = None
    db.commit()
    return schedule.id, attempt.id


def backoff(failures: int) -> int:
    """30s, 60s, 120s, ... capped at 15 minutes."""
    return min(900, 30 * (2 ** min(max(0, failures - 1), 5)))


def complete_attempt(db: Session, schedule_id: int, attempt_id: int,
                     *, import_id: int | None, error: str | None, now: datetime) -> None:
    schedule = db.get(PipelineSchedule, schedule_id)
    attempt = db.get(PipelineExecution, attempt_id)
    if schedule is None or attempt is None or attempt.status != "running":
        return
    attempt.finished_at = now
    schedule.lease_until = None
    if error:
        attempt.status = "failed"
        attempt.error = error[:400]
        schedule.status = "failed"
        schedule.last_error = error[:400]
        schedule.consecutive_failures += 1
        schedule.next_run_at = now + timedelta(seconds=backoff(schedule.consecutive_failures))
    else:
        attempt.status = "completed"
        attempt.import_id = import_id
        schedule.status = "completed"
        schedule.last_error = None
        schedule.last_success_at = now
        schedule.consecutive_failures = 0
        schedule.last_import_id = import_id
        schedule.next_run_at = (now + timedelta(minutes=schedule.interval_minutes)
                                if schedule.enabled else None)
    db.commit()


def tick(now: datetime | None = None) -> bool:
    """Execute at most one due job; this is called only by the worker process.

    Failures are recorded and rescheduled. A failed HTTP fetch does not create
    an ImportRun, but does create a PipelineExecution with an error message.
    """
    start = now or utcnow()
    with SessionLocal() as db:
        claim = claim_one(db, start)
    if claim is None:
        return False
    schedule_id, attempt_id = claim
    import_id = None
    error = None
    try:
        rows = dummyjson.fetch_products()
        with SessionLocal() as db:
            run = persist_rows(db, source_name=dummyjson.SOURCE_NAME,
                               filename="dummyjson://products?limit=20", rows=rows,
                               normalizer=dummyjson.normalize_product, first_row_number=1)
            import_id = run.id
    except Exception as exc:
        LOG.exception("Pipeline attempt %s failed", attempt_id)
        error = (str(exc) if isinstance(exc, dummyjson.ConnectorError)
                 else "Interner Fehler bei der Verarbeitung; Worker-Logs prüfen.")
    with SessionLocal() as db:
        complete_attempt(db, schedule_id, attempt_id, import_id=import_id,
                         error=error, now=utcnow())
    return True
