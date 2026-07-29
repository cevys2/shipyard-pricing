"""Analitik baca-saja di atas `tabel_katalog_harga` (harga jual jasa docking).

PENTING: modul ini TIDAK PERNAH menulis ke `tabel_katalog_harga` -- tidak ada INSERT,
UPDATE, DELETE, maupun DDL. Semua normalisasi teks (kategori berantakan, newline di
tengah string) dilakukan di dalam SELECT, bukan dengan membetulkan datanya. Lihat
`docs/catatan-tabel-katalog-harga.md`.
"""

from typing import Any

from sqlalchemy import text

from app.config import settings
from app.database import engine

TABLE = settings.catalog_table

# Kategori di Excel sumbernya berantakan: "DOCKING\n  dan UNDOCKING" dan "Docking dan
# Undocking" itu kategori yang sama. Dirapikan saat dibaca -- newline/spasi beruntun jadi
# satu spasi, lalu huruf besar semua.
#
# chr(160) = non-breaking space, sering ikut kebawa dari sel Excel. `trim()` dan `\s`
# versi POSIX TIDAK menganggapnya spasi, jadi tanpa replace ini "DOCKING DAN UNDOCKING"
# dan "DOCKING DAN UNDOCKING<nbsp>" tetap terhitung dua kategori berbeda.
_KATEGORI_NORM = (
    "upper(btrim(regexp_replace(replace(kategori_pekerjaan, chr(160), ' '), '\\s+', ' ', 'g')))"
)


def tren_harga_jasa(*, kategori: str | None = None, min_sampel: int = 3) -> dict[str, Any]:
    """Median harga jual per kategori pekerjaan per tahun, plus data untuk peringatan bias.

    Median (bukan rata-rata) karena data realisasi docking punya baris ekstrem -- satu
    pekerjaan replating besar bisa menarik rata-rata sekategori.

    `min_sampel` menyaring kombinasi kategori-tahun yang datanya terlalu tipis untuk
    dibaca sebagai tren.
    """
    where_kat = ""
    params: dict[str, Any] = {"min_sampel": min_sampel}
    if kategori and kategori != "Semua":
        where_kat = f"AND {_KATEGORI_NORM} = :kategori"
        params["kategori"] = kategori

    with engine.connect() as conn:
        seri = conn.execute(
            text(
                f"""
                SELECT {_KATEGORI_NORM} AS kategori,
                       tahun,
                       COUNT(*)                                                    AS n_baris,
                       COUNT(DISTINCT nama_kapal)                                  AS n_kapal,
                       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY harga_satuan)   AS median,
                       MIN(harga_satuan)                                           AS minimum,
                       MAX(harga_satuan)                                           AS maksimum
                FROM   {TABLE}
                WHERE  harga_satuan > 0
                  AND  kategori_pekerjaan IS NOT NULL
                  AND  trim(kategori_pekerjaan) NOT IN ('', '-')
                  {where_kat}
                GROUP  BY 1, 2
                HAVING COUNT(*) >= :min_sampel
                ORDER  BY 1, 2
                """
            ),
            params,
        ).mappings().all()

        # Komposisi kapal per tahun: dasar peringatan bahwa "kenaikan harga" bisa
        # sekadar efek berubahnya campuran kapal, bukan inflasi harga.
        per_tahun = conn.execute(
            text(
                f"""
                SELECT tahun,
                       COUNT(*)                   AS n_baris,
                       COUNT(DISTINCT nama_kapal) AS n_kapal
                FROM   {TABLE}
                WHERE  harga_satuan > 0
                GROUP  BY tahun
                ORDER  BY tahun
                """
            )
        ).mappings().all()

        cakupan = conn.execute(
            text(
                f"""
                SELECT COUNT(*) AS total_baris,
                       COUNT(DISTINCT {_KATEGORI_NORM}) AS total_kategori,
                       COUNT(DISTINCT tahun) AS total_tahun
                FROM   {TABLE}
                WHERE  harga_satuan > 0
                """
            )
        ).mappings().first()

    return {
        "seri": [dict(r) for r in seri],
        "per_tahun": [dict(r) for r in per_tahun],
        "cakupan": dict(cakupan) if cakupan else {},
    }


def kategori_options(*, min_sampel: int = 3) -> list[str]:
    """Kategori yang benar-benar punya data lolos `min_sampel`.

    Saringan HAVING-nya harus sama persis dengan `tren_harga_jasa()`. Kalau daftar opsi
    dibuat dari DISTINCT biasa, ada kategori yang bisa dipilih tapi grafiknya kosong --
    tiap tahunnya kurang dari `min_sampel` baris sehingga tersaring habis di sisi data.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT kategori FROM (
                    SELECT {_KATEGORI_NORM} AS kategori, tahun
                    FROM   {TABLE}
                    WHERE  harga_satuan > 0
                      AND  kategori_pekerjaan IS NOT NULL
                      AND  trim(kategori_pekerjaan) NOT IN ('', '-')
                    GROUP  BY 1, 2
                    HAVING COUNT(*) >= :min_sampel
                ) t
                GROUP  BY kategori
                ORDER  BY kategori
                """
            ),
            {"min_sampel": min_sampel},
        ).scalars().all()
    return ["Semua"] + [r for r in rows if r]


def tren_material() -> dict[str, Any]:
    """Material yang punya lebih dari satu titik harga -- bahan grafik tren material.

    Sengaja mengembalikan `total_material` dan `siap_tren` sekaligus supaya UI bisa
    jujur menyebut cakupannya ("3 dari 11 material punya >1 titik harga") dan tidak
    menampilkan halaman yang terlihat meyakinkan padahal mewakili sebagian kecil data.
    """
    with engine.connect() as conn:
        ringkas = conn.execute(
            text(
                """
                SELECT COUNT(*) AS total_material,
                       COUNT(*) FILTER (WHERE n_harga > 1) AS siap_tren,
                       COALESCE(SUM(n_harga), 0)           AS total_titik_harga
                FROM (
                    SELECT sd.id, COUNT(h.id) AS n_harga
                    FROM   sumber_daya sd
                    LEFT   JOIN sumber_daya_harga h ON h.sumber_daya_id = sd.id
                    WHERE  sd.jenis = 'BAHAN' AND sd.aktif
                    GROUP  BY sd.id
                ) t
                """
            )
        ).mappings().first()

        kandidat = conn.execute(
            text(
                """
                SELECT sd.id, sd.nama, sd.spesifikasi, sd.satuan,
                       COUNT(h.id)          AS n_harga,
                       MIN(h.berlaku_dari)  AS dari,
                       MAX(h.berlaku_dari)  AS sampai,
                       COUNT(DISTINCT h.mata_uang) AS n_mata_uang
                FROM   sumber_daya sd
                JOIN   sumber_daya_harga h ON h.sumber_daya_id = sd.id
                WHERE  sd.jenis = 'BAHAN' AND sd.aktif
                GROUP  BY sd.id, sd.nama, sd.spesifikasi, sd.satuan
                HAVING COUNT(h.id) > 1
                ORDER  BY COUNT(h.id) DESC, sd.nama
                """
            )
        ).mappings().all()

    return {
        "ringkas": dict(ringkas) if ringkas else {},
        "kandidat": [dict(r) for r in kandidat],
    }
