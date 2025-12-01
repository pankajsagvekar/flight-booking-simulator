from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite:///./flights.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


def _table_columns(conn, table_name: str) -> set:
    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def _ensure_column(conn, table: str, column: str, ddl: str):
    columns = _table_columns(conn, table)
    if column not in columns:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))


def ensure_schema_migrations():
    """
    SQLite does not auto-migrate with SQLAlchemy metadata. This helper runs
    lightweight ALTER TABLE statements so existing environments pick up the new
    booking- and inventory-related columns without manual intervention.
    """
    with engine.begin() as conn:
        booking_columns = {
            "pnr": "pnr TEXT",
            "status": "status TEXT DEFAULT 'HOLD'",
            "payment_status": "payment_status TEXT DEFAULT 'PENDING'",
            "passenger_manifest": "passenger_manifest TEXT",
            "contact_phone": "contact_phone TEXT",
            "total_amount": "total_amount FLOAT DEFAULT 0",
            "payment_reference": "payment_reference TEXT",
            "currency": "currency TEXT DEFAULT 'INR'",
            "payment_attempts": "payment_attempts INTEGER DEFAULT 0",
            "flight_cache_id": "flight_cache_id INTEGER",
            "hold_expires_at": "hold_expires_at DATETIME",
            "created_at": "created_at DATETIME DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP",
        }
        for name, ddl in booking_columns.items():
            _ensure_column(conn, "bookings", name, ddl)

        flight_columns = {
            "airline": "airline TEXT",
        }
        for name, ddl in flight_columns.items():
            _ensure_column(conn, "flight_cache", name, ddl)
