"""Core raw revisions and observation ordering without changing domain IDs."""

import sqlalchemy as sa
from alembic import op

revision = "0008_historical_core_sources"
down_revision = "0007_near_live_updates"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "core_source_revisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
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
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("scope", sa.String(100), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "provider", "scope", "content_hash", name="uq_core_source_revision"
        ),
    )
    op.create_table(
        "core_source_states",
        sa.Column(
            "identity_id",
            sa.Uuid(),
            sa.ForeignKey("provider_identities.id"),
            primary_key=True,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
    )
    # Existing successful observations establish a conservative ordering floor.
    # Original raw payloads are unavailable; no retroactive source is invented.
    op.execute(
        "INSERT INTO core_source_states (identity_id, observed_at) "
        "SELECT p.id, MAX(r.fetched_at) FROM provider_identities p "
        "JOIN import_runs r ON r.provider = p.provider "
        "WHERE r.status = 'succeeded' AND r.fetched_at IS NOT NULL GROUP BY p.id"
    )


def downgrade():
    op.drop_table("core_source_states")
    op.drop_table("core_source_revisions")
