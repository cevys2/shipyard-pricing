import logging
import os
import re

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.seed_kategori import baris_alias, baris_kategori
from app.services import pencarian

logger = logging.getLogger(__name__)

# Yang boleh masuk ke kategori_norm_sql(): nama kolom (`kategori`, `t.kategori_pekerjaan`)
# atau penanda bind parameter (`:kategori`). Keduanya ikut ke dalam SQL apa adanya dan tidak
# bisa di-parameterize, jadi yang dijaga adalah bentuknya. Semua pemanggilnya literal di
# kode, tidak ada yang datang dari request.
_ARGUMEN_NORM = re.compile(r"^:?[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")


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
                f"""
                CREATE VIEW v_harga_terkini AS
                SELECT DISTINCT ON (sumber_daya_id)
                       sumber_daya_id, supplier_id, harga_satuan, mata_uang, nama_kapal,
                       tahun_pembelian, berlaku_dari, no_dokumen
                FROM   sumber_daya_harga
                ORDER  BY sumber_daya_id, {urutan_harga_sql()}
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


# Urutan "titik harga mana yang paling baru". SATU definisi, dipakai enam tempat.
#
# `tahun_pembelian` yang menentukan, bukan `berlaku_dari`. Sebabnya: `berlaku_dari` boleh
# dikosongkan di tempelan, dan kalau kosong dia jatuh ke `date.today()` -- jadi sering dia
# bukan fakta soal pembeliannya, melainkan fakta soal kapan orang sempat menginput. Waktu
# kolom itu yang mengurutkan, faktur 2023 yang baru diinput hari ini mengalahkan pembelian
# 2025 yang diinput minggu lalu, lalu ikut terbawa ke harga komponen AHSP yang hidup
# mengikuti `v_harga_terkini`. Di cadangan 9 Agustus, 9 dari 68 baris harga punya
# `berlaku_dari` di tahun yang berbeda dari `tahun_pembelian`.
#
# `berlaku_dari` tetap ikut sebagai pemecah seri: dia tanggal penuh, jadi lebih presisi
# untuk membedakan dua pembelian di tahun yang sama -- selama memang diisi.
def urutan_harga_sql(alias: str = "", *, terbaru_dulu: bool = True) -> str:
    if alias and not _ARGUMEN_NORM.match(alias):
        raise ValueError(f"Bukan alias tabel yang sah: {alias!r}")
    p = f"{alias}." if alias else ""
    arah = "DESC" if terbaru_dulu else "ASC"
    return f"{p}tahun_pembelian {arah}, {p}berlaku_dari {arah}, {p}id {arah}"


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


# Kategori di Excel sumbernya berantakan: "DOCKING\n  dan UNDOCKING" dan "Docking dan
# Undocking" itu kategori yang sama. Dirapikan saat dibaca -- newline/spasi beruntun jadi
# satu spasi, lalu huruf besar semua.
#
# chr(160) = non-breaking space, sering ikut kebawa dari sel Excel. `trim()` dan `\s` versi
# POSIX TIDAK menganggapnya spasi, jadi tanpa replace ini "DOCKING DAN UNDOCKING" dan
# "DOCKING DAN UNDOCKING<nbsp>" tetap terhitung dua kategori berbeda.
#
# Definisinya di sini, satu tempat, karena dipakai DUA pihak yang harus sepakat persis:
# analitik (mengelompokkan saat membaca) dan alias di tabel `kategori_alias` (yang isinya
# disimpan dalam bentuk hasil normalisasi ini). Kalau keduanya beda satu karakter saja,
# tidak ada error yang muncul -- resolver cuma diam-diam tidak menemukan pasangan, dan
# `kategori_id` tinggal NULL. Itu kegagalan yang paling mahal di sini karena tak bersuara.
def kategori_norm_sql(kolom: str = "kategori_pekerjaan") -> str:
    if not _ARGUMEN_NORM.match(kolom):
        raise ValueError(f"Bukan nama kolom atau bind parameter yang sah: {kolom!r}")
    return f"upper(btrim(regexp_replace(replace({kolom}, chr(160), ' '), '\\s+', ' ', 'g')))"


def ensure_kategori_table() -> None:
    """Master kategori pekerjaan kanonik + alias, lalu isi `tabel_katalog_harga.kategori_id`.

    Dua lapis, sengaja dipisah: `kategori_alias` yang memetakan otomatis, dan kolom
    `kategori_id` tempat hasilnya mendarat. Manusia boleh menimpa hasilnya dengan menyetel
    `kategori_sumber = 'manual'`, dan resolver tidak pernah menyentuh baris bertanda itu.

    Isi `kategori_pekerjaan` TIDAK PERNAH ditulis ulang -- itu catatan apa yang benar-benar
    tertulis di laporan asli. Koreksi mendarat di `kategori_id`, bukan dengan mengedit
    teks aslinya (keputusan K-6, docs/bundel-kategori-claude-code.md).
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS kategori (
                    id     SERIAL PRIMARY KEY,
                    nama   TEXT NOT NULL UNIQUE,
                    urutan INT  NOT NULL DEFAULT 0,
                    aktif  BOOLEAN NOT NULL DEFAULT TRUE
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS kategori_alias (
                    id          SERIAL PRIMARY KEY,
                    kategori_id INT  NOT NULL REFERENCES kategori(id) ON DELETE CASCADE,
                    alias       TEXT NOT NULL UNIQUE
                )
                """
            )
        )
        conn.execute(
            text(
                "INSERT INTO kategori (nama, urutan) VALUES (:nama, :urutan) "
                "ON CONFLICT (nama) DO UPDATE SET urutan = EXCLUDED.urutan "
                "WHERE kategori.urutan IS DISTINCT FROM EXCLUDED.urutan"
            ),
            baris_kategori(),
        )
        # DO UPDATE, bukan DO NOTHING seperti di arsip docs/seed_kategori.sql: dengan
        # DO NOTHING, memindahkan sebuah alias ke kategori lain tidak akan pernah berlaku
        # di database yang sudah terisi -- diam, tanpa error. Asumsi K-A1 ("ubah 1 baris
        # alias") mensyaratkan perubahan itu benar-benar sampai. `IS DISTINCT FROM` bikin
        # jalan yang lazim (tidak ada yang berubah) tetap jadi no-op, bukan menulis ulang
        # 83 baris tiap kali app start.
        conn.execute(
            text(
                "INSERT INTO kategori_alias (kategori_id, alias) "
                "SELECT id, :alias FROM kategori WHERE nama = :nama "
                "ON CONFLICT (alias) DO UPDATE SET kategori_id = EXCLUDED.kategori_id "
                "WHERE kategori_alias.kategori_id IS DISTINCT FROM EXCLUDED.kategori_id"
            ),
            baris_alias(),
        )

    # `tabel_katalog_harga` tidak dibuat di repo ini -- dia sudah ada sebelum aplikasi ini
    # lahir. Di database kosong (mis. dev baru) tabelnya belum tentu ada, dan itu tidak
    # boleh menjatuhkan startup: master kategorinya sendiri sudah berhasil dibuat di atas.
    with engine.begin() as conn:
        ada = conn.execute(
            text("SELECT to_regclass(:t)"), {"t": f"public.{settings.catalog_table}"}
        ).scalar()
        if ada is None:
            logger.warning(
                "%s belum ada -- kolom kategori_id dilewati.", settings.catalog_table
            )
            return
        # Penambahan kolom nullable. Kolom yang sudah ada tidak disentuh sama sekali.
        # CHECK-nya menempel di ADD COLUMN IF NOT EXISTS, jadi ikut dilewati kalau kolomnya
        # sudah ada -- tidak perlu guard pg_constraint seperti `chk_sdh_mata_uang`, yang
        # dibutuhkan justru karena constraint di sana dipasang lewat ADD CONSTRAINT terpisah.
        conn.execute(
            text(
                f"""
                ALTER TABLE {settings.catalog_table}
                  ADD COLUMN IF NOT EXISTS kategori_id     INT REFERENCES kategori(id),
                  ADD COLUMN IF NOT EXISTS kategori_sumber TEXT NOT NULL DEFAULT 'alias'
                                           CHECK (kategori_sumber IN ('alias','manual'))
                """
            )
        )
        conn.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS idx_tkh_kategori "
                f"ON {settings.catalog_table}(kategori_id)"
            )
        )
    selaraskan_kategori()


def selaraskan_kategori() -> int:
    """Isi `kategori_id` dari `kategori_alias`. Mengembalikan jumlah baris yang berubah.

    Hanya menyentuh baris `kategori_sumber = 'alias'` -- koreksi manusia (`'manual'`) kebal,
    termasuk kalau ada baris lain berteks kategori sama yang tetap ikut resolver.

    `IS DISTINCT FROM` di akhir bikin pemanggilan kedua jadi nol baris, bukan menulis ulang
    isi yang sama. Jadi aman dipanggil tiap app start.
    """
    with engine.begin() as conn:
        hasil = conn.execute(
            text(
                f"""
                UPDATE {settings.catalog_table} t
                SET    kategori_id = a.kategori_id
                FROM   kategori_alias a
                WHERE  t.kategori_sumber = 'alias'
                  AND  {kategori_norm_sql("t.kategori_pekerjaan")} = a.alias
                  AND  t.kategori_id IS DISTINCT FROM a.kategori_id
                """
            )
        )
    return hasil.rowcount


def ensure_ahsp_tables() -> None:
    """Langkah 3 Sesi 3.1: ahsp + ahsp_komponen (tab Struktur Biaya).

    WAJIB dipanggil sesudah `ensure_material_tables()` DAN `ensure_kategori_table()`:
    `ahsp_komponen` punya foreign key ke `sumber_daya`, dan `ahsp.kategori_id` ke `kategori`.
    Urutannya dijaga di `main.py`. Sengaja tidak dibungkus penjaga "kalau tabelnya belum ada,
    lewati saja" -- itu cuma menunda kegagalannya sampai baris AHSP pertama disimpan, dengan
    pesan yang jauh lebih sulit dibaca.

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

    _ikat_kategori_ahsp()


def _ikat_kategori_ahsp() -> None:
    """Sesi K3A: `ahsp.kategori` yang teks bebas dapat pasangan `kategori_id`.

    Kolom `kategori` lama sengaja TIDAK di-drop. Dia jadi catatan apa yang diketik waktu
    baris itu dibuat, sama peranannya dengan `kategori_pekerjaan` di katalog jasa.

    Backfill-nya hanya menyentuh baris yang `kategori_id`-nya masih NULL. Bukan sekadar
    hemat: sesudah form pakai dropdown, pengguna bisa memilih kategori yang berbeda dari
    teks lama, dan mengisi ulang tiap app start akan menarik pilihannya balik ke teks itu
    -- diam-diam, tiap deploy.
    """
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE ahsp ADD COLUMN IF NOT EXISTS kategori_id INT REFERENCES kategori(id)")
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_ahsp_kategori ON ahsp(kategori_id)"))
        terisi = conn.execute(
            text(
                f"""
                UPDATE ahsp a
                SET    kategori_id = al.kategori_id
                FROM   kategori_alias al
                WHERE  a.kategori_id IS NULL
                  AND  {kategori_norm_sql("a.kategori")} = al.alias
                """
            )
        ).rowcount
        # Yang gagal tidak ditebak dan tidak dikosongkan -- cuma dilaporkan. Kategori AHSP
        # boleh kosong, jadi yang menarik hanya baris yang PUNYA teks tapi tidak dikenali.
        gagal = conn.execute(
            text(
                "SELECT DISTINCT kategori FROM ahsp "
                "WHERE kategori_id IS NULL AND btrim(coalesce(kategori, '')) <> '' "
                "ORDER BY kategori"
            )
        ).scalars().all()

    if terisi:
        logger.info("Backfill kategori AHSP: %d baris terisi.", terisi)
    if gagal:
        logger.warning(
            "Backfill kategori AHSP: %d sebutan tidak dikenali, barisnya dibiarkan kosong: %s",
            len(gagal),
            ", ".join(repr(g) for g in gagal),
        )


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
