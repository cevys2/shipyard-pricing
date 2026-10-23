"""Analitik baca-saja di atas `tabel_katalog_harga` (harga jual jasa docking).

PENTING: modul ini TIDAK PERNAH menulis ke `tabel_katalog_harga` -- tidak ada INSERT,
UPDATE, DELETE, maupun DDL. Semua normalisasi teks (kategori berantakan, newline di
tengah string) dilakukan di dalam SELECT, bukan dengan membetulkan datanya. Lihat
`docs/catatan-tabel-katalog-harga.md`.
"""

from typing import Any

from sqlalchemy import text

from app.config import settings
from app.database import (
    JENIS_KAPAL_SQL,
    NAMA_KAPAL_NORM_SQL,
    engine,
    urutan_harga_sql,
)

TABLE = settings.catalog_table

# Modul ini dulu menormalisasi `kategori_pekerjaan` sendiri saat membaca, karena teks
# kategorinya berantakan dan tidak ada tempat lain untuk merapikannya. Sekarang perapian
# itu sudah terjadi sekali di `kategori_id` lewat resolver, jadi analitik tinggal ikut
# JOIN -- ekspresi normalisasinya tidak lagi punya pemakai di sini.


def nilai_pekerjaan() -> dict[str, Any]:
    """Nilai pekerjaan (volume x harga_satuan) per kategori/tahun dan per kapal/klien.

    Pertanyaan "harga satuannya berapa" dijawab layar Harga Wajar. Yang ini menjawab "uangnya pergi ke mana" -- dan itu baru mungkin sejak kolom `volume` ada,
    karena tanpa kuantitas satu baris Rp 300.000 bisa berarti Rp 300.000 atau
    Rp 90.000.000.

    CAKUPANNYA SEPARUH, DAN ITU HARUS KELIHATAN. Per 22 September 2026 cuma 3.243 dari
    8.024 baris punya `volume` -- sisanya diimpor sebelum kolomnya ada, dan nilainya
    memang tidak diketahui. Cakupannya juga tidak acak: dia mengikuti jalur impor, jadi
    per kapal angkanya melompat dari 14% (SINDU TRITAMA) sampai 100% (PRATHITA IV).
    Karena itu `per_kapal` membawa `n_baris` DAN `n_baris_bernilai` sekaligus: kapal yang
    cuma 14% barisnya terhitung akan terlihat murah padahal cuma sebagian yang terbaca,
    dan satu-satunya cara jujur adalah menyebut pecahannya, bukan menyembunyikan
    penyebutnya.

    `klien` memakai `COALESCE(ki.induk, ...)` supaya dua ejaan PT yang satu induk tidak
    dihitung sebagai dua klien -- lihat `database.ensure_klien_induk()`. Nama kapal
    dinormalisasi spasinya lewat `NAMA_KAPAL_NORM_SQL` dengan alasan yang sama.
    """
    # ROUND(...::numeric): `harga_satuan` double precision, jadi volume x harga jatuh ke
    # float dan menyisakan ekor seperti "...577,972507". Rupiah tidak sepecah itu, dan
    # angka yang memamerkan ketelitian palsu bikin orang ragu pada seluruh layarnya.
    with engine.connect() as conn:
        # JOIN (bukan LEFT JOIN) ke `kategori`: nilai dari kategori "tidak diketahui" tidak
        # bisa ditindaklanjuti. Yang tersaring ikut dilaporkan di `cakupan.tanpa_kategori`,
        # dan layar menampilkannya -- sejak grafik Tren Harga Jual Jasa dibuang (23 Oktober
        # 2026), itu satu-satunya tempat baris tanpa kategori kelihatan.
        per_kategori = conn.execute(
            text(
                f"""
                SELECT k.nama                            AS kategori,
                       t.tahun,
                       COUNT(*)                          AS n_baris,
                       ROUND(SUM(t.volume * t.harga_satuan)::numeric) AS nilai
                FROM   {TABLE} t
                JOIN   kategori k ON k.id = t.kategori_id
                WHERE  t.harga_satuan > 0 AND t.volume IS NOT NULL
                GROUP  BY k.nama, k.urutan, t.tahun
                ORDER  BY k.urutan, t.tahun
                """
            )
        ).mappings().all()

        # Di sini TIDAK disaring `volume IS NOT NULL`: penyebutnya justru yang dicari.
        # COUNT(*) = seluruh baris berharga kapal itu, COUNT(t.volume) = yang ikut
        # terhitung nilainya. SUM mengabaikan NULL dengan sendirinya.
        per_kapal = conn.execute(
            text(
                f"""
                SELECT {NAMA_KAPAL_NORM_SQL}             AS nama_kapal,
                       {JENIS_KAPAL_SQL}                 AS jenis,
                       COALESCE(ki.induk, t.nama_perusahaan) AS klien,
                       t.tahun,
                       COUNT(*)                          AS n_baris,
                       COUNT(t.volume)                   AS n_baris_bernilai,
                       COALESCE(ROUND(SUM(t.volume * t.harga_satuan)::numeric), 0) AS nilai
                FROM   {TABLE} t
                LEFT   JOIN klien_induk ki ON ki.nama_perusahaan = t.nama_perusahaan
                WHERE  t.harga_satuan > 0
                GROUP  BY {NAMA_KAPAL_NORM_SQL},
                          {JENIS_KAPAL_SQL},
                          COALESCE(ki.induk, t.nama_perusahaan),
                          t.tahun
                ORDER  BY 3, 1, 4
                """
            )
        ).mappings().all()

        cakupan = conn.execute(
            text(
                f"""
                SELECT COUNT(*)                                      AS total_baris,
                       COUNT(volume)                                 AS baris_bernilai,
                       COUNT(DISTINCT {NAMA_KAPAL_NORM_SQL})         AS total_kapal,
                       COUNT(DISTINCT {NAMA_KAPAL_NORM_SQL})
                           FILTER (WHERE volume IS NOT NULL)         AS kapal_bernilai,
                       COUNT(*) FILTER (WHERE kategori_id IS NULL)   AS tanpa_kategori,
                       COALESCE(ROUND(SUM(volume * harga_satuan)::numeric), 0) AS nilai_total
                FROM   {TABLE}
                WHERE  harga_satuan > 0
                """
            )
        ).mappings().first()

    return {
        "cakupan": dict(cakupan) if cakupan else {},
        "per_kategori": [dict(r) for r in per_kategori],
        "per_kapal": [dict(r) for r in per_kapal],
    }


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
