"""Shared bounded Pitwall admission counters."""

import sqlalchemy as sa
from alembic import op

revision = "0005_pitwall_protection"
down_revision = "0004_session_updates"
branch_labels = None
depends_on = None


def upgrade():
    table = op.create_table(
        "pitwall_usage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("minute", sa.Integer(), nullable=False),
        sa.Column("minute_count", sa.Integer(), nullable=False),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("day_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pitwall_usage")),
        sa.CheckConstraint("id = 1", name=op.f("ck_pitwall_usage_singleton")),
        sa.CheckConstraint(
            "minute_count >= 0 AND day_count >= 0",
            name=op.f("ck_pitwall_usage_nonnegative_usage"),
        ),
    )
    op.bulk_insert(table, [dict(id=1, minute=0, minute_count=0, day=0, day_count=0)])


def downgrade():
    op.drop_table("pitwall_usage")
