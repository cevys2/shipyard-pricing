import logging
import os

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.services import pencarian

logger = logging.getLogger(__name__)


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


@event.listens_for(engine, "connect")
def _atur_ambang_trgm(dbapi_conn, _catatan) -> None:
    """Setel ambang operator `<%` sekali per koneksi baru, bukan tiap query.

    Operator `<%` di pencarian memakai ambang dari GUC ini. Menyetelnya per query berarti
    satu round-trip tambahan ke Railway untuk setiap ketikan di kotak cari; per koneksi
    berarti sekali saja lalu ikut dipakai ulang oleh pool.

    Dilewati kalau pg_trgm belum ketahuan terpasang -- menyetel parameter milik ekstensi
    yang tidak ada bikin koneksinya gagal, dan itu akan menjatuhkan seluruh aplikasi,
    bukan cuma pencariannya.
    """
    if not pencarian.trgm_siap():
        return
    try:
        cur = dbapi_conn.cursor()
        cur.execute(f"SET pg_trgm.word_similarity_threshold = {pencarian.AMBANG}")
        cur.close()
    except Exception:  # noqa: BLE001 -- driver bisa melempar apa saja di sini
        logger.warning(
            "Gagal menyetel pg_trgm.word_similarity_threshold; pencarian jatuh ke ambang "
            "bawaan 0.6 (lebih ketat, salah ketik berat tidak ketemu).",
            exc_info=True,
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


def ensure_ahsp_tables() -> None:
    """Langkah 3 Sesi 3.1: ahsp + ahsp_komponen (tab Struktur Biaya).

    Berdiri sendiri: `tabel_katalog_harga` tidak disentuh, dan CHECK constraint
    `sumber_daya.jenis` tidak diubah -- empat jenis yang sudah ada sudah menampung
    semua komponen (bagian 2 docs/rencana-langkah-3-struktur-biaya.md).

    Baris komponen sengaja menyimpan qty/shift/jml_hari terpisah, bukan satu koefisien
    hasil perkalian. "4 orang, 1 shift, 0,07 hari" bisa diperiksa orang lapangan;
    "0,28" tidak bisa.
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS ahsp (
                    id          SERIAL PRIMARY KEY,
                    uraian      TEXT NOT NULL,
                    satuan      TEXT NOT NULL,
                    jenis_jual  TEXT NOT NULL DEFAULT 'JASA'
                                CHECK (jenis_jual IN ('JASA','MATERIAL')),
                    kategori    TEXT,
                    parameter   JSONB NOT NULL DEFAULT '{}'::jsonb,
                    catatan     TEXT,
                    aktif       BOOLEAN NOT NULL DEFAULT TRUE,
                    dibuat_pada TIMESTAMPTZ NOT NULL DEFAULT now(),
                    diubah_pada TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )
        # Normalisasi yang sama persis dengan sd_identitas_sql() -- aturan "dianggap kembar"
        # harus seragam di seluruh aplikasi, kalau tidak yang satu menolak apa yang lain terima.
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_ahsp_uraian ON ahsp "
                "(lower(regexp_replace(trim(uraian), '\\s+', ' ', 'g')), lower(trim(satuan)))"
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS ahsp_komponen (
                    id             SERIAL PRIMARY KEY,
                    ahsp_id        INT NOT NULL REFERENCES ahsp(id) ON DELETE CASCADE,
                    sumber_daya_id INT NOT NULL REFERENCES sumber_daya(id),
                    kelompok       TEXT NOT NULL
                                   CHECK (kelompok IN ('BAHAN','UPAH','ALAT','KONSUMABEL')),
                    qty            NUMERIC(18,6) NOT NULL DEFAULT 1 CHECK (qty > 0),
                    shift          NUMERIC(18,6) NOT NULL DEFAULT 1 CHECK (shift > 0),
                    jml_hari       NUMERIC(18,6) NOT NULL DEFAULT 1 CHECK (jml_hari > 0),
                    urutan         INT NOT NULL DEFAULT 0,
                    catatan        TEXT,
                    UNIQUE (ahsp_id, sumber_daya_id, kelompok)
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_ak_ahsp ON ahsp_komponen(ahsp_id)"))


def ensure_partno_unique() -> None:
    """Part number unik per jenis -- part number adalah identitas sebenarnya sebuah material.

    Dijalankan di transaksi sendiri, bukan di dalam `_dedup_sumber_daya()`, karena bisa gagal
    pada data yang belum bersih (satu part number terpakai di dua baris material). Kalau
    gagal, aplikasi tetap jalan: `_identitas_key()` di layer aplikasi sudah memakai aturan
    yang sama, dan index ini cuma jaring pengaman di tingkat DB. Menjatuhkan seluruh aplikasi
    karena jaring pengaman tidak terpasang justru lebih merugikan daripada tidak punya index.
    """
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_sd_partno ON sumber_daya "
                    "(lower(regexp_replace(trim(spesifikasi), '\\s+', ' ', 'g')), jenis) "
                    "WHERE trim(coalesce(spesifikasi, '')) <> ''"
                )
            )
    except Exception as e:  # noqa: BLE001 -- sengaja: kegagalan di sini tidak boleh fatal
        print(
            "[warn] uq_sd_partno tidak bisa dipasang, kemungkinan ada part number kembar di "
            f"sumber_daya. Aplikasi tetap jalan. Detail: {type(e).__name__}: {e}"
        )


# Kolom yang ikut tercari di tiap kotak pencarian. Dipakai bareng oleh definisi index di
# bawah dan oleh service-nya, supaya ekspresi index dan ekspresi query tidak pernah beda.
KOLOM_CARI_MATERIAL = ("nama", "spesifikasi")
KOLOM_CARI_KATALOG = ("uraian_pekerjaan", "kategori_pekerjaan")


def ensure_pencarian_index() -> None:
    """pg_trgm + index GIN buat pencarian yang memaafkan salah ketik.

    Ekstensinya sengaja tidak diwajibkan. Kalau role DB di Railway tidak boleh
    `CREATE EXTENSION`, aplikasi tetap start dan pencarian jatuh ke pencocokan substring
    per kata (lihat services/pencarian.py) -- lebih tumpul, tapi hidup. Menjadikannya
    syarat wajib artinya satu izin DB yang kurang bikin seluruh aplikasi tidak bisa naik.
    """
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    except SQLAlchemyError:
        logger.warning(
            "pg_trgm tidak bisa dipasang -- pencarian tetap jalan tapi tanpa toleransi "
            "salah ketik. Pasang manual sebagai superuser: CREATE EXTENSION pg_trgm;",
            exc_info=True,
        )

    with engine.connect() as conn:
        ada = conn.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
        ).first()
    pencarian.set_trgm(bool(ada))
    if not ada:
        return

    # Koneksi yang terlanjur dibuat sebelum baris di atas (termasuk yang dipakai fungsi ini)
    # melewati listener `_atur_ambang_trgm` karena saat itu status pg_trgm belum ketahuan.
    # Dibuang supaya semua koneksi yang melayani request nanti benar-benar punya ambangnya.
    engine.dispose()

    # Index ekspresi: yang di-index adalah gabungan kolom yang sudah dinormalisasi, persis
    # ekspresi yang dipakai query -- kalau beda sedikit saja, index terpasang tapi tidak
    # pernah tersentuh. Ini bukan kekhawatiran teoretis: versi pertama memakai
    # `word_similarity(...) >= ambang` alih-alih operator `<%`, dan EXPLAIN menunjukkan
    # SELURUH index pencarian tidak terpakai -- satu cabang OR yang tidak bisa di-index
    # memaksa pindai penuh, yang bikin index cabang-cabang lainnya jadi percuma.
    index = (
        ("idx_sd_cari_trgm", "sumber_daya", pencarian.jerami_sql(KOLOM_CARI_MATERIAL)),
        ("idx_sd_cari_rapat", "sumber_daya", pencarian.rapat_sql(KOLOM_CARI_MATERIAL)),
        ("idx_katalog_cari_trgm", settings.catalog_table, pencarian.jerami_sql(KOLOM_CARI_KATALOG)),
        ("idx_katalog_cari_rapat", settings.catalog_table, pencarian.rapat_sql(KOLOM_CARI_KATALOG)),
    )
    for nama, tabel, ekspresi in index:
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        f"CREATE INDEX IF NOT EXISTS {nama} ON {tabel} "
                        f"USING gin (({ekspresi}) gin_trgm_ops)"
                    )
                )
        except SQLAlchemyError:
            # Satu index gagal (mis. tabelnya belum ada di DB kosong) tidak boleh
            # menggagalkan yang lain -- semuanya cuma optimasi, bukan syarat kebenaran.
            logger.warning("Index pencarian %s gagal dibuat", nama, exc_info=True)


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
