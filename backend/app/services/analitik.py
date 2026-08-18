"""Analitik baca-saja di atas `tabel_katalog_harga` (harga jual jasa docking).

PENTING: modul ini TIDAK PERNAH menulis ke `tabel_katalog_harga` -- tidak ada INSERT,
UPDATE, DELETE, maupun DDL. Semua normalisasi teks (kategori berantakan, newline di
tengah string) dilakukan di dalam SELECT, bukan dengan membetulkan datanya. Lihat
`docs/catatan-tabel-katalog-harga.md`.
"""

from typing import Any

from sqlalchemy import text

from app.config import settings
from app.database import engine, urutan_harga_sql

TABLE = settings.catalog_table

# Modul ini dulu menormalisasi `kategori_pekerjaan` sendiri saat membaca, karena teks
# kategorinya berantakan dan tidak ada tempat lain untuk merapikannya. Sekarang perapian
# itu sudah terjadi sekali di `kategori_id` lewat resolver, jadi analitik tinggal ikut
# JOIN -- ekspresi normalisasinya tidak lagi punya pemakai di sini.


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
        where_kat = "AND k.nama = :kategori"
        params["kategori"] = kategori

    with engine.connect() as conn:
        # `kapal` ikut dikembalikan karena median tanpa tahu kapal mana yang menyusunnya
        # tidak bisa ditindaklanjuti: angka Rp 65.000 untuk Sweepblasting jadi tidak jelas
        # itu rata-rata dari kapal besar, kapal kecil, atau campuran keduanya.
        #
        # Pengelompokan lewat `kategori_id`, bukan lewat normalisasi teks. Sepuluh sebutan
        # "PIPA-PIPA"/"Pipa - Pipa"/"PIPING" dulu jadi sepuluh kelompok tipis yang
        # masing-masing bisa gugur di `min_sampel`; sekarang satu kelompok tebal.
        #
        # JOIN (bukan LEFT JOIN) menyaring baris yang `kategori_id`-nya masih NULL. Itu
        # disengaja -- median dari kategori "tidak diketahui" tidak ada artinya -- tapi
        # jumlahnya ikut dilaporkan di `cakupan.tanpa_kategori` supaya penyusutannya
        # kelihatan, bukan hilang diam-diam.
        seri = conn.execute(
            text(
                f"""
                SELECT k.nama AS kategori,
                       t.tahun,
                       COUNT(*)                                                     AS n_baris,
                       COUNT(DISTINCT t.nama_kapal)                                 AS n_kapal,
                       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY t.harga_satuan)  AS median,
                       MIN(t.harga_satuan)                                          AS minimum,
                       MAX(t.harga_satuan)                                          AS maksimum,
                       -- Agregat biasa, bukan subquery berkorelasi: grup di sini SUDAH
                       -- (kategori, tahun), jadi array_agg atas grup tepat berisi kapal
                       -- yang menyusun median tersebut.
                       array_agg(DISTINCT t.nama_kapal ORDER BY t.nama_kapal)
                           FILTER (WHERE t.nama_kapal IS NOT NULL)                  AS kapal
                FROM   {TABLE} t
                JOIN   kategori k ON k.id = t.kategori_id
                WHERE  t.harga_satuan > 0
                  {where_kat}
                GROUP  BY k.nama, k.urutan, t.tahun
                HAVING COUNT(*) >= :min_sampel
                ORDER  BY k.urutan, t.tahun
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

        # `tanpa_kategori` baru: baris yang belum punya kategori_id sama sekali tidak masuk
        # `seri`. Yang lazim bikin ini naik adalah impor Excel dengan sebutan kategori yang
        # belum ada aliasnya -- resolver baru jalan lagi saat aplikasi start berikutnya.
        # Tanpa angka ini, baris-baris itu cuma raib dari grafik tanpa memberi tahu siapa pun.
        cakupan = conn.execute(
            text(
                f"""
                SELECT COUNT(*) AS total_baris,
                       COUNT(DISTINCT kategori_id) AS total_kategori,
                       COUNT(DISTINCT tahun) AS total_tahun,
                       COUNT(*) FILTER (WHERE kategori_id IS NULL) AS tanpa_kategori
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
    """Kategori dari master (aktif saja, urut `urutan`) yang punya data lolos `min_sampel`.

    Namanya sekarang datang dari tabel `kategori`, bukan dari memindai teks bebas -- itu
    inti Sesi K2. Yang sengaja DIPERTAHANKAN dari versi lama: saringan `min_sampel`-nya
    tetap sama persis dengan `tren_harga_jasa()`. Mengembalikan seluruh isi master apa
    adanya akan memunculkan lagi bug yang dulu diperbaiki di sini -- kategori yang bisa
    dipilih tapi grafiknya kosong, karena tiap tahunnya kurang dari `min_sampel` baris
    sehingga tersaring habis di sisi data.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT k.nama
                FROM   kategori k
                WHERE  k.aktif
                  AND  EXISTS (
                           SELECT 1
                           FROM   {TABLE} t
                           WHERE  t.kategori_id = k.id
                             AND  t.harga_satuan > 0
                           GROUP  BY t.tahun
                           HAVING COUNT(*) >= :min_sampel
                       )
                ORDER  BY k.urutan
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

        # harga_awal/harga_akhir diambil lewat DISTINCT ON di subquery supaya perubahan
        # persennya dihitung di DB, bukan disusun ulang di frontend dari daftar titik.
        kandidat = conn.execute(
            text(
                f"""
                SELECT sd.id, sd.nama, sd.spesifikasi, sd.satuan,
                       COUNT(h.id)                 AS n_harga,
                       MIN(h.tahun_pembelian)      AS dari,
                       MAX(h.tahun_pembelian)      AS sampai,
                       COUNT(DISTINCT h.mata_uang) AS n_mata_uang,
                       MIN(h.mata_uang)            AS mata_uang,
                       (SELECT a.harga_satuan FROM sumber_daya_harga a
                        WHERE a.sumber_daya_id = sd.id
                        ORDER BY {urutan_harga_sql("a", terbaru_dulu=False)} LIMIT 1) AS harga_awal,
                       (SELECT z.harga_satuan FROM sumber_daya_harga z
                        WHERE z.sumber_daya_id = sd.id
                        ORDER BY {urutan_harga_sql("z")} LIMIT 1) AS harga_akhir
                FROM   sumber_daya sd
                JOIN   sumber_daya_harga h ON h.sumber_daya_id = sd.id
                WHERE  sd.jenis = 'BAHAN' AND sd.aktif
                GROUP  BY sd.id, sd.nama, sd.spesifikasi, sd.satuan
                HAVING COUNT(h.id) > 1
                ORDER  BY COUNT(h.id) DESC, sd.nama
                """
            )
        ).mappings().all()

        titik = []
        if kandidat:
            titik = conn.execute(
                text(
                    f"""
                    SELECT h.sumber_daya_id, h.tahun_pembelian, h.harga_satuan, h.mata_uang,
                           h.nama_kapal, sup.nama AS supplier_nama
                    FROM   sumber_daya_harga h
                    LEFT   JOIN supplier sup ON sup.id = h.supplier_id
                    WHERE  h.sumber_daya_id = ANY(:ids)
                    ORDER  BY h.sumber_daya_id, {urutan_harga_sql("h", terbaru_dulu=False)}
                    """
                ),
                {"ids": [k["id"] for k in kandidat]},
            ).mappings().all()

    out_kandidat = []
    for k in kandidat:
        d = dict(k)
        awal, akhir = d.get("harga_awal"), d.get("harga_akhir")
        # Perubahan persen hanya bermakna kalau mata uangnya tunggal -- 100 EUR jadi
        # 1.700.000 IDR bukan kenaikan 1.699.900%, cuma pindah mata uang.
        d["perubahan_persen"] = (
            round((float(akhir) - float(awal)) / float(awal) * 100, 2)
            if awal and akhir and float(awal) > 0 and d["n_mata_uang"] == 1
            else None
        )
        out_kandidat.append(d)

    return {
        "ringkas": dict(ringkas) if ringkas else {},
        "kandidat": out_kandidat,
        "titik": [dict(r) for r in titik],
    }
