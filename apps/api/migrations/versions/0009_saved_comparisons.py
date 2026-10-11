"""Persist local workspace comparison presets without changing source records."""

import sqlalchemy as sa
from alembic import op

revision = "0009_saved_comparisons"
down_revision = "0008_historical_core_sources"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "saved_comparisons",
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
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("comparison_type", sa.String(30), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("source_route", sa.String(30), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        *[
            sa.Column(column, sa.Uuid(), nullable=True)
            for column in (
                "season_id",
                "event_id",
                "session_id",
                "driver_a_id",
                "driver_b_id",
                "lap_a_id",
                "lap_b_id",
            )
        ],
        *[
            sa.ForeignKeyConstraint([column], [f"{table}.id"], ondelete="SET NULL")
            for column, table in (
                ("season_id", "seasons"),
                ("event_id", "events"),
                ("session_id", "sessions"),
                ("driver_a_id", "drivers"),
                ("driver_b_id", "drivers"),
                ("lap_a_id", "laps"),
                ("lap_b_id", "laps"),
            )
        ],
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "comparison_type IN ('telemetry_laps', 'strategy_tyres')",
            name="supported_type",
        ),
        sa.CheckConstraint("season >= 1950", name="valid_season"),
    )
    op.create_index(
        "ix_saved_comparisons_owner_updated",
        "saved_comparisons",
        ["owner_id", "updated_at", "id"],
    )
    op.create_index(
        "ix_saved_comparisons_owner_season", "saved_comparisons", ["owner_id", "season"]
    )


def downgrade():
    op.drop_table("saved_comparisons")
