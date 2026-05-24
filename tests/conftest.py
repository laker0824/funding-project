import pytest
import os, sys, tempfile

os.environ["TESTING"] = "1"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import db

TEST_DB = os.path.join(tempfile.gettempdir(), "test_funding.db")
db.DB_PATH = TEST_DB


@pytest.fixture(autouse=True)
def clean_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    db.init_db()
    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
