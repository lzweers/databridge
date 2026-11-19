"""Minimal non-destructive v0.1 -> v0.2 upgrade for the local demo.

In a production system this would be an Alembic revision.  Keeping it small
allows an existing Docker volume from the v0.1 starter to survive this update.
"""
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def upgrade_legacy_schema(engine: Engine) -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        if "supplier_offers" not in inspector.get_table_names():
            return  # Fresh DB: SQLAlchemy create_all will create v0.2 directly.
        columns = {col["name"] for col in inspector.get_columns("supplier_offers")}
        if "price_eur" in columns and "price_amount" not in columns:
            connection.execute(text("ALTER TABLE supplier_offers RENAME COLUMN price_eur TO price_amount"))
        if "currency" not in columns:
            connection.execute(text(
                "ALTER TABLE supplier_offers ADD COLUMN currency VARCHAR(3) NOT NULL DEFAULT 'EUR'"
            ))
