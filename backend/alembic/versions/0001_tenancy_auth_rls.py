"""Tenancy + auth tables, app role, RLS policies.

Revision ID: 0001
Revises:
Create Date: 2026-06-10

Multi-tenancy ground rules established here:
- ``fawtara_app`` is the runtime role: LOGIN, NOSUPERUSER, NOBYPASSRLS. Grants are
  explicit per table (no ALTER DEFAULT PRIVILEGES) so compliance-sensitive tables
  (e.g. the append-only audit log in M4) can withhold UPDATE/DELETE.
- Policies key on transaction-local GUCs ``app.current_tenant_id`` /
  ``app.current_user_id`` via the helper functions below. Unset GUC => NULL =>
  policy false => zero rows.
- ``users`` carries no tenant_id (global identity, accountants span tenants) and is
  deliberately not under RLS — see docs/DECISIONS.md D-006.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("legal_name_ar", sa.String(length=255), nullable=False),
        sa.Column("legal_name_en", sa.String(length=255), nullable=False),
        sa.Column("trn", sa.String(length=15), nullable=False),
        sa.Column("license_no", sa.String(length=100), nullable=True),
        sa.Column("emirate", sa.String(length=50), nullable=True),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("revenue_band", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
    )
    op.create_index(op.f("ix_tenants_trn"), "tenants", ["trn"], unique=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("phone_verified", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "tenant_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
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
            name=op.f("fk_tenant_memberships_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_tenant_memberships_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenant_memberships")),
        sa.UniqueConstraint("tenant_id", "user_id", name=op.f("uq_tenant_memberships_tenant_id")),
    )
    op.create_index(
        op.f("ix_tenant_memberships_tenant_id"), "tenant_memberships", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_tenant_memberships_user_id"), "tenant_memberships", ["user_id"], unique=False
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_refresh_tokens_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_refresh_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
    )
    op.create_index(op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], unique=False)

    op.create_table(
        "otp_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=30), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_otp_codes_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_otp_codes")),
    )
    op.create_index(op.f("ix_otp_codes_user_id"), "otp_codes", ["user_id"], unique=False)

    # --- runtime role -------------------------------------------------------
    # Dev/CI password; production overrides it via the secrets vault (D-005).
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fawtara_app') THEN
                CREATE ROLE fawtara_app LOGIN PASSWORD 'fawtara_app'
                    NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
            END IF;
        END
        $$;
        """
    )
    op.execute("GRANT USAGE ON SCHEMA public TO fawtara_app")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON "
        "tenants, users, tenant_memberships, refresh_tokens, otp_codes TO fawtara_app"
    )

    # --- RLS context helpers ------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_current_tenant_id() RETURNS uuid
        LANGUAGE sql STABLE AS
        $$ SELECT NULLIF(current_setting('app.current_tenant_id', true), '')::uuid $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_current_user_id() RETURNS uuid
        LANGUAGE sql STABLE AS
        $$ SELECT NULLIF(current_setting('app.current_user_id', true), '')::uuid $$;
        """
    )

    # --- RLS policies ---------------------------------------------------------
    # FORCE so policies bind even if the connecting role owns the table.
    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenants FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenants_isolation ON tenants
        USING (
            id = app_current_tenant_id()
            OR EXISTS (
                SELECT 1 FROM tenant_memberships m
                WHERE m.tenant_id = tenants.id AND m.user_id = app_current_user_id()
            )
        )
        WITH CHECK (id = app_current_tenant_id())
        """
    )

    op.execute("ALTER TABLE tenant_memberships ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenant_memberships FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_memberships_isolation ON tenant_memberships
        USING (
            tenant_id = app_current_tenant_id()
            OR user_id = app_current_user_id()
        )
        WITH CHECK (tenant_id = app_current_tenant_id())
        """
    )

    op.execute("ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE refresh_tokens FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY refresh_tokens_isolation ON refresh_tokens
        USING (user_id = app_current_user_id())
        WITH CHECK (user_id = app_current_user_id())
        """
    )

    op.execute("ALTER TABLE otp_codes ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE otp_codes FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY otp_codes_isolation ON otp_codes
        USING (user_id = app_current_user_id())
        WITH CHECK (user_id = app_current_user_id())
        """
    )


def downgrade() -> None:
    op.drop_table("otp_codes")
    op.drop_table("refresh_tokens")
    op.drop_table("tenant_memberships")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
    op.drop_index(op.f("ix_tenants_trn"), table_name="tenants")
    op.drop_table("tenants")
    op.execute("DROP FUNCTION IF EXISTS app_current_tenant_id()")
    op.execute("DROP FUNCTION IF EXISTS app_current_user_id()")
    # the fawtara_app role is intentionally left in place (shared across databases)
