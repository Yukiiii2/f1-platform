"""Private collections and bookmarks; preserve public records and stale references."""

import sqlalchemy as sa
from alembic import op

revision = "0011_analysis_workspace"
down_revision = "0010_user_accounts"
branch_labels = None
depends_on = None


def entity():
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    ]


def references():
    return [
        sa.Column("reference_id", sa.Uuid(), nullable=False),
        sa.Column("reference_type", sa.String(20), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        *[
            sa.Column(
                column, sa.Uuid(), sa.ForeignKey(target + ".id", ondelete="SET NULL")
            )
            for column, target in [
                ("season_id", "seasons"),
                ("event_id", "events"),
                ("driver_id", "drivers"),
                ("session_id", "sessions"),
                ("comparison_id", "saved_comparisons"),
            ]
        ],
    ]


def upgrade():
    op.create_table(
        "collections",
        *entity(),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.String(1000)),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_collections_user_updated", "collections", ["user_id", "updated_at", "id"]
    )
    op.create_table(
        "collection_items",
        *entity(),
        *references(),
        sa.Column(
            "collection_id",
            sa.Uuid(),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "reference_type IN ('comparison','event','driver','session')",
            name="supported_type",
        ),
        sa.CheckConstraint("season >= 1950 AND season <= 9999", name="valid_season"),
        sa.UniqueConstraint(
            "collection_id",
            "reference_type",
            "reference_id",
            "season",
            name="uq_collection_items_reference",
        ),
    )
    op.create_index(
        "ix_collection_items_collection_created",
        "collection_items",
        ["collection_id", "created_at", "id"],
    )
    op.create_table(
        "favorites",
        *entity(),
        *references(),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "reference_type IN ('event','driver')", name="supported_type"
        ),
        sa.CheckConstraint("season >= 1950 AND season <= 9999", name="valid_season"),
        sa.UniqueConstraint(
            "user_id", "reference_type", "reference_id", name="uq_favorites_reference"
        ),
    )
    op.create_index(
        "ix_favorites_user_created", "favorites", ["user_id", "created_at", "id"]
    )


def downgrade():
    for table in ("collection_items", "favorites", "collections"):
        if op.get_bind().scalar(sa.text("SELECT count(*) FROM " + table)):
            raise RuntimeError(
                "Workspace data exists; rollback requires an explicit preservation plan"
            )
    op.drop_table("collection_items")
    op.drop_table("favorites")
    op.drop_table("collections")
