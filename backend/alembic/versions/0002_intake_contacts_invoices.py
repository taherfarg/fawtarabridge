"""Intake: contacts, invoices, import mapping templates (+ RLS).

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-10

All three tables are tenant-owned business data: ENABLE + FORCE row-level
security with the tenant-arm policy, explicit grants to fawtara_app.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RLS_TABLES = ("contacts", "invoices", "import_mapping_templates")


def upgrade() -> None:
    op.create_table(
        "contacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name_en", sa.String(length=255), nullable=False),
        sa.Column("name_ar", sa.String(length=255), nullable=True),
        sa.Column("trn", sa.String(length=15), nullable=True),
        sa.Column("peppol_id", sa.String(length=100), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("street", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("emirate", sa.String(length=50), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("default_vat_category", sa.String(length=4), nullable=True),
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
            name=op.f("fk_contacts_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contacts")),
    )
    op.create_index(op.f("ix_contacts_tenant_id"), "contacts", ["tenant_id"], unique=False)
    op.create_index(
        "ix_contacts_tenant_id_trn",
        "contacts",
        ["tenant_id", "trn"],
        unique=True,
        postgresql_where=sa.text("trn IS NOT NULL"),
    )

    op.create_table(
        "invoices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_number", sa.String(length=100), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("canonical", JSONB(), nullable=False),
        sa.Column("spec_version", sa.String(length=30), nullable=True),
        sa.Column("buyer_contact_id", sa.Uuid(), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("buyer_name", sa.String(length=255), nullable=False),
        sa.Column("buyer_trn", sa.String(length=15), nullable=True),
        sa.Column("total_including_vat", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("duplicate_warning", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
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
            ["buyer_contact_id"],
            ["contacts.id"],
            name=op.f("fk_invoices_buyer_contact_id_contacts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_invoices_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_invoices_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoices")),
        sa.UniqueConstraint("tenant_id", "invoice_number", name=op.f("uq_invoices_tenant_id")),
    )
    op.create_index(op.f("ix_invoices_tenant_id"), "invoices", ["tenant_id"], unique=False)
    op.create_index(
        "ix_invoices_tenant_id_issue_date", "invoices", ["tenant_id", "issue_date"], unique=False
    )
    op.create_index(
        "ix_invoices_tenant_id_status", "invoices", ["tenant_id", "status"], unique=False
    )
    op.create_index(
        "ix_invoices_tenant_id_buyer_trn", "invoices", ["tenant_id", "buyer_trn"], unique=False
    )

    op.create_table(
        "import_mapping_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("mapping", JSONB(), nullable=False),
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
            name=op.f("fk_import_mapping_templates_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_mapping_templates")),
        sa.UniqueConstraint(
            "tenant_id", "name", name=op.f("uq_import_mapping_templates_tenant_id")
        ),
    )
    op.create_index(
        op.f("ix_import_mapping_templates_tenant_id"),
        "import_mapping_templates",
        ["tenant_id"],
        unique=False,
    )

    for table in _RLS_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO fawtara_app")
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
    op.drop_table("import_mapping_templates")
    op.drop_table("invoices")
    op.drop_index("ix_contacts_tenant_id_trn", table_name="contacts")
    op.drop_table("contacts")
