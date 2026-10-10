"""Post-session finalization using the existing normalized import/services boundary."""

import logging
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select

from app import models
from app.domain.enums import SessionStatus, SessionType
from app.ingestion.service import run_import
from app.ingestion.telemetry import run_telemetry_import
from app.services.strategy import session_strategy

logger = logging.getLogger(__name__)
POLL_SECONDS = 1800
MAX_FAILURES = 3
LOCK_KEY = 701101943


def utc(value):
    # SQLite strips tzinfo in isolated tests; persisted job timestamps are UTC.
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def clock(value=None):
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("An aware clock is required")
    return value.astimezone(timezone.utc)


@contextmanager
def worker_lock(engine):
    """One worker owns the pipeline. Connection loss/crash releases the PG lock."""
    if engine.dialect.name != "postgresql":
        # Only isolated tests use SQLite; repository runtime requires PostgreSQL.
        yield True
        return
    with engine.connect() as connection:
        acquired = bool(connection.scalar(select(func.pg_try_advisory_lock(LOCK_KEY))))
        connection.commit()
        try:
            yield acquired
        finally:
            if acquired:
                connection.execute(select(func.pg_advisory_unlock(LOCK_KEY)))
                connection.commit()


def register_session(
    factory, session_id, source_session, driver_ids, *, now=None, live=False
):
    now = clock(now)
    if source_session < 1 or not driver_ids or any(number < 1 for number in driver_ids):
        raise ValueError(
            "Explicit positive source session and driver mappings are required"
        )
    if live and len(driver_ids) > 32:
        raise ValueError("Live scope supports at most 32 drivers")
    if len(set(driver_ids.values())) != len(driver_ids):
        raise ValueError("Driver mappings must be distinct")
    scope = {
        str(number): str(identifier)
        for number, identifier in sorted(driver_ids.items())
    }
    with factory.begin() as db:
        session = db.get(models.Session, session_id)
        if session is None or any(
            db.get(models.Driver, identifier) is None
            for identifier in driver_ids.values()
        ):
            raise ValueError("Import domain session/drivers first")
        if live and (
            session.status in {SessionStatus.COMPLETED, SessionStatus.CANCELLED}
            or (session.scheduled_date and session.scheduled_date < now.date())
        ):
            raise ValueError(
                "Historical completed sessions cannot enter near-live polling"
            )
        job = db.scalar(
            select(models.SessionUpdateJob).where(
                models.SessionUpdateJob.session_id == session_id
            )
        )
        if job:
            if job.source_session != source_session or job.driver_ids != scope:
                raise ValueError("Registered source scope cannot be replaced")
            if live and job.status not in {"succeeded", "cancelled"}:
                job.live_enabled = True
                job.next_attempt_at = now
            return job.id
        source_job = db.scalar(
            select(models.SessionUpdateJob).where(
                models.SessionUpdateJob.source_session == source_session
            )
        )
        if source_job:
            raise ValueError("Source session is registered for another domain session")
        identity = db.scalar(
            select(models.ProviderIdentity).where(
                models.ProviderIdentity.provider == "openf1",
                models.ProviderIdentity.entity_kind == "session",
                models.ProviderIdentity.external_id == str(source_session),
            )
        )
        if identity and identity.domain_id != session_id:
            raise ValueError("Source session is mapped to another domain session")
        job = models.SessionUpdateJob(
            session_id=session_id,
            source_session=source_session,
            driver_ids=scope,
            next_attempt_at=now,
            live_enabled=live,
        )
        db.add(job)
        db.flush()
        return job.id


def retry_session(factory, session_id, *, now=None):
    with factory.begin() as db:
        job = db.scalar(
            select(models.SessionUpdateJob)
            .where(models.SessionUpdateJob.session_id == session_id)
            .with_for_update()
        )
        if job is None or job.status == "running":
            raise ValueError("No idle registered job to retry")
        job.status, job.stage = (
            "pending",
            "live"
            if job.live_enabled and job.stage in {"live", "waiting"}
            else "completion",
        )
        job.consecutive_failures = 0
        job.live_suspended = False
        job.next_attempt_at = clock(now)
        job.failure_details = None


def fresh_reads(scope):
    """No current data cache: API reads DB, Next fetches with cache=no-store."""
    return {"mode": "not_cached"}


def stage(factory, identifier, name, **values):
    with factory.begin() as db:
        job = db.get(models.SessionUpdateJob, identifier)
        job.stage = name
        for field, value in values.items():
            setattr(job, field, value)
    logger.info("Session update job=%s stage=%s", identifier, name)


def finalize(factory, job, core, telemetry, now, interval, invalidate):
    started = time.monotonic()
    identifier = job.id
    try:
        stage(
            factory,
            identifier,
            "core",
            status="running",
            started_at=now,
            attempt_count=job.attempt_count + 1,
            failure_details=None,
        )
        with factory() as db:
            session = db.get(models.Session, job.session_id)
            event = db.get(models.Event, session.event_id)
            year = db.get(models.Season, event.season_id).year
            scheduled = session.starts_at or (
                datetime.combine(
                    session.scheduled_date, datetime.min.time(), timezone.utc
                )
                if session.scheduled_date
                else None
            )
            if scheduled and utc(scheduled) > now + timedelta(days=1):
                stage(
                    factory,
                    identifier,
                    "waiting",
                    status="pending",
                    next_attempt_at=utc(scheduled) - timedelta(days=1),
                )
                return
            round_number = event.round
        # Refresh schedules/results/available standing snapshots once per event/tick.
        key = year, round_number
        if key not in core[1]:
            try:
                core[1][key] = run_import(core[0], factory, year, round_number)
            except Exception as error:
                core[1][key] = error
        if isinstance(core[1][key], Exception):
            raise core[1][key]
        stage(factory, identifier, "completion", core_import_id=core[1][key])
        proof = telemetry.inspect_session(job.source_session, now)
        with factory() as db:
            session = db.get(models.Session, job.session_id)
            event = db.get(models.Event, session.event_id)
            country = db.get(models.Circuit, event.circuit_id).country
            country = {
                "USA": "United States",
                "UK": "United Kingdom",
                "UAE": "United Arab Emirates",
            }.get(country, country)
            date = session.scheduled_date or (
                utc(session.starts_at).date() if session.starts_at else None
            )
            if (
                proof.year != year
                or proof.session_type != session.type
                or proof.country.casefold() != country.casefold()
                or (proof.starts_at is not None and date != proof.starts_at.date())
            ):
                raise ValueError(
                    "Source session does not match the registered domain scope"
                )
            published = (
                session.status == SessionStatus.COMPLETED
                and db.scalar(
                    select(models.Result.id)
                    .where(models.Result.session_id == session.id)
                    .limit(1)
                )
                is not None
            )
            cancelled = proof.cancelled or session.status == SessionStatus.CANCELLED
            needs_results = session.type in {
                SessionType.RACE,
                SessionType.SPRINT,
                SessionType.QUALIFYING,
            }
            needs_standings = session.type in {SessionType.RACE, SessionType.SPRINT}
            standings = all(
                db.scalar(select(model.id).where(model.event_id == event.id).limit(1))
                is not None
                for model in (models.DriverStanding, models.ConstructorStanding)
            )
            core_ready = (not needs_results or published) and (
                not needs_standings or standings
            )
            scope = {
                "session_id": str(session.id),
                "event_id": str(event.id),
                "season": year,
                "driver_ids": sorted(set(job.driver_ids.values())),
            }
        if cancelled:
            stage(
                factory,
                identifier,
                "cancelled",
                status="cancelled",
                finished_at=now,
                failure_details="source_cancelled",
            )
            return
        wait = (
            max(interval, 21600)
            if proof.ends_at + timedelta(days=1) < now
            else interval
        )
        if not proof.settled or not (published or proof.completed):
            stage(
                factory,
                identifier,
                "waiting",
                status="pending",
                consecutive_failures=0,
                next_attempt_at=now + timedelta(seconds=wait),
                failure_details="awaiting_completion_evidence",
            )
            return
        if job.stage == "results" and not core_ready:
            stage(
                factory,
                identifier,
                "results",
                status="pending",
                consecutive_failures=0,
                next_attempt_at=now + timedelta(seconds=wait),
                failure_details="awaiting_results_or_standings",
            )
            return
        evidence = {
            "provider": "jolpica" if published else "openf1",
            "kind": "published_results" if published else proof.evidence_kind,
            "observed_at": (now if published else proof.observed_at).isoformat(),
            "source_session": job.source_session,
            "checked_at": now.isoformat(),
        }
        stage(
            factory,
            identifier,
            "telemetry",
            confirmed_at=now,
            completion_evidence=evidence,
        )
        run_id = run_telemetry_import(
            telemetry,
            factory,
            job.session_id,
            job.source_session,
            {int(number): UUID(driver) for number, driver in job.driver_ids.items()},
        )
        stage(factory, identifier, "derived", telemetry_import_id=run_id)
        with factory.begin() as db:
            session = db.get(models.Session, job.session_id)
            run = db.get(models.ImportRun, run_id)
            if run.status != "succeeded":
                raise ValueError("Telemetry validation has not succeeded")
            # Preserve existing pace exclusions, unknown ages, and source boundaries.
            derived = session_strategy(db, session, provider="openf1").model_dump(
                mode="json"
            )
            stored = db.get(models.SessionUpdateJob, identifier)
            stored.row_counts = run.row_counts
            stored.derived_summary = {"calculation_version": "strategy-v1", **derived}
            # Completion fact comes from the recorded provider evidence, not the clock.
            session.status = SessionStatus.COMPLETED
            session.ends_at = proof.ends_at
        stage(factory, identifier, "cache")
        cache_state = invalidate(scope)
        if not core_ready:
            stage(
                factory,
                identifier,
                "results",
                status="pending",
                consecutive_failures=0,
                cache_state=cache_state,
                next_attempt_at=now + timedelta(seconds=wait),
                failure_details="awaiting_results_or_standings",
            )
            return
        stage(
            factory,
            identifier,
            "done",
            status="succeeded",
            consecutive_failures=0,
            finished_at=clock(),
            cache_state=cache_state,
            failure_details=None,
            data_status="finalized",
            live_active=False,
        )
        logger.info(
            "Session update job=%s status=succeeded elapsed_seconds=%.1f counts=%s",
            identifier,
            time.monotonic() - started,
            run.row_counts,
        )
    except Exception as error:
        # Only fixed classifications: never source error strings, URLs, keys or prompts.
        failures = job.consecutive_failures + 1
        reason = (
            "validation_failed"
            if isinstance(error, ValueError)
            else "dependency_failed"
        )
        with factory() as db:
            failed_stage = db.get(models.SessionUpdateJob, identifier).stage
        stage(
            factory,
            identifier,
            "failed",
            status="failed" if failures >= MAX_FAILURES else "retry",
            consecutive_failures=failures,
            failure_details=f"{failed_stage}:{reason}",
            finished_at=clock(),
            next_attempt_at=now + timedelta(seconds=interval * 2 ** (failures - 1)),
        )
        logger.warning(
            "Session update job=%s status=%s failures=%d "
            "category=%s elapsed_seconds=%.1f",
            identifier,
            "failed" if failures >= MAX_FAILURES else "retry",
            failures,
            reason,
            time.monotonic() - started,
        )


def refresh_live(factory, job, telemetry, now, interval):
    """Return False only when the historical finalization path should take over."""
    started = time.monotonic()
    with factory() as db:
        session = db.get(models.Session, job.session_id)
        event = db.get(models.Event, session.event_id)
        scheduled = session.starts_at or (
            datetime.combine(session.scheduled_date, datetime.min.time(), timezone.utc)
            if session.scheduled_date
            else None
        )
        if (
            job.stage
            in {
                "core",
                "completion",
                "telemetry",
                "derived",
                "cache",
                "results",
                "failed",
            }
            and job.attempt_count > 0
        ):
            return False
        # Old/completed jobs use the original public historical API without live auth.
        if session.status == SessionStatus.COMPLETED or (
            scheduled and utc(scheduled) + timedelta(days=1) <= now
        ):
            return False
        if scheduled and utc(scheduled) - timedelta(minutes=30) > now:
            stage(
                factory,
                job.id,
                "waiting",
                status="pending",
                next_attempt_at=utc(scheduled) - timedelta(minutes=30),
            )
            return True
        year = db.get(models.Season, event.season_id).year
        country = db.get(models.Circuit, event.circuit_id).country
        country = {
            "USA": "United States",
            "UK": "United Kingdom",
            "UAE": "United Arab Emirates",
        }.get(country, country)
        expected_date = session.scheduled_date or (
            utc(session.starts_at).date() if session.starts_at else None
        )
    if job.live_suspended:
        # Last source end is only a handoff hint; historical completion still
        # requires its original evidence checks. Unknown ends use a bounded window.
        ready_at = (
            utc(job.live_ends_at) + timedelta(minutes=30)
            if job.live_ends_at
            else utc(scheduled) + timedelta(hours=6)
            if scheduled
            else now
        )
        if now >= ready_at:
            return False
        stage(
            factory,
            job.id,
            "waiting",
            status="pending",
            next_attempt_at=min(ready_at, now + timedelta(minutes=30)),
        )
        return True
    try:
        stage(
            factory,
            job.id,
            "live",
            status="running",
            started_at=now,
            attempt_count=job.attempt_count + 1,
            failure_details=None,
        )
        proof = telemetry.inspect_live_session(
            job.source_session, now, sorted(int(number) for number in job.driver_ids)
        )
        if (
            proof.year != year
            or proof.session_type != session.type
            or proof.country.casefold() != country.casefold()
            or (proof.starts_at is None and not proof.cancelled)
            or (proof.starts_at is not None and proof.starts_at.date() != expected_date)
        ):
            raise ValueError("Source live session does not match registered scope")
        stage(
            factory,
            job.id,
            "live",
            live_ends_at=proof.ends_at,
            live_active=proof.active,
        )
        if proof.cancelled:
            # Terminal job and public state must commit together, preserving the
            # provisional observations already imported before cancellation.
            with factory.begin() as db:
                db.get(models.Session, job.session_id).status = SessionStatus.CANCELLED
                stored = db.get(models.SessionUpdateJob, job.id)
                stored.stage, stored.status = "cancelled", "cancelled"
                stored.finished_at = now
                stored.failure_details = "source_cancelled"
                stored.live_active, stored.live_suspended = False, False
                stored.consecutive_failures = 0
            logger.info("Session update job=%s stage=cancelled", job.id)
            return True
        if proof.settled:
            return False
        if proof.active:
            run_telemetry_import(
                telemetry,
                factory,
                job.session_id,
                job.source_session,
                {
                    int(number): UUID(driver)
                    for number, driver in job.driver_ids.items()
                },
                live_job_id=job.id,
                now=now,
            )
        # Poll interval starts after IO, preventing catch-up bursts and tight loops.
        stage(
            factory,
            job.id,
            "live" if proof.active else "waiting",
            status="pending",
            consecutive_failures=0,
            failure_details=None,
            next_attempt_at=now
            + timedelta(seconds=interval + time.monotonic() - started),
        )
    except Exception as error:
        failures = job.consecutive_failures + 1
        suspended = failures >= MAX_FAILURES
        category = (
            "validation_failed"
            if isinstance(error, ValueError)
            else "dependency_failed"
        )
        stage(
            factory,
            job.id,
            "waiting" if suspended else "live",
            status="pending" if suspended else "retry",
            live_suspended=suspended,
            live_active=False,
            consecutive_failures=failures,
            failure_details=f"live:{category}",
            next_attempt_at=now
            + timedelta(
                seconds=(1800 if suspended else interval * 2 ** (failures - 1))
                + time.monotonic()
                - started
            ),
        )
        logger.warning(
            "Live update job=%s failures=%d suspended=%s category=%s",
            job.id,
            failures,
            suspended,
            category,
        )
    return True


def run_once(
    factory,
    core,
    telemetry,
    *,
    now=None,
    interval=POLL_SECONDS,
    live_interval=60,
    invalidate=None,
):
    now = clock(now)
    if interval < 900:
        raise ValueError("Post-session polling interval must be at least 900 seconds")
    if not 60 <= live_interval <= 300:
        raise ValueError("Live polling interval must be between 60 and 300 seconds")
    engine = factory.kw["bind"]
    with worker_lock(engine) as acquired:
        if not acquired:
            logger.info("Session updates deferred: another worker owns the pipeline")
            return 0
        with factory() as db:
            jobs = list(
                db.scalars(
                    select(models.SessionUpdateJob)
                    .where(
                        models.SessionUpdateJob.status.in_(
                            ["pending", "retry", "running"]
                        ),
                        models.SessionUpdateJob.next_attempt_at <= now,
                    )
                    .order_by(
                        models.SessionUpdateJob.next_attempt_at,
                        models.SessionUpdateJob.id,
                    )
                )
            )
        core_context = core, {}
        for job in jobs:
            if job.live_enabled and refresh_live(
                factory, job, telemetry, now, live_interval
            ):
                continue
            if job.live_enabled and job.stage in {"live", "waiting"}:
                # Live and authoritative historical attempts have separate budgets.
                job.consecutive_failures = 0
                stage(
                    factory,
                    job.id,
                    "completion",
                    consecutive_failures=0,
                    live_active=False,
                )
            finalize(
                factory,
                job,
                core_context,
                telemetry,
                now,
                interval,
                invalidate or fresh_reads,
            )
        return len(jobs)
