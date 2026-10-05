from sqlalchemy import select


def session_records(
    db,
    model,
    session_id,
    order,
    limit,
    offset,
    driver_id=None,
    provider=None,
    from_time=None,
    to_time=None,
):
    query = select(model).where(model.session_id == session_id)
    if driver_id is not None and hasattr(model, "driver_id"):
        query = query.where(model.driver_id == driver_id)
    if provider is not None:
        query = query.where(model.provider == provider)
    if from_time is not None:
        query = query.where(model.timestamp >= from_time)
    if to_time is not None:
        query = query.where(model.timestamp < to_time)
    return list(
        db.scalars(
            query.order_by(getattr(model, order), model.id).limit(limit).offset(offset)
        )
    )
