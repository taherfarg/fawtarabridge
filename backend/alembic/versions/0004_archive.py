"""Immutable archive records (FR-7.1).

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-11

Append-only at the database level (SELECT+INSERT grants only). Tenant FK is
RESTRICT: archived compliance records must outlive casual tenant deletion.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "archive_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("transmission_id", sa.Uuid(), nullable=True),
        sa.Column("invoice_number", sa.String(length=100), nullable=False),
        sa.Column("buyer_name", sa.String(length=255), nullable=False),
        sa.Column("buyer_trn", sa.String(length=15), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("total_including_vat", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("spec_version", sa.String(length=30), nullable=False),
        sa.Column("xml", sa.LargeBinary(), nullable=False),
        sa.Column("pdf", sa.LargeBinary(), nullable=False),
        sa.Column("ack", JSONB(), nullable=False),
        sa.Column("xml_hash", sa.String(length=64), nullable=False),
        sa.Column("retention_until", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
            name=op.f("fk_archive_records_invoice_id_invoices"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_archive_records_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["transmission_id"],
            ["transmissions.id"],
            name=op.f("fk_archive_records_transmission_id_transmissions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_archive_records")),
        sa.UniqueConstraint("invoice_id", name=op.f("uq_archive_records_invoice_id")),
    )
    op.create_index(op.f("ix_archive_records_tenant_id"), "archive_records", ["tenant_id"])
    op.create_index(
        "ix_archive_records_tenant_issue", "archive_records", ["tenant_id", "issue_date"]
    )

    # Deterministic audit ordering: same-transaction events share created_at.
    op.execute(
        "ALTER TABLE audit_events ADD COLUMN seq BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE"
    )

    op.execute("GRANT SELECT, INSERT ON archive_records TO fawtara_app")
    op.execute("ALTER TABLE archive_records ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE archive_records FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY archive_records_isolation ON archive_records
        USING (tenant_id = app_current_tenant_id())
        WITH CHECK (tenant_id = app_current_tenant_id())
        """
    )


def downgrade() -> None:
    op.drop_table("archive_records")
    op.drop_column("audit_events", "seq")
