from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

if settings.database_url.startswith("sqlite"):
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


# Import model modules so their metadata is registered before create_all().
from app.db import models  # noqa: F401,E402


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    
    # Safely alter database to add columns and unique indices if they don't exist
    from sqlalchemy import text
    with engine.begin() as conn:
        for col, col_type in [
            ("confirmed_at", "DATETIME"),
            ("packed_at", "DATETIME"),
            ("shipped_at", "DATETIME"),
            ("delivered_at", "DATETIME"),
            ("cancelled_at", "DATETIME"),
        ]:
            try:
                conn.execute(text(f"ALTER TABLE orders ADD COLUMN {col} {col_type}"))
            except Exception:
                # Column already exists, ignore
                pass

        # Create unique indexes if needed
        indexes = [
            ("idx_orders_cart_id_unique", "CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_cart_id_unique ON orders(cart_id)"),
            ("idx_orders_payment_id_unique", "CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_payment_id_unique ON orders(payment_id) WHERE payment_id IS NOT NULL"),
            ("idx_payment_orders_rzp_order_id", "CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_orders_rzp_order_id ON payment_orders(razorpay_order_id)"),
            ("idx_webhook_events_event_id", "CREATE UNIQUE INDEX IF NOT EXISTS idx_webhook_events_event_id ON webhook_events(event_id)"),
        ]
        for idx_name, idx_sql in indexes:
            try:
                conn.execute(text(idx_sql))
            except Exception:
                pass

init_db()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
