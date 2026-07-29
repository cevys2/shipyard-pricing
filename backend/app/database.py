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
        _dedup_sumber_daya(conn)


# Identitas material = nama + spesifikasi + satuan, dinormalisasi (case & spasi
# berlebih diabaikan). Dipakai bareng oleh migrasi dedup dan lookup di bulk_create,
# jadi definisinya HARUS satu tempat -- kalau beda, unique index bakal nolak baris
# yang menurut aplikasi belum ada.
def sd_identitas_sql(alias: str = "") -> str:
    p = f"{alias}." if alias else ""
    return (
        f"lower(regexp_replace(trim({p}nama), '\\s+', ' ', 'g')), "
        f"lower(regexp_replace(trim(coalesce({p}spesifikasi, '')), '\\s+', ' ', 'g')), "
        f"lower(trim({p}satuan)), "
        f"{p}jenis"
    )


def _dedup_sumber_daya(conn) -> None:
    """Gabungkan material kembar jadi satu master, lalu kunci pakai unique index.

    Kenapa perlu: `bulk_create` dulu selalu INSERT master baru, jadi paste batch yang
    sama dua kali bikin material yang identik jadi 2 baris `sumber_daya` terpisah --
    masing-masing dengan riwayat harganya sendiri. Akibatnya riwayat harga satu barang
    terpecah dan tren harganya tidak akan pernah terbentuk. Di data produksi ini
    kejadian: 11 item ke-input 3x jadi 33 baris.

    Idempoten, dan di-skip total setelah unique index terpasang (index-nya sendiri yang
    menjamin duplikat nggak bisa muncul lagi) supaya nggak full-scan tiap app start.
    """
    already_locked = conn.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname = 'uq_sd_identitas'")
    ).first()
    if already_locked:
        return

    identitas = sd_identitas_sql()

    # 1. Alihkan semua riwayat harga ke master dengan id terkecil di tiap grup kembar.
    conn.execute(
        text(
            f"""
            WITH grup AS (
                SELECT id, MIN(id) OVER (PARTITION BY {identitas}) AS induk
                FROM   sumber_daya
            )
            UPDATE sumber_daya_harga h
            SET    sumber_daya_id = g.induk
            FROM   grup g
            WHERE  h.sumber_daya_id = g.id AND g.induk <> g.id
            """
        )
    )

    # 2. Hapus master kembar yang riwayat harganya sudah dipindah di langkah 1.
    conn.execute(
        text(
            f"""
            DELETE FROM sumber_daya
            WHERE  id NOT IN (SELECT MIN(id) FROM sumber_daya GROUP BY {identitas})
            """
        )
    )

    # 3. Langkah 1 bikin baris harga yang persis sama menumpuk di master yang sama.
    #    Baris identik = satu kejadian harga yang ke-input berulang, BUKAN perubahan
    #    harga -- kalau dibiarkan, chart tren nampilin titik palsu. Sisakan satu.
    conn.execute(
        text(
            """
            DELETE FROM sumber_daya_harga a
            USING  sumber_daya_harga b
            WHERE  a.id > b.id
              AND  a.sumber_daya_id = b.sumber_daya_id
              AND  a.harga_satuan   = b.harga_satuan
              AND  a.mata_uang      = b.mata_uang
              AND  a.berlaku_dari   = b.berlaku_dari
              AND  a.tahun_pembelian = b.tahun_pembelian
              AND  a.supplier_id IS NOT DISTINCT FROM b.supplier_id
              AND  a.nama_kapal  IS NOT DISTINCT FROM b.nama_kapal
            """
        )
    )

    conn.execute(
        text(f"CREATE UNIQUE INDEX IF NOT EXISTS uq_sd_identitas ON sumber_daya ({identitas})")
    )


def ensure_audit_table() -> None:
    """Jejak siapa mengubah apa, buat katalog material DAN tabel_katalog_harga.

    Sengaja tabel terpisah & append-only, bukan kolom `diubah_oleh` di tabel aslinya:
    (a) tabel_katalog_harga tidak boleh diubah strukturnya, (b) yang menarik justru
    riwayat perubahannya, bukan cuma penyunting terakhir.
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id          BIGSERIAL PRIMARY KEY,
                    aktor       TEXT NOT NULL,
                    aksi        TEXT NOT NULL,
                    entitas     TEXT NOT NULL,
                    jumlah      INT  NOT NULL DEFAULT 1,
                    detail      JSONB,
                    dibuat_pada TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_audit_waktu ON audit_log(dibuat_pada DESC)")
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_audit_entitas "
                "ON audit_log(entitas, dibuat_pada DESC)"
            )
        )
