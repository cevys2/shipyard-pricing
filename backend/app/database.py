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
        # kode ternyata "practically useless" buat klien (Part No. asli lebih pas di
        # spesifikasi) -- drop di DB yang sudah ada, sekaligus dihilangkan dari CREATE
        # TABLE di atas biar instalasi baru juga bersih.
        conn.execute(text("ALTER TABLE sumber_daya DROP COLUMN IF EXISTS kode"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sd_jenis ON sumber_daya(jenis)"))
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS sumber_daya_harga (
                    id              SERIAL PRIMARY KEY,
                    sumber_daya_id  INT NOT NULL REFERENCES sumber_daya(id) ON DELETE CASCADE,
                    supplier_id     INT REFERENCES supplier(id),
                    harga_satuan    NUMERIC(18,2) NOT NULL CHECK (harga_satuan > 0),
                    mata_uang       TEXT NOT NULL DEFAULT 'IDR' CHECK (mata_uang IN ('IDR','EUR','USD')),
                    nama_kapal      TEXT,
                    tahun_pembelian INT NOT NULL,
                    berlaku_dari    DATE NOT NULL,
                    sumber          TEXT,
                    no_dokumen      TEXT,
                    catatan         TEXT,
                    dibuat_pada     TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )
        # nama_kapal: harga/pembelian material biasanya buat kapal tertentu (bukan sifat
        # tetap materialnya, jadi ini di histori harga -- bukan di master sumber_daya).
        conn.execute(text("ALTER TABLE sumber_daya_harga ADD COLUMN IF NOT EXISTS nama_kapal TEXT"))
        # tahun_pembelian: acuan analitik yang sengaja dipisah dari dibuat_pada (auto now()
        # saat insert -- bukan tanggal pembelian asli, apalagi buat data lama yang di-backfill)
        # dan dari berlaku_dari (NOT NULL tapi default ke hari ini kalau dikosongkan -- masalah
        # yang sama, cuma pindah tempat). Kolom lama sudah ada isinya, jadi tambah nullable dulu,
        # backfill dari berlaku_dari, baru di-set NOT NULL.
        conn.execute(text("ALTER TABLE sumber_daya_harga ADD COLUMN IF NOT EXISTS tahun_pembelian INT"))
        conn.execute(
            text(
                "UPDATE sumber_daya_harga SET tahun_pembelian = EXTRACT(YEAR FROM berlaku_dari)::INT "
                "WHERE tahun_pembelian IS NULL"
            )
        )
        conn.execute(text("ALTER TABLE sumber_daya_harga ALTER COLUMN tahun_pembelian SET NOT NULL"))
        # Postgres nggak punya "ADD CONSTRAINT IF NOT EXISTS", jadi guard manual.
        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_sdh_mata_uang') THEN
                        ALTER TABLE sumber_daya_harga
                            ADD CONSTRAINT chk_sdh_mata_uang CHECK (mata_uang IN ('IDR','EUR','USD'));
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_sdh_tahun') THEN
                        ALTER TABLE sumber_daya_harga
                            ADD CONSTRAINT chk_sdh_tahun CHECK (tahun_pembelian BETWEEN 1990 AND 2100);
                    END IF;
                END $$;
                """
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_sdh_sd_tgl "
                "ON sumber_daya_harga(sumber_daya_id, berlaku_dari DESC)"
            )
        )
        # DROP + CREATE (bukan CREATE OR REPLACE) -- Postgres nggak izinin REPLACE
        # mengubah urutan/nama kolom view yang sudah ada, cuma boleh nambah di akhir.
        # View ini nggak ada dependent lain, aman di-drop.
        conn.execute(text("DROP VIEW IF EXISTS v_harga_terkini"))
        conn.execute(
            text(
                """
                CREATE VIEW v_harga_terkini AS
                SELECT DISTINCT ON (sumber_daya_id)
                       sumber_daya_id, supplier_id, harga_satuan, mata_uang, nama_kapal,
                       tahun_pembelian, berlaku_dari, no_dokumen
                FROM   sumber_daya_harga
                ORDER  BY sumber_daya_id, berlaku_dari DESC, id DESC
                """
            )
        )
