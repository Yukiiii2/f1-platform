import argparse
from uuid import UUID

from sqlalchemy import func, select, update

from app import models
from app.db.session import get_session_factory


def assign_legacy(db, workspace: UUID, user_id: UUID, apply=False):
    if (
        db.scalar(
            select(models.User.id).where(models.User.id == user_id).with_for_update()
        )
        is None
    ):
        raise ValueError("Target account does not exist")
    scope = (
        models.SavedComparison.owner_id == workspace,
        models.SavedComparison.user_id.is_(None),
    )
    if not apply:
        return db.scalar(
            select(func.count()).select_from(models.SavedComparison).where(*scope)
        )
    ids = db.scalars(
        update(models.SavedComparison)
        .where(*scope)
        .values(user_id=user_id, owner_id=None)
        .returning(models.SavedComparison.id)
    ).all()
    db.commit()
    return len(ids)


def main():
    parser = argparse.ArgumentParser(
        description="Explicit legacy preset assignment; dry run by default"
    )
    parser.add_argument("--assign-legacy", action="store_true", required=True)
    parser.add_argument("--workspace", type=UUID, required=True)
    parser.add_argument("--user", type=UUID, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with get_session_factory()() as db:
        try:
            count = assign_legacy(db, args.workspace, args.user, args.apply)
        except ValueError as error:
            parser.error(str(error))
    print(f"{'Assigned' if args.apply else 'Dry run: eligible'} presets: {count}")


if __name__ == "__main__":
    main()
