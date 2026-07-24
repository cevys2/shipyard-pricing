import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import settings


def normalize_db_url(db_url: str) -> str:
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+pg8000://", 1)
    elif db_url.startswith("postgresql://") and "pg8000" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+pg8000://", 1)
    return db_url


def get_engine() -> Engine:
    db_url = os.environ.get("SUPABASE_URL") or settings.supabase_url
    if not db_url:
        raise RuntimeError("SUPABASE_URL is not set")
    return create_engine(
        normalize_db_url(db_url),
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=300,
    )


engine = get_engine()


def ensure_users_table() -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role VARCHAR(20) NOT NULL DEFAULT 'user'
                )
                """
            )
        )
        count = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
        if count == 0:
            from app.auth import hash_password

            default_hash = hash_password("admin123")
            conn.execute(
                text(
                    "INSERT INTO users (username, password_hash, role) VALUES ('admin', :pw, 'admin')"
                ),
                {"pw": default_hash},
            )
