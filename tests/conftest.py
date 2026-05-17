"""
Shared pytest fixtures.
Tests that touch the database use the `db_conn` fixture.
Set POSTGRES_PASSWORD env var if needed (default: empty for trust auth).
"""

import os
import pytest
import psycopg2
import psycopg2.extras


@pytest.fixture(scope="session")
def db_conn():
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        database=os.getenv("POSTGRES_DB", "ecommerce"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def db_cur(db_conn):
    cur = db_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    yield cur
    cur.close()
