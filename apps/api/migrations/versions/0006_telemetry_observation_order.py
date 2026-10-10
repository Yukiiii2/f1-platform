"""Prevent older observations from replacing newer normalized telemetry."""

import sqlalchemy as sa
from alembic import op

revision = "0006_telemetry_observation_order"
down_revision = "0005_pitwall_protection"
branch_labels = None
depends_on = None

TABLES = (
    "laps",
    "telemetry_samples",
    "stints",
    "pit_stops",
    "position_samples",
    "interval_samples",
    "race_control_messages",
    "weather_samples",
)


def upgrade():
    for name in TABLES:
        op.add_column(name, sa.Column("source_observed_at", sa.DateTime(timezone=True)))
        # Revision timestamps are first-seen times, not latest observation times
        # (A->B->A reuses A's immutable revision). Protect all pre-migration state
        # from in-flight/cached older bundles with a conservative migration time.
        # Stop importers during migration and fetch again after upgrading.
        op.execute(sa.text(f"UPDATE {name} SET source_observed_at = CURRENT_TIMESTAMP"))


def downgrade():
    for name in reversed(TABLES):
        op.drop_column(name, "source_observed_at")
