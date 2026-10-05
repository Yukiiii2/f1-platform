"""Add import metadata, date-only schedules and nullable standings ranks.

Revision ID: 0002_core_ingestion
Revises: 0001_core_domain
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_core_ingestion"
down_revision = "0001_core_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_identities",
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("entity_kind", sa.String(length=30), nullable=False),
        sa.Column("external_id", sa.String(length=300), nullable=False),
        sa.Column("domain_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "entity_kind IN ('season', 'circuit', 'event', 'session', 'driver', "
            "'team', 'result', 'driver_standing', 'constructor_standing')",
            name=op.f("ck_provider_identities_entity_kind"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provider_identities")),
        sa.UniqueConstraint(
            "provider", "entity_kind", "domain_id", name="uq_provider_identity_domain"
        ),
        sa.UniqueConstraint(
            "provider",
            "entity_kind",
            "external_id",
            name="uq_provider_identity_external",
        ),
    )
    op.create_index(
        op.f("ix_provider_identities_domain_id"),
        "provider_identities",
        ["domain_id"],
        unique=False,
    )
    op.create_table(
        "import_runs",
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("external_identifier", sa.String(length=100), nullable=False),
        sa.Column("season_id", sa.Uuid(), nullable=True),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("row_counts", sa.JSON(), nullable=False),
        sa.Column("failure_details", sa.String(length=500), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name=op.f("ck_import_runs_status"),
        ),
        sa.CheckConstraint(
            "attempt_count > 0", name=op.f("ck_import_runs_positive_attempt_count")
        ),
        sa.ForeignKeyConstraint(
            ["season_id"], ["seasons.id"], name=op.f("fk_import_runs_season_id_seasons")
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name=op.f("fk_import_runs_session_id_sessions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_runs")),
    )
    op.create_index(
        op.f("ix_import_runs_provider"), "import_runs", ["provider"], unique=False
    )
    op.add_column("events", sa.Column("scheduled_date", sa.Date(), nullable=True))
    op.add_column("sessions", sa.Column("scheduled_date", sa.Date(), nullable=True))
    with op.batch_alter_table("driver_standings") as batch:
        batch.alter_column("position", existing_type=sa.Integer(), nullable=True)
    with op.batch_alter_table("constructor_standings") as batch:
        batch.alter_column("position", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("constructor_standings") as batch:
        batch.alter_column("position", existing_type=sa.Integer(), nullable=False)
    with op.batch_alter_table("driver_standings") as batch:
        batch.alter_column("position", existing_type=sa.Integer(), nullable=False)
    op.drop_column("sessions", "scheduled_date")
    op.drop_column("events", "scheduled_date")
    op.drop_index(op.f("ix_import_runs_provider"), table_name="import_runs")
    op.drop_table("import_runs")
    op.drop_index(
        op.f("ix_provider_identities_domain_id"), table_name="provider_identities"
    )
    op.drop_table("provider_identities")
