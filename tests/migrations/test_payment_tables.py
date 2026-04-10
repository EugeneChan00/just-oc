"""
tests/migrations/test_payment_tables.py

Red-phase failing tests for payment migration scripts.
These tests verify table creation, index verification, foreign key constraints,
and idempotent re-runs for:
- 001_create_payment_tables (transactions, payment_events)
- 002_add_gateway_configs (gateway_configs)

These tests are DESIGNED TO FAIL until the migrations are implemented correctly.
Once migrations are in place and passing, these tests should green.
"""

import pytest


class MockTable:
    """Mock table object for verifying op.create_table calls."""

    def __init__(self, name):
        self.name = name
        self.columns = []
        self.indexes = []
        self.foreign_keys = []
        self.constraints = []


class MockColumn:
    """Mock column for verifying table creation."""

    def __init__(self, name, type_, nullable=False, primary_key=False):
        self.name = name
        self.type = type_
        self.nullable = nullable
        self.primary_key = primary_key


class MockIndex:
    """Mock index for verifying index creation."""

    def __init__(self, name, columns, unique=False):
        self.name = name
        self.columns = columns
        self.unique = unique


class MockForeignKey:
    """Mock foreign key for verifying FK constraints."""

    def __init__(self, column, reference, ondelete):
        self.column = column
        self.reference = reference
        self.ondelete = ondelete


class Test001CreatePaymentTables:
    """Tests for 001_create_payment_tables migration."""

    def test_transactions_table_has_all_required_columns(self):
        """
        RED TEST: transactions table must have id, amount, currency, status, gateway, created_at, updated_at.
        FAIL until migration creates the table with correct schema.
        """
        # This test reads the migration file and parses column definitions
        # In a real test, we would run the migration and inspect the schema
        # For red-phase, we verify the migration file has correct create_table calls
        import ast
        from pathlib import Path

        migration_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "migrations"
            / "versions"
            / "001_create_payment_tables.py"
        )
        assert migration_path.exists(), (
            "Migration file 001_create_payment_tables.py does not exist"
        )

        source = migration_path.read_text()

        # Verify required columns are referenced in the migration
        required_columns = [
            "id",
            "amount",
            "currency",
            "status",
            "gateway",
            "created_at",
            "updated_at",
        ]
        for col in required_columns:
            assert col in source, (
                f"Column '{col}' not found in 001_create_payment_tables.py"
            )

        # Verify Numeric type for amount (12,2 precision)
        assert "Numeric(precision=12, scale=2)" in source, (
            "amount should be Decimal(12,2)"
        )

        # Verify VARCHAR(3) for currency
        assert "String(length=3)" in source or "VARCHAR(3)" in source, (
            "currency should be VARCHAR(3)"
        )

        # Verify transaction_status enum with all values
        for status in ["pending", "processing", "completed", "failed", "refunded"]:
            assert status in source, f"Status '{status}' not found in enum definition"

    def test_payment_events_table_has_all_required_columns(self):
        """
        RED TEST: payment_events table must have id, transaction_id, event_type, gateway_response, timestamp.
        FAIL until migration creates the table with correct schema.
        """
        from pathlib import Path

        migration_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "migrations"
            / "versions"
            / "001_create_payment_tables.py"
        )
        source = migration_path.read_text()

        required_columns = [
            "id",
            "transaction_id",
            "event_type",
            "gateway_response",
            "timestamp",
        ]
        for col in required_columns:
            assert col in source, (
                f"Column '{col}' not found in payment_events table definition"
            )

        # Verify JSONB type for gateway_response
        assert "JSONB" in source, "gateway_response should be JSONB type"

    def test_transactions_has_status_gateway_index(self):
        """
        RED TEST: transactions table must have index idx_transactions_status_gateway on (status, gateway).
        FAIL until migration creates the index.
        """
        from pathlib import Path

        migration_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "migrations"
            / "versions"
            / "001_create_payment_tables.py"
        )
        source = migration_path.read_text()

        assert "idx_transactions_status_gateway" in source, (
            "Index idx_transactions_status_gateway not found"
        )
        assert '["status", "gateway"]' in source or "['status', 'gateway']" in source, (
            "Index should be on (status, gateway)"
        )

    def test_payment_events_has_foreign_key_to_transactions(self):
        """
        RED TEST: payment_events.transaction_id must have FK to transactions.id with CASCADE DELETE.
        FAIL until migration creates the FK with correct cascade behavior.
        """
        from pathlib import Path

        migration_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "migrations"
            / "versions"
            / "001_create_payment_tables.py"
        )
        source = migration_path.read_text()

        assert "ForeignKey" in source, "ForeignKey not found in migration"
        assert "transactions.id" in source, "FK should reference transactions.id"
        assert 'ondelete="CASCADE"' in source or "ondelete='CASCADE'" in source, (
            "FK should have ON DELETE CASCADE"
        )

    def test_migration_is_idempotent(self):
        """
        RED TEST: Migration must handle idempotent re-runs (tables already exist → no-op).
        FAIL until migration implements _table_exists check.
        """
        from pathlib import Path

        migration_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "migrations"
            / "versions"
            / "001_create_payment_tables.py"
        )
        source = migration_path.read_text()

        # Migration must have _table_exists function
        assert "_table_exists" in source, (
            "_table_exists function not found for idempotency"
        )

        # Migration must check if table exists before creating
        assert "_table_exists" in source and "create_table" in source, (
            "Migration should check existence before create_table"
        )

        # The upgrade function should wrap table creation in existence check
        upgrade_func_start = source.find("def upgrade")
        assert upgrade_func_start != -1, "upgrade() function not found"

        # Verify _table_exists is called in upgrade
        assert source.count("_table_exists") >= 2, (
            "Should check _table_exists for both transactions and payment_events"
        )

    def test_downgrade_drops_tables_in_reverse_order(self):
        """
        RED TEST: Downgrade must drop payment_events before transactions (FK dependency).
        FAIL until downgrade implements correct drop order.
        """
        from pathlib import Path

        migration_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "migrations"
            / "versions"
            / "001_create_payment_tables.py"
        )
        source = migration_path.read_text()

        downgrade_start = source.find("def downgrade")
        assert downgrade_start != -1, "downgrade() function not found"

        downgrade_body = source[downgrade_start:]

        # payment_events should be dropped before transactions (reverse FK order)
        events_drop_pos = downgrade_body.find('drop_table("payment_events")')
        transactions_drop_pos = downgrade_body.find('drop_table("transactions")')

        assert events_drop_pos != -1, "payment_events drop not found in downgrade"
        assert transactions_drop_pos != -1, "transactions drop not found in downgrade"
        assert events_drop_pos < transactions_drop_pos, (
            "payment_events should be dropped before transactions (FK dependency)"
        )


class Test002AddGatewayConfigs:
    """Tests for 002_add_gateway_configs migration."""

    def test_gateway_configs_table_has_all_required_columns(self):
        """
        RED TEST: gateway_configs table must have id, gateway_name, api_endpoint, credentials_vault_path, is_active.
        FAIL until migration creates the table with correct schema.
        """
        from pathlib import Path

        migration_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "migrations"
            / "versions"
            / "002_add_gateway_configs.py"
        )
        assert migration_path.exists(), (
            "Migration file 002_add_gateway_configs.py does not exist"
        )

        source = migration_path.read_text()

        required_columns = [
            "id",
            "gateway_name",
            "api_endpoint",
            "credentials_vault_path",
            "is_active",
        ]
        for col in required_columns:
            assert col in source, (
                f"Column '{col}' not found in gateway_configs table definition"
            )

    def test_gateway_name_has_unique_constraint(self):
        """
        RED TEST: gateway_configs.gateway_name must have UNIQUE constraint.
        FAIL until migration adds unique=True or explicit ALTER TABLE constraint.
        """
        from pathlib import Path

        migration_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "migrations"
            / "versions"
            / "002_add_gateway_configs.py"
        )
        source = migration_path.read_text()

        assert "unique=True" in source or "UNIQUE" in source.upper(), (
            "gateway_name must have UNIQUE constraint"
        )

        # Verify the constraint name is handled for idempotent case
        # If table existed before migration, constraint may need explicit ADD
        assert "_constraint_exists" in source or "ADD CONSTRAINT" in source, (
            "Migration should handle existing table case"
        )

    def test_migration_has_correct_revision_chain(self):
        """
        RED TEST: 002_add_gateway_configs must have down_revision = "001_create_payment_tables".
        FAIL until revision chain is correctly linked.
        """
        from pathlib import Path

        migration_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "migrations"
            / "versions"
            / "002_add_gateway_configs.py"
        )
        source = migration_path.read_text()

        assert 'down_revision = "001_create_payment_tables"' in source, (
            "down_revision must point to 001_create_payment_tables"
        )
        assert 'revision = "002_add_gateway_configs"' in source, (
            "revision ID must be 002_add_gateway_configs"
        )

    def test_gateway_configs_is_idempotent(self):
        """
        RED TEST: Migration must handle idempotent re-runs.
        FAIL until migration implements _table_exists check and handles existing unique constraint.
        """
        from pathlib import Path

        migration_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "migrations"
            / "versions"
            / "002_add_gateway_configs.py"
        )
        source = migration_path.read_text()

        assert "_table_exists" in source, (
            "_table_exists function not found for idempotency"
        )

        # Must also handle constraint existence check for the unique constraint
        # on gateway_name when table already exists from a prior run
        assert "_constraint_exists" in source or (
            "_table_exists" in source and "unique" in source.lower()
        ), "Migration should handle unique constraint for idempotent re-run"

    def test_downgrade_drops_gateway_configs(self):
        """
        RED TEST: Downgrade must drop gateway_configs table.
        FAIL until downgrade implements correct drop.
        """
        from pathlib import Path

        migration_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "migrations"
            / "versions"
            / "002_add_gateway_configs.py"
        )
        source = migration_path.read_text()

        downgrade_start = source.find("def downgrade")
        assert downgrade_start != -1, "downgrade() function not found"

        downgrade_body = source[downgrade_start:]
        assert 'drop_table("gateway_configs")' in downgrade_body, (
            "gateway_configs drop not found in downgrade"
        )


class TestMigrationIntegration:
    """Integration tests verifying the complete migration chain."""

    def test_both_migrations_have_table_exists_helper(self):
        """
        RED TEST: Both migrations must implement _table_exists for idempotency.
        FAIL until both migrations implement the helper.
        """
        from pathlib import Path

        base = Path(__file__).parent.parent.parent / "src" / "migrations" / "versions"

        for filename in ["001_create_payment_tables.py", "002_add_gateway_configs.py"]:
            path = base / filename
            source = path.read_text()
            assert "_table_exists" in source, (
                f"{filename} must implement _table_exists for idempotency"
            )

    def test_migration_files_exist(self):
        """
        RED TEST: Both migration files must exist in the correct location.
        FAIL until files are created.
        """
        from pathlib import Path

        base = Path(__file__).parent.parent.parent / "src" / "migrations" / "versions"

        assert (base / "001_create_payment_tables.py").exists(), (
            "001_create_payment_tables.py not found"
        )
        assert (base / "002_add_gateway_configs.py").exists(), (
            "002_add_gateway_configs.py not found"
        )

    def test_no_sqlalchemy_orm_imports_in_migrations(self):
        """
        GREEN TEST: Migrations should use Alembic op API, not ORM models.
        This ensures migrations are standalone and don't import app models.
        """
        import re
        from pathlib import Path

        base = Path(__file__).parent.parent.parent / "src" / "migrations" / "versions"

        for filename in ["001_create_payment_tables.py", "002_add_gateway_configs.py"]:
            path = base / filename
            source = path.read_text()

            # These imports are NOT allowed — migrations must be model-independent
            assert "from src.models" not in source, (
                f"{filename} must not import from src.models"
            )
            assert "from src.models import" not in source, (
                f"{filename} must not import from src.models"
            )
            # Check for Base as a Python identifier (not as substring in strings/comments)
            # We check for "Base.metadata" or "Base(" which would indicate ORM usage
            assert not re.search(r"\bBase\s*\.metadata\b", source), (
                f"{filename} must not reference Base.metadata"
            )
            assert not re.search(r"\bBase\s*\(", source), (
                f"{filename} must not instantiate Base"
            )


# Pytest configuration
pytest_plugins = []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
