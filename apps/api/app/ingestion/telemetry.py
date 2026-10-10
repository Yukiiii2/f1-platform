"""Atomic, retry-safe session imports without modifying the core domain."""

import argparse
import hashlib
import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from app import models
from app.db.session import get_engine, get_session_factory
from app.ingestion.telemetry_contracts import TelemetryBundle, TelemetryProvider
from app.providers.base import ProviderError
from app.providers.openf1 import OpenF1Provider
from app.schemas import telemetry as schemas

logger = logging.getLogger(__name__)
ENTITIES = {
    "lap": (models.Lap, schemas.LapCreate),
    "telemetry": (models.TelemetrySample, schemas.TelemetrySampleCreate),
    "stint": (models.Stint, schemas.StintCreate),
    "pit": (models.PitStop, schemas.PitStopCreate),
    "position": (models.PositionSample, schemas.PositionSampleCreate),
    "interval": (models.IntervalSample, schemas.IntervalSampleCreate),
    "race_control": (models.RaceControlMessage, schemas.RaceControlMessageCreate),
    "weather": (models.WeatherSample, schemas.WeatherSampleCreate),
}


def reconcile(db, provider, session_id, source_session, driver_ids, bundle):
    session = db.get(models.Session, session_id)
    event = db.get(models.Event, session.event_id)
    season = db.get(models.Season, event.season_id)
    circuit = db.get(models.Circuit, event.circuit_id)
    country_aliases = {
        "USA": "United States",
        "UK": "United Kingdom",
        "UAE": "United Arab Emirates",
    }
    country = country_aliases.get(circuit.country, circuit.country)
    if bundle.year != season.year or bundle.session_type != session.type:
        raise ValueError("Source session does not match the domain season/session type")
    if country.casefold() != bundle.country.casefold():
        raise ValueError("Source session does not match the domain country")
    expected_date = session.scheduled_date
    if expected_date is None and session.starts_at is not None:
        expected_date = session.starts_at.astimezone(timezone.utc).date()
    if expected_date is None or bundle.starts_at.date() != expected_date:
        raise ValueError(
            "Source session date cannot be reconciled with the domain schedule"
        )
    if set(bundle.driver_codes) != set(driver_ids):
        raise ValueError("Source drivers do not match the explicitly requested scope")
    identity = db.scalar(
        select(models.ProviderIdentity).where(
            models.ProviderIdentity.provider == provider,
            models.ProviderIdentity.entity_kind == "session",
            models.ProviderIdentity.external_id == str(source_session),
        )
    )
    other = db.scalar(
        select(models.ProviderIdentity).where(
            models.ProviderIdentity.provider == provider,
            models.ProviderIdentity.entity_kind == "session",
            models.ProviderIdentity.domain_id == session_id,
        )
    )
    if identity and identity.domain_id != session_id:
        raise ValueError(
            "Source session is already mapped to a different domain session"
        )
    if other and other.external_id != str(source_session):
        raise ValueError(
            "Domain session is already mapped to a different source session"
        )
    if identity is None:
        db.add(
            models.ProviderIdentity(
                provider=provider,
                entity_kind="session",
                external_id=str(source_session),
                domain_id=session_id,
            )
        )
    for number, driver_id in driver_ids.items():
        driver = db.get(models.Driver, driver_id)
        if driver is None:
            raise ValueError(
                "Explicit driver mapping references a missing domain driver"
            )
        code = bundle.driver_codes[number]
        if code and driver.code and code != driver.code:
            raise ValueError(
                "Explicit driver mapping conflicts with the source driver code"
            )
        mapping = db.scalar(
            select(models.SessionDriverIdentity).where(
                models.SessionDriverIdentity.provider == provider,
                models.SessionDriverIdentity.session_id == session_id,
                models.SessionDriverIdentity.driver_number == number,
            )
        )
        if mapping and mapping.driver_id != driver_id:
            raise ValueError(
                "Session driver number is already mapped to another driver"
            )
        reverse = db.scalar(
            select(models.SessionDriverIdentity).where(
                models.SessionDriverIdentity.provider == provider,
                models.SessionDriverIdentity.session_id == session_id,
                models.SessionDriverIdentity.driver_id == driver_id,
            )
        )
        if reverse and reverse.driver_number != number:
            raise ValueError(
                "Domain driver already has another number in this source session"
            )
        if mapping is None:
            db.add(
                models.SessionDriverIdentity(
                    provider=provider,
                    session_id=session_id,
                    driver_id=driver_id,
                    driver_number=number,
                )
            )
    db.flush()


def persist_session_bundle(
    db: DbSession,
    provider: str,
    session_id: UUID,
    source_session: int,
    driver_ids: dict[int, UUID],
    bundle: TelemetryBundle,
    *,
    changed_only: bool = False,
) -> dict[str, int]:
    observed_at = bundle.observation_started_at or bundle.fetched_at
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("Telemetry observation time must be timezone-aware")
    observed_at = observed_at.astimezone(timezone.utc)
    if db.get_bind().dialect.name == "postgresql":
        lock = int.from_bytes(
            hashlib.sha256(f"f1-import:{provider}".encode()).digest()[:8], signed=True
        )
        db.execute(select(func.pg_advisory_xact_lock(lock)))
    reconcile(db, provider, session_id, source_session, driver_ids, bundle)
    grouped = defaultdict(list)
    for record in bundle.records:
        if record.kind not in ENTITIES or len(record.source_key) > 200:
            raise ValueError("Invalid normalized source identity")
        grouped[record.kind].append(record)
    counts = {kind: 0 for kind in ENTITIES}
    for kind, records in grouped.items():
        model, schema = ENTITIES[kind]
        existing = (
            {}
            if changed_only
            else {
                row.source_key: row
                for row in db.scalars(
                    select(model).where(
                        model.provider == provider,
                        model.session_id == session_id,
                    )
                )
            }
        )
        source = models.TelemetrySourceRecord
        revisions = (
            {}
            if changed_only
            else {
                (key, checksum): identifier
                for key, checksum, identifier in db.execute(
                    select(source.source_key, source.checksum, source.id).where(
                        source.provider == provider,
                        source.session_id == session_id,
                        source.kind == kind,
                    )
                )
            }
        )
        seen = set()
        for start in range(0, len(records), 500):
            if changed_only:
                keys = [record.source_key for record in records[start : start + 500]]
                existing.update(
                    {
                        row.source_key: row
                        for row in db.scalars(
                            select(model).where(
                                model.provider == provider,
                                model.session_id == session_id,
                                model.source_key.in_(keys),
                            )
                        )
                    }
                )
                revisions.update(
                    {
                        (key, checksum): identifier
                        for key, checksum, identifier in db.execute(
                            select(source.source_key, source.checksum, source.id).where(
                                source.provider == provider,
                                source.session_id == session_id,
                                source.kind == kind,
                                source.source_key.in_(keys),
                            )
                        )
                    }
                )
            prepared = []
            for record in records[start : start + 500]:
                if record.source_key in seen:
                    raise ValueError("Duplicate normalized record identity")
                seen.add(record.source_key)
                data = {
                    **record.attributes,
                    "session_id": session_id,
                    "provider": provider,
                }
                if record.driver_number is not None:
                    if record.driver_number not in driver_ids:
                        raise ValueError("Unmapped source driver")
                    data["driver_id"] = driver_ids[record.driver_number]
                validated = schema.model_validate(data)
                raw = json.dumps(
                    record.source_payload,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                checksum = hashlib.sha256(raw.encode()).hexdigest()
                revision = revisions.get((record.source_key, checksum))
                if revision is None:
                    revision = uuid4()
                    db.add(
                        source(
                            id=revision,
                            provider=provider,
                            session_id=session_id,
                            kind=kind,
                            source_key=record.source_key,
                            checksum=checksum,
                            payload=record.source_payload,
                            fetched_at=bundle.fetched_at,
                        )
                    )
                    revisions[record.source_key, checksum] = revision
                prepared.append((record.source_key, revision, validated.model_dump()))
            # Batch raw inserts before their normalized foreign-key references.
            db.flush()
            for key, revision, data in prepared:
                data.update(
                    source_record_id=revision,
                    source_key=key,
                    source_observed_at=observed_at,
                )
                row = existing.get(key)
                if row is None:
                    row = model(**data)
                    db.add(row)
                    existing[key] = row
                else:
                    current = row.source_observed_at
                    if current is not None:
                        # SQLite fixture storage drops timezone offsets; PostgreSQL
                        # keeps these timestamptz columns aware in production.
                        current = (
                            current.replace(tzinfo=timezone.utc)
                            if current.tzinfo is None
                            else current
                        )
                        if observed_at <= current:
                            if not changed_only:
                                counts[kind] += 1
                            continue
                    if changed_only and row.source_record_id == revision:
                        # A repeated payload is not re-imported. Advance only its
                        # ordering watermark: otherwise a delayed A->B->A import
                        # could overwrite this newer observation with stale B.
                        row.source_observed_at = observed_at
                        continue
                    for field, value in data.items():
                        setattr(row, field, value)
                counts[kind] += 1
            db.flush()
    return counts


def run_telemetry_import(
    provider: TelemetryProvider,
    factory: sessionmaker[DbSession],
    session_id: UUID,
    source_session: int,
    driver_ids: dict[int, UUID],
    *,
    live_job_id: UUID | None = None,
    now: datetime | None = None,
) -> UUID:
    if source_session < 1 or not driver_ids or any(number < 1 for number in driver_ids):
        raise ValueError(
            "Explicit source session and positive driver numbers are required"
        )
    if len(set(driver_ids.values())) != len(driver_ids):
        raise ValueError(
            "Each selected source driver must map to a different domain driver"
        )
    with factory.begin() as db:
        session = db.get(models.Session, session_id)
        if session is None:
            raise ValueError("Domain session must be imported before telemetry")
        event = db.get(models.Event, session.event_id)
        run = models.ImportRun(
            provider=provider.name,
            session_id=session_id,
            season_id=event.season_id,
            external_identifier=f"{source_session}:"
            + ",".join(map(str, sorted(driver_ids))),
            started_at=datetime.now(timezone.utc),
        )
        db.add(run)
        db.flush()
        run_id = run.id
    bundle, attempt = None, 1
    try:
        if live_job_id is None:
            bundle = provider.fetch_session(source_session, sorted(driver_ids))
        else:
            with factory() as db:
                job = db.get(models.SessionUpdateJob, live_job_id)
                if (
                    job is None
                    or job.session_id != session_id
                    or job.source_session != source_session
                ):
                    raise ValueError("Live job scope mismatch")
                cursor = job.live_cursor
            bundle = provider.fetch_incremental(
                source_session, sorted(driver_ids), cursor, now
            )
        while True:
            try:
                with factory.begin() as db:
                    counts = persist_session_bundle(
                        db,
                        provider.name,
                        session_id,
                        source_session,
                        driver_ids,
                        bundle,
                        changed_only=live_job_id is not None,
                    )
                    run = db.get(models.ImportRun, run_id)
                    run.status = "succeeded"
                    run.row_counts = counts
                    run.fetched_at = bundle.fetched_at
                    run.source_updated_at = bundle.source_updated_at
                    run.finished_at = datetime.now(timezone.utc)
                    run.attempt_count = attempt
                    if live_job_id is not None:
                        job = db.get(models.SessionUpdateJob, live_job_id)
                        if bundle.cursor is None:
                            raise ValueError("Live refresh requires a validated cursor")
                        # Same transaction as raw revisions and normalized rows.
                        job.live_cursor = bundle.cursor
                        job.live_updated_at = bundle.fetched_at
                        job.data_status = "provisional"
                        job.telemetry_import_id = run_id
                        job.row_counts = counts
                        session = db.get(models.Session, session_id)
                        session.status = "in_progress"
                logger.info(
                    "Telemetry import %s succeeded: provider=%s counts=%s",
                    run_id,
                    provider.name,
                    counts,
                )
                return run_id
            except DBAPIError as error:
                if attempt >= 3 or getattr(error.orig, "sqlstate", None) not in {
                    "40001",
                    "40P01",
                    "23505",
                }:
                    raise
                time.sleep(2 ** (attempt - 1))
                attempt += 1
    except Exception as error:
        with factory.begin() as db:
            run = db.get(models.ImportRun, run_id)
            run.status = "failed"
            run.finished_at = datetime.now(timezone.utc)
            run.attempt_count = attempt
            detail = (
                str(error)
                if isinstance(error, ProviderError)
                else "Telemetry validation or persistence failed"
            )
            run.failure_details = f"{type(error).__name__}: {detail}"[:500]
            if bundle is not None:
                run.fetched_at = bundle.fetched_at
                run.source_updated_at = bundle.source_updated_at
        logger.error("Telemetry import %s failed (%s)", run_id, type(error).__name__)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import historical OpenF1 session data"
    )
    parser.add_argument(
        "--session", type=UUID, required=True, help="Existing application session UUID"
    )
    parser.add_argument(
        "--source-session", type=int, required=True, help="Explicit OpenF1 session key"
    )
    parser.add_argument(
        "--driver",
        action="append",
        required=True,
        metavar="NUMBER=UUID",
        help="Session car number to application driver UUID; repeat for each driver",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        driver_ids = {}
        for mapping in args.driver:
            number, identifier = mapping.split("=", 1)
            number = int(number)
            if number in driver_ids:
                raise ValueError("Duplicate driver number")
            driver_ids[number] = UUID(identifier)
        with OpenF1Provider() as provider:
            run_id = run_telemetry_import(
                provider,
                get_session_factory(),
                args.session,
                args.source_session,
                driver_ids,
            )
        print(f"Telemetry import succeeded: {run_id}")
        return 0
    except Exception as error:
        detail = (
            str(error)
            if isinstance(error, ProviderError)
            else "Check mappings, migrations and import_runs."
        )
        print(f"Telemetry import failed ({type(error).__name__}): {detail}")
        return 1
    finally:
        if get_engine.cache_info().currsize:
            get_engine().dispose()


if __name__ == "__main__":
    raise SystemExit(main())
