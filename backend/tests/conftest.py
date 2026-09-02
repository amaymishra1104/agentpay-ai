from pathlib import Path
import pytest

from app.db.database import SessionLocal, init_db
from app.services.auth_service import create_session_token
from app.services.catalog_service import _invalidate_catalog_caches

PRODUCTS_FILE = Path(__file__).resolve().parents[2] / "data" / "products.json"


def get_auth_headers(customer_id: str = "c_demo_001") -> dict:
    token = create_session_token(customer_id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session", autouse=True)
def preserve_seed_products():
    """
    Backs up data/products.json before test session and restores it after test session.
    """
    if PRODUCTS_FILE.exists():
        original_content = PRODUCTS_FILE.read_text(encoding="utf-8")
        try:
            yield
        finally:
            PRODUCTS_FILE.write_text(original_content, encoding="utf-8")
            _invalidate_catalog_caches()
    else:
        yield


@pytest.fixture(scope="function")
def db_session():
    init_db()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def pytest_configure(config):
    config.addinivalue_line("markers", "live_groq: mark test as live groq test")


def pytest_collection_modifyitems(config, items):
    markexpr = config.getoption("markexpr")
    if "live_groq" in markexpr:
        return

    skip_live = pytest.mark.skip(reason="need -m live_groq to run")
    for item in items:
        if "live_groq" in item.keywords:
            item.add_marker(skip_live)
