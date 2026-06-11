"""Transmissions, append-only audit log, tenant ASP onboarding columns.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-11

audit_events is append-only AT THE DATABASE LEVEL: fawtara_app gets SELECT and
INSERT only — no UPDATE, no DELETE (architecture rule 5).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("entity_type", sa.String(length=30), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("before", JSONB(), nullable=True),
        sa.Column("after", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_audit_events_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_audit_events_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(op.f("ix_audit_events_tenant_id"), "audit_events", ["tenant_id"])
    op.create_index(
        "ix_audit_events_entity", "audit_events", ["tenant_id", "entity_type", "entity_id"]
    )

    op.create_table(
        "transmissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("asp_provider", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("spec_version", sa.String(length=30), nullable=False),
        sa.Column("xml_hash", sa.String(length=64), nullable=False),
        sa.Column("asp_message_id", sa.String(length=100), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("rejection_code", sa.String(length=50), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            ["invoice_id"],
            ["invoices.id"],
            name=op.f("fk_transmissions_invoice_id_invoices"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_transmissions_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transmissions")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_transmissions_idempotency_key")),
    )
    op.create_index(op.f("ix_transmissions_tenant_id"), "transmissions", ["tenant_id"])
    op.create_index(op.f("ix_transmissions_invoice_id"), "transmissions", ["invoice_id"])
    op.create_index(op.f("ix_transmissions_asp_message_id"), "transmissions", ["asp_message_id"])

    op.add_column("tenants", sa.Column("asp_participant_id", sa.String(length=100), nullable=True))
    op.add_column(
        "tenants",
        sa.Column(
            "asp_onboarding_status",
            sa.String(length=20),
            nullable=False,
            server_default="not_started",
        ),
    )

    # --- privileges & RLS -----------------------------------------------------
    # Append-only: NO update/delete grants on audit_events, even for the app role.
    op.execute("GRANT SELECT, INSERT ON audit_events TO fawtara_app")
    op.execute("GRANT SELECT, INSERT, UPDATE ON transmissions TO fawtara_app")

    for table in ("audit_events", "transmissions"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_isolation ON {table}
            USING (tenant_id = app_current_tenant_id())
            WITH CHECK (tenant_id = app_current_tenant_id())
            """
        )


def downgrade() -> None:
    op.drop_column("tenants", "asp_onboarding_status")
    op.drop_column("tenants", "asp_participant_id")
    op.drop_table("transmissions")
    op.drop_table("audit_events")
