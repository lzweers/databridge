"""Safety boundary: test suite is forbidden from using the application's PostgreSQL DB.

pytest loads conftest.py before collecting test modules. In v0.5.1,
importing benchmark.py during collection initialized app.database before a
module-level DATABASE_URL override, causing destructive fixtures to target
PostgreSQL. This file prevents that ordering bug.
"""
import os

# Select an isolated local file before *any* app/benchmark module import.
os.environ["DATABASE_URL"] = "sqlite:///./databridge-test.db"

from app.database import engine

if engine.dialect.name != "sqlite":
    raise RuntimeError("UNSAFE TEST CONFIGURATION: refusing to test against a non-SQLite database")
