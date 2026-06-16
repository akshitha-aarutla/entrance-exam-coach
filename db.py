"""
db.py — Database abstraction layer.

Uses SQLite locally (zero-config, for development on your own laptop)
and PostgreSQL automatically when deployed (Render/Railway/Heroku-style
platforms set a DATABASE_URL environment variable pointing to a managed
Postgres instance).

This lets app.py write ONE set of SQL queries (using '?' placeholders,
SQLite style) and have them work transparently against Postgres too —
this module rewrites '?' to '%s' and translates a couple of syntax
differences (AUTOINCREMENT, etc.) automatically.
"""

import os

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USING_POSTGRES = bool(DATABASE_URL)

if USING_POSTGRES:
    import psycopg2
    import psycopg2.extras

    # Render's DATABASE_URL sometimes starts with "postgres://" but
    # psycopg2 expects "postgresql://" — normalize it.
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    import sqlite3
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    SQLITE_PATH = os.path.join(BASE_DIR, "database.db")


class CursorWrapper:
    """
    Wraps a real DB cursor so the rest of app.py can keep using SQLite-style
    '?' placeholders and dict-like row access, even when actually running
    on Postgres (which uses '%s' placeholders).
    """
    def __init__(self, real_cursor):
        self._cursor = real_cursor

    def execute(self, query, params=()):
        if USING_POSTGRES:
            query = query.replace("?", "%s")
        return self._cursor.execute(query, params)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def lastrowid(self):
        if USING_POSTGRES:
            # Postgres needs RETURNING id; handled separately where needed.
            return None
        return self._cursor.lastrowid


class ConnectionWrapper:
    def __init__(self, real_conn):
        self._conn = real_conn

    def cursor(self):
        if USING_POSTGRES:
            real_cursor = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            real_cursor = self._conn.cursor()
        return CursorWrapper(real_cursor)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def get_db():
    """Return a database connection (Postgres if DATABASE_URL is set, else SQLite)."""
    if USING_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        return ConnectionWrapper(conn)
    else:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        return ConnectionWrapper(conn)


def _translate_schema(create_table_sql):
    """
    Translate SQLite-flavored CREATE TABLE syntax to Postgres-flavored
    syntax when running on Postgres.
    """
    if not USING_POSTGRES:
        return create_table_sql

    sql = create_table_sql
    sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    return sql


def init_db():
    """Create tables if they don't exist (works for both SQLite and Postgres)."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute(_translate_schema("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """))

    cur.execute(_translate_schema("""
        CREATE TABLE IF NOT EXISTS test_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            exam_type TEXT NOT NULL,
            subject TEXT NOT NULL,
            score INTEGER NOT NULL,
            total_questions INTEGER NOT NULL,
            weak_topics_json TEXT,
            test_date TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """))

    cur.execute(_translate_schema("""
        CREATE TABLE IF NOT EXISTS timetables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            exam_date TEXT NOT NULL,
            days_left INTEGER NOT NULL,
            plan_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """))

    conn.commit()
    conn.close()
