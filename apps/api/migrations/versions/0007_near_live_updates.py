"""Opt-in near-live state; existing jobs retain historical behavior."""

import sqlalchemy as sa
from alembic import op

revision = "0007_near_live_updates"
down_revision = "0006_telemetry_observation_order"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "session_update_jobs",
        sa.Column(
            "live_active", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "session_update_jobs",
        sa.Column(
            "live_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "session_update_jobs",
        sa.Column(
            "live_suspended", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "session_update_jobs",
        sa.Column("live_cursor", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "session_update_jobs",
        sa.Column("live_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "session_update_jobs",
        sa.Column("live_ends_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "session_update_jobs",
        sa.Column(
            "data_status", sa.String(20), nullable=False, server_default="not_tracked"
        ),
    )
    with op.batch_alter_table("session_update_jobs") as batch:
        batch.create_check_constraint(
            "data_status", "data_status IN ('not_tracked', 'provisional', 'finalized')"
        )
    op.execute(
        "UPDATE session_update_jobs SET data_status = 'finalized' "
        "WHERE status = 'succeeded'"
    )


def downgrade():
    with op.batch_alter_table("session_update_jobs") as batch:
        batch.drop_constraint("data_status", type_="check")
        for column in (
            "data_status",
            "live_ends_at",
            "live_updated_at",
            "live_cursor",
            "live_suspended",
            "live_enabled",
            "live_active",
        ):
            batch.drop_column(column)
