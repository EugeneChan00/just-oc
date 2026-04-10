"""
002_add_gateway_configs.py

Gateway configuration table for payment_processor_worker.
Supports idempotent re-runs (table already exists → no-op).

Revision ID: 002_add_gateway_configs
Revises: 001_create_payment_tables
Create Date: 2026-04-09 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.engine import Connection

# revision identifiers
revision = "002_add_gateway_configs"
down_revision = "001_create_payment_tables"
branch_labels = None
depends_on = None


def _table_exists(connection: Connection, table_name: str) -> bool:
    """Check if a table exists in the database."""
    result = connection.execute(
        sa.text(
            "SELECT EXISTS ("
            "  SELECT FROM information_schema.tables "
            "  WHERE table_schema = 'public' "
            "  AND table_name = :table_name"
            ")"
        ),
        {"table_name": table_name},
    )
    return result.scalar() is True


def _constraint_exists(
    connection: Connection, table_name: str, constraint_name: str
) -> bool:
    """Check if a named constraint exists on a table."""
    result = connection.execute(
        sa.text(
            "SELECT EXISTS ("
            "  SELECT FROM information_schema.table_constraints "
            "  WHERE constraint_schema = 'public' "
            "  AND table_name = :table_name "
            "  AND constraint_name = :constraint_name"
            ")"
        ),
        {"table_name": table_name, "constraint_name": constraint_name},
    )
    return result.scalar() is True


def upgrade() -> None:
    """
    Create gateway_configs table idempotently.

    gateway_configs:
        - id: UUID primary key
        - gateway_name: VARCHAR(50), NOT NULL, UNIQUE
        - api_endpoint: VARCHAR(500), NOT NULL
        - credentials_vault_path: VARCHAR(500), NOT NULL
        - is_active: BOOLEAN, NOT NULL DEFAULT TRUE

    Unique constraint: gateway_name must be unique across all gateway configs.
    This ensures only one active configuration per gateway.
    """
    conn: Connection = op.get_bind()

    if not _table_exists(conn, "gateway_configs"):
        op.create_table(
            "gateway_configs",
            sa.Column(
                "id",
                UUID(as_uuid=True),
                primary_key=True,
                comment="Gateway configuration ID",
            ),
            sa.Column(
                "gateway_name",
                sa.String(length=50),
                nullable=False,
                unique=True,
                comment="Gateway name: stripe | paypal | bank_transfer",
            ),
            sa.Column(
                "api_endpoint",
                sa.String(length=500),
                nullable=False,
                comment="Base API endpoint URL for the gateway",
            ),
            sa.Column(
                "credentials_vault_path",
                sa.String(length=500),
                nullable=False,
                comment="Vault path for API credentials (e.g., vault://stripe/secrets/live)",
            ),
            sa.Column(
                "is_active",
                sa.Boolean,
                nullable=False,
                server_default=sa.true(),
                comment="Whether this gateway config is active for payment processing",
            ),
            comment="Payment gateway configurations for payment_processor_worker",
        )

        # Index on is_active for filtering active gateways (used by select_gateway logic)
        op.create_index(
            "idx_gateway_configs_is_active",
            "gateway_configs",
            ["is_active"],
            unique=False,
        )
    else:
        # Idempotent: verify unique constraint on gateway_name exists
        # If table existed before this migration, constraint may not be there
        if not _constraint_exists(
            conn, "gateway_configs", "gateway_configs_gateway_name_key"
        ):
            # PostgreSQL auto-creates constraint named gateway_configs_gateway_name_key for unique=True
            # If we reach here on an older table, we need to add the constraint
            op.execute(
                "ALTER TABLE gateway_configs "
                "ADD CONSTRAINT gateway_configs_gateway_name_unique UNIQUE (gateway_name)"
            )
        # If table was created with the unique=True in create_table above, the constraint
        # will already exist (named gateway_configs_gateway_name_key by PostgreSQL convention)
        pass


def downgrade() -> None:
    """
    Drop gateway_configs table.
    """
    conn: Connection = op.get_bind()

    if _table_exists(conn, "gateway_configs"):
        op.drop_index(
            "idx_gateway_configs_is_active",
            table_name="gateway_configs",
        )
        op.drop_table("gateway_configs")
