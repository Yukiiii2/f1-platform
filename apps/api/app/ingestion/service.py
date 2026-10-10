import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from app import models, schemas
from app.ingestion.contracts import ImportBundle
from app.providers.base import F1Provider, ProviderError

logger = logging.getLogger(__name__)

# Dependency order and natural keys reuse Phase 1's existing constraints.
ENTITIES = {
    "season": (models.Season, schemas.SeasonCreate, ("year",)),
    "circuit": (models.Circuit, schemas.CircuitCreate, ()),
    "driver": (models.Driver, schemas.DriverCreate, ()),
    "team": (models.Team, schemas.TeamCreate, ()),
    "event": (models.Event, schemas.EventCreate, ("season_id", "round")),
    "session": (models.Session, schemas.SessionCreate, ("event_id", "type")),
    "result": (models.Result, schemas.ResultCreate, ("session_id", "driver_id")),
    "driver_standing": (
        models.DriverStanding,
        schemas.DriverStandingCreate,
        ("event_id", "driver_id"),
    ),
    "constructor_standing": (
        models.ConstructorStanding,
        schemas.ConstructorStandingCreate,
        ("event_id", "team_id"),
    ),
}


def persist_bundle(
    db: DbSession, provider: str, bundle: ImportBundle
) -> dict[str, int]:
    if db.get_bind().dialect.name == "postgresql":
        # Serialize this provider across seasons: drivers and circuits are shared.
        lock = int.from_bytes(
            hashlib.sha256(f"f1-import:{provider}".encode()).digest()[:8], signed=True
        )
        db.execute(select(func.pg_advisory_xact_lock(lock)))
    if bundle.fetched_at.tzinfo is None or bundle.fetched_at.utcoffset() is None:
        raise ValueError("An aware source observation is required")
    if bundle.raw_payload is not None:
        season_record = next(
            record for record in bundle.records if record.kind == "season"
        )
        digest = hashlib.sha256(
            json.dumps(
                bundle.raw_payload, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        # Season + represented rounds scopes whole-season and independent round imports.
        scope = (
            season_record.external_id
            + ":"
            + ",".join(
                sorted(
                    record.external_id.split(":")[-1]
                    for record in bundle.records
                    if record.kind == "event"
                )
            )
        )
        revision = db.scalar(
            select(models.CoreSourceRevision).where(
                models.CoreSourceRevision.provider == provider,
                models.CoreSourceRevision.scope == scope,
                models.CoreSourceRevision.content_hash == digest,
            )
        )
        if revision is None:
            db.add(
                models.CoreSourceRevision(
                    provider=provider,
                    scope=scope,
                    content_hash=digest,
                    payload=bundle.raw_payload,
                    observed_at=bundle.fetched_at,
                )
            )
    counts = {}
    resolved = {}
    order = {kind: index for index, kind in enumerate(ENTITIES)}
    for record in sorted(bundle.records, key=lambda item: order[item.kind]):
        model, schema, natural_keys = ENTITIES[record.kind]
        data = dict(record.attributes)
        for field, reference in record.references.items():
            if reference not in resolved:
                identity = db.scalar(
                    select(models.ProviderIdentity).where(
                        models.ProviderIdentity.provider == provider,
                        models.ProviderIdentity.entity_kind == reference[0],
                        models.ProviderIdentity.external_id == reference[1],
                    )
                )
                if identity is None:
                    raise ValueError("Unresolved source identity")
                resolved[reference] = identity.domain_id
            data[field] = resolved[reference]
        validated = schema.model_validate(data)
        identity = db.scalar(
            select(models.ProviderIdentity).where(
                models.ProviderIdentity.provider == provider,
                models.ProviderIdentity.entity_kind == record.kind,
                models.ProviderIdentity.external_id == record.external_id,
            )
        )
        row = db.get(model, identity.domain_id) if identity else None
        state = db.get(models.CoreSourceState, identity.id) if identity else None
        if state is not None:
            last = state.observed_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if last > bundle.fetched_at:
                resolved[record.kind, record.external_id] = identity.domain_id
                continue
        if identity and row is None:
            raise ValueError("Provider identity references a missing domain row")
        if row is None and natural_keys:
            row = db.scalar(
                select(model).where(
                    *(
                        getattr(model, key) == getattr(validated, key)
                        for key in natural_keys
                    )
                )
            )
        if row is None:
            row = model(**validated.model_dump())
            db.add(row)
            db.flush()
        else:
            for field, value in validated.model_dump(exclude_unset=True).items():
                setattr(row, field, value)
        if identity is None:
            identity = models.ProviderIdentity(
                provider=provider,
                entity_kind=record.kind,
                external_id=record.external_id,
                domain_id=row.id,
            )
            db.add(identity)
            db.flush()
        if state is None:
            db.add(
                models.CoreSourceState(
                    identity_id=identity.id, observed_at=bundle.fetched_at
                )
            )
        else:
            state.observed_at = bundle.fetched_at
        resolved[record.kind, record.external_id] = row.id
        counts[record.kind] = counts.get(record.kind, 0) + 1
        db.flush()
    return counts


def run_import(
    provider: F1Provider,
    factory: sessionmaker[DbSession],
    year: int,
    round_number: int | None = None,
) -> UUID:
    if year < 1950 or (round_number is not None and round_number < 1):
        raise ValueError("Invalid season or round")
    started = datetime.now(timezone.utc)
    with factory.begin() as db:
        run = models.ImportRun(
            provider=provider.name,
            external_identifier=f"{year}:{round_number or 'all'}",
            started_at=started,
        )
        db.add(run)
        db.flush()
        run_id = run.id
    attempt = 1
    bundle = None
    try:
        # Upstream IO occurs outside the transaction that changes domain data.
        bundle = provider.fetch(year, round_number)
        while True:
            try:
                with factory.begin() as db:
                    counts = persist_bundle(db, provider.name, bundle)
                    identity = db.scalar(
                        select(models.ProviderIdentity).where(
                            models.ProviderIdentity.provider == provider.name,
                            models.ProviderIdentity.entity_kind == "season",
                            models.ProviderIdentity.external_id == str(year),
                        )
                    )
                    run = db.get(models.ImportRun, run_id)
                    run.status = "succeeded"
                    run.season_id = identity.domain_id
                    run.fetched_at = bundle.fetched_at
                    run.source_updated_at = bundle.source_updated_at
                    run.finished_at = datetime.now(timezone.utc)
                    run.attempt_count = attempt
                    run.row_counts = counts
                break
            except DBAPIError as error:
                state = getattr(error.orig, "sqlstate", None)
                if attempt >= 3 or state not in {"40001", "40P01", "23505"}:
                    raise
                time.sleep(2 ** (attempt - 1))
                attempt += 1
        logger.info(
            "Core import %s succeeded: provider=%s counts=%s",
            run_id,
            provider.name,
            counts,
        )
        return run_id
    except Exception as error:
        # Never persist raw HTTP/DB exceptions: they may include credentials.
        detail = (
            str(error)
            if isinstance(error, ProviderError)
            else "Core validation or persistence failed"
        )
        with factory.begin() as db:
            run = db.get(models.ImportRun, run_id)
            run.status = "failed"
            run.finished_at = datetime.now(timezone.utc)
            run.attempt_count = attempt
            run.failure_details = f"{type(error).__name__}: {detail}"[:500]
            if bundle:
                run.fetched_at = bundle.fetched_at
                run.source_updated_at = bundle.source_updated_at
        logger.error("Core import %s failed (%s)", run_id, type(error).__name__)
        raise
