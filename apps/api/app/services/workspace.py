"""Validate references and batch page resolution without copying analysis data."""

from datetime import timezone
from urllib.parse import urlencode

from sqlalchemy import func, select

from app import models
from app.schemas.workspace import CollectionRead, ReferenceRead
from app.services.comparisons import read_many as comparisons_read

MODELS = {
    "comparison": models.SavedComparison,
    "event": models.Event,
    "driver": models.Driver,
    "session": models.Session,
}
COLUMNS = {
    "comparison": "comparison_id",
    "event": "event_id",
    "driver": "driver_id",
    "session": "session_id",
}


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def collections_read(db, rows):
    counts = (
        dict(
            db.execute(
                select(models.CollectionItem.collection_id, func.count())
                .where(models.CollectionItem.collection_id.in_([r.id for r in rows]))
                .group_by(models.CollectionItem.collection_id)
            ).all()
        )
        if rows
        else {}
    )
    return [
        CollectionRead(
            id=r.id,
            title=r.title,
            description=r.description,
            created_at=aware(r.created_at),
            updated_at=aware(r.updated_at),
            item_count=counts.get(r.id, 0),
        )
        for r in rows
    ]


def validate_reference(db, row, request, owner):
    season = db.scalar(
        select(models.Season).where(models.Season.year == request.season)
    )
    target = db.get(MODELS[request.reference_type], request.reference_id)
    valid = season is not None and target is not None
    if valid and request.reference_type == "comparison":
        valid = target.user_id == owner and target.season == request.season
    elif valid and request.reference_type == "event":
        valid = target.season_id == season.id
    elif valid and request.reference_type == "session":
        event = db.get(models.Event, target.event_id)
        valid = event is not None and event.season_id == season.id
    if not valid:
        return False
    row.reference_id = request.reference_id
    row.reference_type = request.reference_type
    row.season = request.season
    row.season_id = season.id
    setattr(row, COLUMNS[request.reference_type], target.id)
    return True


def references_read(db, rows, owner):
    refs = {}
    for kind, model in MODELS.items():
        ids = {getattr(r, COLUMNS[kind]) for r in rows if r.reference_type == kind} - {
            None
        }
        query = select(model).where(model.id.in_(ids))
        if kind == "comparison":
            query = query.where(model.user_id == owner)
        refs[kind] = {r.id: r for r in db.scalars(query)} if ids else {}
    event_ids = {s.event_id for s in refs["session"].values()}
    refs["events"] = (
        {
            r.id: r
            for r in db.scalars(
                select(models.Event).where(models.Event.id.in_(event_ids))
            )
        }
        if event_ids
        else {}
    )
    season_ids = {r.season_id for r in rows} - {None}
    seasons = (
        {
            r.id: r
            for r in db.scalars(
                select(models.Season).where(models.Season.id.in_(season_ids))
            )
        }
        if season_ids
        else {}
    )
    comparisons = {
        r.id: r for r in comparisons_read(db, list(refs["comparison"].values()))
    }
    result = []
    for row in rows:
        target = refs[row.reference_type].get(getattr(row, COLUMNS[row.reference_type]))
        season = seasons.get(row.season_id)
        valid = target is not None and season is not None and season.year == row.season
        label, url, notices, availability = (
            "Reference unavailable",
            None,
            [],
            "unavailable",
        )
        if valid and target.id != row.reference_id:
            valid = False
        if valid and row.reference_type == "event":
            valid = target.season_id == season.id
            label = target.name
            url = f"/races/{target.id}?{urlencode({'season': row.season})}"
        elif valid and row.reference_type == "driver":
            label = f"{target.given_name} {target.family_name}"
            url = f"/drivers/{target.id}?{urlencode({'season': row.season})}"
        elif valid and row.reference_type == "session":
            event = refs["events"].get(target.event_id)
            valid = event is not None and event.season_id == season.id
            if valid:
                label = f"{event.name} · {target.type.value.replace('_', ' ').title()}"
                query = urlencode({"season": row.season, "session": target.id})
                url = f"/races/{event.id}?{query}#results"
        elif valid and row.reference_type == "comparison":
            comparison = comparisons[target.id]
            valid = comparison.configuration.season == row.season
            label, availability, notices = (
                comparison.title,
                comparison.availability,
                comparison.notices,
            )
            if valid and comparison.open_url:
                url = f"/comparisons/{target.id}/open?season={row.season}"
        if not valid:
            label, url = "Reference unavailable", None
            notices = [
                "The referenced record is unavailable. No replacement was selected."
            ]
        elif row.reference_type != "comparison":
            availability = "available"
            notices = [
                "Page reference only. Recorded analysis and telemetry availability "
                "are checked when opened."
            ]
        result.append(
            ReferenceRead(
                id=row.id,
                reference_type=row.reference_type,
                reference_id=row.reference_id,
                season=row.season,
                created_at=aware(row.created_at),
                updated_at=aware(row.updated_at),
                label=label,
                open_url=url,
                availability=availability if valid else "unavailable",
                notices=notices,
            )
        )
    return result
