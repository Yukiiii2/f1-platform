"""Create the nine core domain tables.

Revision ID: 0001_core_domain
Revises: None
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_core_domain"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "circuits",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("country", sa.String(length=100), nullable=False),
        sa.Column("locality", sa.String(length=100), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_circuits")),
    )
    op.create_table(
        "drivers",
        sa.Column("given_name", sa.String(length=100), nullable=False),
        sa.Column("family_name", sa.String(length=100), nullable=False),
        sa.Column("code", sa.String(length=3), nullable=True),
        sa.Column("permanent_number", sa.Integer(), nullable=True),
        sa.Column("nationality", sa.String(length=100), nullable=True),
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
            "permanent_number BETWEEN 1 AND 99", name=op.f("ck_drivers_number_range")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_drivers")),
    )
    op.create_table(
        "seasons",
        sa.Column("year", sa.Integer(), nullable=False),
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
        sa.CheckConstraint("year >= 1950", name=op.f("ck_seasons_valid_year")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_seasons")),
        sa.UniqueConstraint("year", name=op.f("uq_seasons_year")),
    )
    op.create_table(
        "teams",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("nationality", sa.String(length=100), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teams")),
    )
    op.create_table(
        "events",
        sa.Column("season_id", sa.Uuid(), nullable=False),
        sa.Column("circuit_id", sa.Uuid(), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("ends_at >= starts_at", name=op.f("ck_events_time_order")),
        sa.CheckConstraint("round > 0", name=op.f("ck_events_positive_round")),
        sa.ForeignKeyConstraint(
            ["circuit_id"], ["circuits.id"], name=op.f("fk_events_circuit_id_circuits")
        ),
        sa.ForeignKeyConstraint(
            ["season_id"], ["seasons.id"], name=op.f("fk_events_season_id_seasons")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
        sa.UniqueConstraint("id", "season_id", name="uq_events_id_season"),
        sa.UniqueConstraint("season_id", "round", name="uq_events_season_round"),
    )
    op.create_index(
        op.f("ix_events_circuit_id"), "events", ["circuit_id"], unique=False
    )
    op.create_index(op.f("ix_events_season_id"), "events", ["season_id"], unique=False)
    op.create_table(
        "constructor_standings",
        sa.Column("season_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("points", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("wins", sa.Integer(), nullable=False),
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
            "points >= 0", name=op.f("ck_constructor_standings_nonnegative_points")
        ),
        sa.CheckConstraint(
            "position > 0", name=op.f("ck_constructor_standings_positive_position")
        ),
        sa.CheckConstraint(
            "wins >= 0", name=op.f("ck_constructor_standings_nonnegative_wins")
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "season_id"],
            ["events.id", "events.season_id"],
            name="fk_constructor_standings_event_season",
        ),
        sa.ForeignKeyConstraint(
            ["season_id"],
            ["seasons.id"],
            name=op.f("fk_constructor_standings_season_id_seasons"),
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name=op.f("fk_constructor_standings_team_id_teams"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_constructor_standings")),
        sa.UniqueConstraint(
            "event_id", "team_id", name="uq_constructor_standings_event_team"
        ),
    )
    op.create_index(
        op.f("ix_constructor_standings_event_id"),
        "constructor_standings",
        ["event_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_constructor_standings_season_id"),
        "constructor_standings",
        ["season_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_constructor_standings_team_id"),
        "constructor_standings",
        ["team_id"],
        unique=False,
    )
    op.create_table(
        "driver_standings",
        sa.Column("season_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("driver_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("points", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("wins", sa.Integer(), nullable=False),
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
            "points >= 0", name=op.f("ck_driver_standings_nonnegative_points")
        ),
        sa.CheckConstraint(
            "position > 0", name=op.f("ck_driver_standings_positive_position")
        ),
        sa.CheckConstraint(
            "wins >= 0", name=op.f("ck_driver_standings_nonnegative_wins")
        ),
        sa.ForeignKeyConstraint(
            ["driver_id"],
            ["drivers.id"],
            name=op.f("fk_driver_standings_driver_id_drivers"),
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "season_id"],
            ["events.id", "events.season_id"],
            name="fk_driver_standings_event_season",
        ),
        sa.ForeignKeyConstraint(
            ["season_id"],
            ["seasons.id"],
            name=op.f("fk_driver_standings_season_id_seasons"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_driver_standings")),
        sa.UniqueConstraint(
            "event_id", "driver_id", name="uq_driver_standings_event_driver"
        ),
    )
    op.create_index(
        op.f("ix_driver_standings_driver_id"),
        "driver_standings",
        ["driver_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_driver_standings_event_id"),
        "driver_standings",
        ["event_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_driver_standings_season_id"),
        "driver_standings",
        ["season_id"],
        unique=False,
    )
    op.create_table(
        "sessions",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "practice_1",
                "practice_2",
                "practice_3",
                "qualifying",
                "sprint_qualifying",
                "sprint",
                "race",
                name="session_type",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "unknown",
                "upcoming",
                "in_progress",
                "completed",
                "delayed",
                "cancelled",
                name="session_status",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('unknown', 'upcoming', 'in_progress', "
            "'completed', 'delayed', 'cancelled')",
            name=op.f("ck_sessions_session_status"),
        ),
        sa.CheckConstraint(
            "type IN ('practice_1', 'practice_2', 'practice_3', 'qualifying', "
            "'sprint_qualifying', 'sprint', 'race')",
            name=op.f("ck_sessions_session_type"),
        ),
        sa.CheckConstraint("ends_at >= starts_at", name=op.f("ck_sessions_time_order")),
        sa.ForeignKeyConstraint(
            ["event_id"], ["events.id"], name=op.f("fk_sessions_event_id_events")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("event_id", "type", name="uq_sessions_event_type"),
    )
    op.create_index(
        op.f("ix_sessions_event_id"), "sessions", ["event_id"], unique=False
    )
    op.create_table(
        "results",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("driver_id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("grid_position", sa.Integer(), nullable=True),
        sa.Column("points", sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column("completed_laps", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=100), nullable=True),
        sa.Column("total_time_ms", sa.Integer(), nullable=True),
        sa.Column("gap_ms", sa.Integer(), nullable=True),
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
            "completed_laps >= 0", name=op.f("ck_results_nonnegative_laps")
        ),
        sa.CheckConstraint("gap_ms >= 0", name=op.f("ck_results_nonnegative_gap")),
        sa.CheckConstraint(
            "grid_position >= 0", name=op.f("ck_results_nonnegative_grid")
        ),
        sa.CheckConstraint("points >= 0", name=op.f("ck_results_nonnegative_points")),
        sa.CheckConstraint("position > 0", name=op.f("ck_results_positive_position")),
        sa.CheckConstraint("total_time_ms > 0", name=op.f("ck_results_positive_time")),
        sa.ForeignKeyConstraint(
            ["driver_id"], ["drivers.id"], name=op.f("fk_results_driver_id_drivers")
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sessions.id"], name=op.f("fk_results_session_id_sessions")
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_results_team_id_teams")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_results")),
        sa.UniqueConstraint(
            "session_id", "driver_id", name="uq_results_session_driver"
        ),
    )
    op.create_index(
        op.f("ix_results_driver_id"), "results", ["driver_id"], unique=False
    )
    op.create_index(
        op.f("ix_results_session_id"), "results", ["session_id"], unique=False
    )
    op.create_index(op.f("ix_results_team_id"), "results", ["team_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_results_team_id"), table_name="results")
    op.drop_index(op.f("ix_results_session_id"), table_name="results")
    op.drop_index(op.f("ix_results_driver_id"), table_name="results")
    op.drop_table("results")
    op.drop_index(op.f("ix_sessions_event_id"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_index(op.f("ix_driver_standings_season_id"), table_name="driver_standings")
    op.drop_index(op.f("ix_driver_standings_event_id"), table_name="driver_standings")
    op.drop_index(op.f("ix_driver_standings_driver_id"), table_name="driver_standings")
    op.drop_table("driver_standings")
    op.drop_index(
        op.f("ix_constructor_standings_team_id"), table_name="constructor_standings"
    )
    op.drop_index(
        op.f("ix_constructor_standings_season_id"), table_name="constructor_standings"
    )
    op.drop_index(
        op.f("ix_constructor_standings_event_id"), table_name="constructor_standings"
    )
    op.drop_table("constructor_standings")
    op.drop_index(op.f("ix_events_season_id"), table_name="events")
    op.drop_index(op.f("ix_events_circuit_id"), table_name="events")
    op.drop_table("events")
    op.drop_table("teams")
    op.drop_table("seasons")
    op.drop_table("drivers")
    op.drop_table("circuits")
