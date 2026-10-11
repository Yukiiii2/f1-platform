"""Accounts and private ownership; preserve unassigned workspace presets."""

import sqlalchemy as sa
from alembic import op

revision = "0010_user_accounts"
down_revision = "0009_saved_comparisons"
branch_labels = None
depends_on = None


def entity_columns():
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


def upgrade():
    op.create_table(
        "users",
        *entity_columns(),
        sa.Column("username", sa.String(32), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.CheckConstraint("username = lower(username)", name="normalized_name"),
    )
    op.create_table(
        "auth_sessions",
        *entity_columns(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_auth_sessions_user_created", "auth_sessions", ["user_id", "created_at"]
    )
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_table(
        "auth_usage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("minute", sa.Integer(), nullable=False),
        sa.Column("minute_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("id = 1", name="singleton"),
        sa.CheckConstraint("minute_count >= 0", name="nonnegative_usage"),
    )
    op.bulk_insert(
        sa.table(
            "auth_usage",
            sa.column("id", sa.Integer()),
            sa.column("minute", sa.Integer()),
            sa.column("minute_count", sa.Integer()),
        ),
        [{"id": 1, "minute": 0, "minute_count": 0}],
    )
    with op.batch_alter_table("saved_comparisons") as batch:
        batch.alter_column("owner_id", existing_type=sa.Uuid(), nullable=True)
        batch.add_column(sa.Column("user_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_saved_comparisons_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_check_constraint(
            op.f("ck_saved_comparisons_one_owner"),
            "(user_id IS NOT NULL AND owner_id IS NULL) OR "
            "(user_id IS NULL AND owner_id IS NOT NULL)",
        )
        batch.create_index(
            "ix_saved_comparisons_user_updated", ["user_id", "updated_at", "id"]
        )
        batch.create_index("ix_saved_comparisons_user_season", ["user_id", "season"])


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM users")):
        raise RuntimeError(
            "Account data exists; account migration rollback requires "
            "an explicit preservation plan"
        )
    with op.batch_alter_table("saved_comparisons") as batch:
        batch.drop_index("ix_saved_comparisons_user_updated")
        batch.drop_index("ix_saved_comparisons_user_season")
        batch.drop_constraint(op.f("ck_saved_comparisons_one_owner"), type_="check")
        batch.drop_constraint(
            op.f("fk_saved_comparisons_user_id_users"), type_="foreignkey"
        )
        batch.drop_column("user_id")
        batch.alter_column("owner_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_table("auth_usage")
    op.drop_table("auth_sessions")
    op.drop_table("users")
