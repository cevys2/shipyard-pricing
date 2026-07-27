import os
import secrets
import logging

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import settings

logger = logging.getLogger("app.database")


def normalize_db_url(db_url: str) -> str:
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+pg8000://", 1)
    elif db_url.startswith("postgresql://") and "pg8000" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+pg8000://", 1)
    return db_url


def get_engine() -> Engine:
    db_url = os.environ.get("DATABASE_URL") or settings.database_url
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")
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

            temp_password = secrets.token_urlsafe(12)
            default_hash = hash_password(temp_password)
            conn.execute(
                text(
                    "INSERT INTO users (username, password_hash, role) VALUES ('admin', :pw, 'admin')"
                ),
                {"pw": default_hash},
            )
            logger.warning(
                "Created initial admin user. Username: admin | Temporary password: %s "
                "-- log in and change this immediately (POST /users/password).",
                temp_password,
            )


def ensure_material_tables() -> None:
    """Langkah 1 roadmap: supplier + sumber_daya + sumber_daya_harga (tab Katalog Material).

    kategori/kategori_alias/layanan sengaja belum dibuat -- itu Langkah 2+.
    tabel_katalog_harga tidak disentuh sama sekali.
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS supplier (
                    id      SERIAL PRIMARY KEY,
                    nama    TEXT NOT NULL UNIQUE,
                    kontak  TEXT,
                    catatan TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS sumber_daya (
                    id          SERIAL PRIMARY KEY,
                    kode        TEXT UNIQUE,
                    jenis       TEXT NOT NULL DEFAULT 'BAHAN'
                                CHECK (jenis IN ('BAHAN','UPAH','ALAT','KONSUMABEL')),
                    nama        TEXT NOT NULL,
                    spesifikasi TEXT,
                    satuan      TEXT NOT NULL,
                    aktif       BOOLEAN NOT NULL DEFAULT TRUE,
                    dibuat_pada TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sd_jenis ON sumber_daya(jenis)"))
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS sumber_daya_harga (
                    id             SERIAL PRIMARY KEY,
                    sumber_daya_id INT NOT NULL REFERENCES sumber_daya(id) ON DELETE CASCADE,
                    supplier_id    INT REFERENCES supplier(id),
                    harga_satuan   NUMERIC(18,2) NOT NULL CHECK (harga_satuan > 0),
                    mata_uang      TEXT NOT NULL DEFAULT 'IDR',
                    berlaku_dari   DATE NOT NULL,
                    sumber         TEXT,
                    no_dokumen     TEXT,
                    catatan        TEXT,
                    dibuat_pada    TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_sdh_sd_tgl "
                "ON sumber_daya_harga(sumber_daya_id, berlaku_dari DESC)"
            )
        )
        conn.execute(
            text(
                """
                CREATE OR REPLACE VIEW v_harga_terkini AS
                SELECT DISTINCT ON (sumber_daya_id)
                       sumber_daya_id, supplier_id, harga_satuan, berlaku_dari, no_dokumen
                FROM   sumber_daya_harga
                ORDER  BY sumber_daya_id, berlaku_dari DESC, id DESC
                """
            )
        )
