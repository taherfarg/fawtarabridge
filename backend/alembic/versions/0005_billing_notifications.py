"""Billing plans, usage metering, notification log + tenant-enumeration helper.

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("plan", sa.String(length=20), nullable=False, server_default="starter"),
    )
    op.add_column("tenants", sa.Column("trial_ends_at", sa.Date(), nullable=True))

    op.create_table(
        "usage_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("invoice_count", sa.Integer(), nullable=False),
        sa.Column("overage_count", sa.Integer(), nullable=False),
        sa.Column("warned_80", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_usage_records_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usage_records")),
        sa.UniqueConstraint("tenant_id", "period", name=op.f("uq_usage_records_tenant_id")),
    )
    op.create_index(op.f("ix_usage_records_tenant_id"), "usage_records", ["tenant_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("recipient", sa.String(length=255), nullable=False),
        sa.Column("template", sa.String(length=50), nullable=False),
        sa.Column("params", JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_notifications_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notifications_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index(op.f("ix_notifications_tenant_id"), "notifications", ["tenant_id"])

    op.execute("GRANT SELECT, INSERT, UPDATE ON usage_records TO fawtara_app")
    op.execute("GRANT SELECT, INSERT ON notifications TO fawtara_app")
    for table in ("usage_records", "notifications"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_isolation ON {table}
            USING (tenant_id = app_current_tenant_id())
            WITH CHECK (tenant_id = app_current_tenant_id())
            """
        )

    # Controlled cross-tenant enumeration for background jobs (weekly digest):
    # SECURITY DEFINER exposes ONLY the ids, no row data; work then happens
    # per-tenant under normal RLS via tenant_session (DECISIONS D-055).
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_all_tenant_ids() RETURNS SETOF uuid
        LANGUAGE sql STABLE SECURITY DEFINER AS
        $$ SELECT id FROM tenants WHERE status = 'active' $$;
        """
    )
    op.execute("GRANT EXECUTE ON FUNCTION app_all_tenant_ids() TO fawtara_app")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app_all_tenant_ids()")
    op.drop_table("notifications")
    op.drop_table("usage_records")
    op.drop_column("tenants", "trial_ends_at")
    op.drop_column("tenants", "plan")
