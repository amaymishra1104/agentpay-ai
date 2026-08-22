import pytest
from app.db.database import SessionLocal, init_db

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

