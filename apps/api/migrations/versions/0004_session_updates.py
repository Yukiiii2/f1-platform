"""Durable post-session finalization jobs, without changing F1 domain contracts."""

import sqlalchemy as sa
from alembic import op

revision = "0004_session_updates"
down_revision = "0003_telemetry_pipeline"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "session_update_jobs",
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
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("source_session", sa.Integer(), nullable=False),
        sa.Column("driver_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("stage", sa.String(30), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("completion_evidence", sa.JSON()),
        sa.Column("core_import_id", sa.Uuid()),
        sa.Column("telemetry_import_id", sa.Uuid()),
        sa.Column("row_counts", sa.JSON(), nullable=False),
        sa.Column("derived_summary", sa.JSON(), nullable=False),
        sa.Column("cache_state", sa.JSON(), nullable=False),
        sa.Column("failure_details", sa.String(100)),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_session_update_jobs")),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name=op.f("fk_session_update_jobs_session_id_sessions"),
        ),
        sa.ForeignKeyConstraint(
            ["core_import_id"],
            ["import_runs.id"],
            name=op.f("fk_session_update_jobs_core_import_id_import_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["telemetry_import_id"],
            ["import_runs.id"],
            name=op.f("fk_session_update_jobs_telemetry_import_id_import_runs"),
        ),
        sa.UniqueConstraint("session_id", name="uq_session_update_session"),
        sa.UniqueConstraint("source_session", name="uq_session_update_source"),
        sa.CheckConstraint(
            "source_session > 0",
            name=op.f("ck_session_update_jobs_positive_source_session"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND consecutive_failures >= 0",
            name=op.f("ck_session_update_jobs_nonnegative_attempts"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'retry', 'succeeded', "
            "'failed', 'cancelled')",
            name=op.f("ck_session_update_jobs_status"),
        ),
    )
    op.create_index(
        "ix_session_update_jobs_next_attempt_at",
        "session_update_jobs",
        ["next_attempt_at"],
    )


def downgrade():
    op.drop_index(
        "ix_session_update_jobs_next_attempt_at", table_name="session_update_jobs"
    )
    op.drop_table("session_update_jobs")
