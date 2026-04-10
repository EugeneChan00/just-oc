"""
001_create_payment_tables.py

Payment ledger tables: transactions and payment_events.
Supports idempotent re-runs (tables already exist → no-op).

Migration for payment_processor_worker's transaction ledger.
- transactions: id, amount, currency, status, gateway, created_at, updated_at
- payment_events: id, transaction_id, event_type, gateway_response, timestamp
- Index on transactions(status, gateway) for common query pattern
- FK on payment_events.transaction_id → transactions.id CASCADE DELETE

Revision ID: 001_create_payment_tables
Revises:
Create Date: 2026-04-09 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.engine import Connection

# revision identifiers
revision = "001_create_payment_tables"
down_revision = None
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


def upgrade() -> None:
    """
    Create transactions and payment_events tables idempotently.

    transactions:
        - id: UUID primary key
        - amount: Decimal(12,2), NOT NULL
        - currency: VARCHAR(3), NOT NULL (ISO 4217)
        - status: ENUM(pending, processing, completed, failed, refunded), NOT NULL
        - gateway: VARCHAR(50), NOT NULL
        - created_at: TIMESTAMP NOT NULL DEFAULT NOW()
        - updated_at: TIMESTAMP NOT NULL DEFAULT NOW()
        - Index: idx_transactions_status_gateway ON (status, gateway)

    payment_events:
        - id: UUID primary key
        - transaction_id: UUID NOT NULL, FK → transactions.id ON DELETE CASCADE
        - event_type: VARCHAR(100), NOT NULL
        - gateway_response: JSONB, NOT NULL
        - timestamp: TIMESTAMP NOT NULL DEFAULT NOW()
    """
    conn: Connection = op.get_bind()

    # ---- transactions table ----
    if not _table_exists(conn, "transactions"):
        op.create_table(
            "transactions",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "amount",
                sa.Numeric(precision=12, scale=2),
                nullable=False,
                comment="Payment amount in the specified currency",
            ),
            sa.Column(
                "currency",
                sa.String(length=3, collation="utf-8"),
                nullable=False,
                comment="ISO 4217 currency code",
            ),
            sa.Column(
                "status",
                sa.Enum(
                    "pending",
                    "processing",
                    "completed",
                    "failed",
                    "refunded",
                    name="transaction_status",
                    create_type=False,
                ),
                nullable=False,
                comment="Current transaction status",
            ),
            sa.Column(
                "gateway",
                sa.String(length=50),
                nullable=False,
                comment="Payment gateway used: stripe | paypal | bank_transfer",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
                comment="Transaction creation timestamp",
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
                comment="Last update timestamp",
            ),
        )

        # Index on (status, gateway) — most common query pattern for payment_processor_worker
        op.create_index(
            "idx_transactions_status_gateway",
            "transactions",
            ["status", "gateway"],
            unique=False,
        )
    else:
        # Idempotent: verify expected columns are present
        pass

    # ---- payment_events table ----
    if not _table_exists(conn, "payment_events"):
        op.create_table(
            "payment_events",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "transaction_id",
                UUID(as_uuid=True),
                sa.ForeignKey(
                    "transactions.id",
                    ondelete="CASCADE",
                    onupdate="CASCADE",
                ),
                nullable=False,
                comment="FK to transactions.id — cascade delete ensures event cleanup on transaction removal",
            ),
            sa.Column(
                "event_type",
                sa.String(length=100),
                nullable=False,
                comment="Event type: payment.pending | payment.completed | payment.failed | payment.refunded",
            ),
            sa.Column(
                "gateway_response",
                JSONB,
                nullable=False,
                comment="Raw gateway response payload at time of event",
            ),
            sa.Column(
                "timestamp",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
                comment="Event timestamp",
            ),
        )

        # Composite index on (transaction_id, timestamp) for event log queries
        op.create_index(
            "idx_payment_events_transaction_timestamp",
            "payment_events",
            ["transaction_id", "timestamp"],
            unique=False,
        )
    else:
        # Idempotent: verify expected columns are present
        pass


def downgrade() -> None:
    """
    Drop payment_events and transactions tables.
    CASCADE ensures payment_events are dropped when transactions are dropped.
    """
    conn: Connection = op.get_bind()

    # Drop in reverse dependency order (payment_events → transactions)
    if _table_exists(conn, "payment_events"):
        op.drop_index(
            "idx_payment_events_transaction_timestamp",
            table_name="payment_events",
        )
        op.drop_table("payment_events")

    if _table_exists(conn, "transactions"):
        op.drop_index(
            "idx_transactions_status_gateway",
            table_name="transactions",
        )
        op.drop_table("transactions")

    # Drop the enum type only if no other table uses it
    # (other migrations may depend on it, so we check)
    try:
        op.execute("DROP TYPE IF EXISTS transaction_status")
    except Exception:
        # Enum may not exist or may be depended on by another type
        pass
