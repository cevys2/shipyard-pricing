"""Harga Wajar: "pekerjaan ini biasanya dihargai berapa per satuan?" -- baca-saja.

Layar ini dibuka sambil menyusun penawaran. Ketik nama pekerjaan, lalu terlihat harga
satuannya di kapal-kapal lain, dikelompokkan per satuan baku (lihat `seed_satuan.py`).

Modul ini TIDAK PERNAH menulis ke `tabel_katalog_harga` -- cuma SELECT, sama seperti
`services/analitik.py`.

KAPAN ANGKA RINGKAS (median + rentang tengah) BOLEH MUNCUL -- disepakati 22 Oktober 2026.
Median dari pekerjaan yang jarang dan harganya hasil nego (contoh dari lapangan: bongkar
pasang jendela marine grade, yang tidak dikerjakan tiap tahun) terbaca seperti "harga pasar"
padahal cuma rata-rata dari beberapa kesepakatan yang berbeda-beda. Pekerjaan standar seperti
pengecatan dan replating tidak punya masalah itu. Yang membedakan keduanya dibaca dari
datanya, bukan dari daftar kategori yang ditulis tangan:

1. Satu docking satu suara. Satu docking = satu kapal di satu tahun. Lima belas baris Elbow
   di satu berkas dihitung sebagai SATU harga (nilai tengah baris-barisnya), supaya satu
   berkas yang barisnya banyak tidak menentukan angkanya sendirian.
2. Minimal `MIN_KAPAL` kapal BERBEDA. Satu kapal yang docking tiga tahun berturut-turut
   tetap satu kapal: tiga kesepakatan dengan klien yang sama bukan tiga pembanding.
3. Kalau menyebar (batas atas rentang tengah >= `RASIO_SEBAR` x batas bawahnya), angka
   ringkas tidak ditampilkan sebagai jawaban. Rentangnya tetap dikirim supaya layar bisa
   menyebut seberapa lebar.

Daftar per docking SELALU dikirim. Untuk pekerjaan yang dinego, pertanyaan yang berguna
adalah "dulu dengan klien ini sepakat berapa", dan daftar itulah jawabannya.

Kedua ambang di atas tebakan awal, belum dicoba ke data produksi. Kalau perlu disetel,
cukup di sini.

PENCARIAN KETAT dan cuma ke `uraian_pekerjaan`. Tanpa toleransi salah ketik (lihat
`pencarian.bangun(toleran=False)`), dan tanpa `kategori_pekerjaan`: mencari "pipa" di teks
kategori akan menarik semua Elbow, Valve, dan Flange di seksi PIPA - PIPA ke satu median.
"""

import statistics
from collections import defaultdict
from typing import Any

from sqlalchemy import text

from app.config import settings
from app.database import (
    NAMA_KAPAL_NORM_SQL,
    engine,
    satuan_katalog_baku_sql,
    satuan_katalog_sql,
    satuan_katalog_tertulis_sql,
)
from app.services import pencarian

TABLE = settings.catalog_table

MIN_KAPAL = 3
RASIO_SEBAR = 2.0

# Kata kunci yang cocok dengan lebih dari ini bukan pertanyaan "harga wajar" lagi ("cat"
# cocok dengan separuh tabel), jadi layar minta kata kunci diperjelas -- bukan memotong
# hasilnya diam-diam lalu menghitung median dari potongan.
BATAS_BARIS = 3000

KOLOM_CARI = ("t.uraian_pekerjaan",)


def _nilai_tengah(nilai: list[float]) -> tuple[float, float, float]:
    """(batas bawah rentang tengah, median, batas atas) -- kuartil 1, 2, 3.

    `method="inclusive"` = interpolasi linear, sama dengan PERCENTILE_CONT di Postgres yang
    dipakai `analitik.tren_harga_jasa()`. `statistics.quantiles` butuh minimal dua titik.
    """
    if len(nilai) == 1:
        return nilai[0], nilai[0], nilai[0]
    q1, q2, q3 = statistics.quantiles(nilai, n=4, method="inclusive")
    return q1, q2, q3


def harga_wajar(q: str | None) -> dict[str, Any]:
    cari = pencarian.bangun(q, KOLOM_CARI, toleran=False)
    hasil: dict[str, Any] = {
        "kata": pencarian.pecah(q, ketat=True),
        "aturan": {"min_kapal": MIN_KAPAL, "rasio_sebar": RASIO_SEBAR},
        "batas_baris": BATAS_BARIS,
        "total_cocok": 0,
        "terlalu_banyak": False,
        "kelompok": [],
    }
    if cari is None:
        return hasil

    with engine.connect() as conn:
        baris = conn.execute(
            text(
                f"""
                SELECT t.id,
                       {NAMA_KAPAL_NORM_SQL}                     AS nama_kapal,
                       COALESCE(ki.induk, t.nama_perusahaan)     AS klien,
                       t.tahun,
                       t.tipe_perjanjian,
                       t.uraian_pekerjaan                        AS uraian,
                       t.induk_uraian,
                       t.harga_satuan,
                       {satuan_katalog_tertulis_sql("t")}        AS satuan_tertulis,
                       {satuan_katalog_baku_sql("t")}            AS satuan_baku,
                       {satuan_katalog_sql("t")}                 AS satuan_rapi
                FROM   {TABLE} t
                LEFT   JOIN klien_induk ki ON ki.nama_perusahaan = t.nama_perusahaan
                WHERE  t.harga_satuan > 0
                  AND  {cari.kondisi}
                ORDER  BY t.tahun DESC, 2, t.id
                LIMIT  :batas
                """
            ),
            {**cari.params, "batas": BATAS_BARIS + 1},
        ).mappings().all()
        borongan = dict(conn.execute(text("SELECT nama, borongan FROM satuan")).all())

    if len(baris) > BATAS_BARIS:
        # None, bukan len(baris): yang terbaca cuma BATAS_BARIS + 1 (LIMIT), jadi angka itu
        # bukan jumlah sebenarnya. Layar menyebut "lebih dari `batas_baris`" sendiri.
        hasil["total_cocok"] = None
        hasil["terlalu_banyak"] = True
        return hasil
    hasil["total_cocok"] = len(baris)

    # Kunci kelompok: nama satuan baku kalau ejaannya sudah dipetakan, kalau belum ejaan
    # yang dirapikan apa adanya -- satuan yang belum dikenal tetap tampil, tidak dibuang.
    # None = baris yang kedua kolom satuannya kosong/"-": harganya per apa tidak diketahui.
    per_satuan: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
    for b in baris:
        d = dict(b)
        d["harga_satuan"] = float(d["harga_satuan"])
        per_satuan[d["satuan_baku"] or d["satuan_rapi"]].append(d)

    kelompok = [_kelompok(satuan, rows, borongan) for satuan, rows in per_satuan.items()]
    kelompok.sort(
        key=lambda k: (k["satuan"] is None, -k["n_kapal"], -k["n_baris"], k["satuan"] or "")
    )
    hasil["kelompok"] = kelompok
    return hasil


def _kelompok(
    satuan: str | None, rows: list[dict[str, Any]], borongan: dict[str, bool]
) -> dict[str, Any]:
    per_docking: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        per_docking[(r["nama_kapal"] or "", r["tahun"] or "")].append(r)

    docking = []
    for (kapal, tahun), isi in per_docking.items():
        harga = [r["harga_satuan"] for r in isi]
        docking.append(
            {
                "nama_kapal": kapal,
                "tahun": tahun,
                "klien": sorted({r["klien"] for r in isi if r["klien"]}),
                "tipe": sorted({r["tipe_perjanjian"] for r in isi if r["tipe_perjanjian"]}),
                "harga": round(statistics.median(harga)),
                "harga_min": min(harga),
                "harga_max": max(harga),
                "n_baris": len(isi),
                "baris": [
                    {
                        k: r[k]
                        for k in (
                            "id",
                            "uraian",
                            "induk_uraian",
                            "harga_satuan",
                            "tipe_perjanjian",
                            "satuan_tertulis",
                        )
                    }
                    for r in isi
                ],
            }
        )
    # Terbaru di atas; di dalam tahun yang sama urut nama kapal A-Z. Dua sort karena
    # `reverse=True` pada satu kunci gabungan ikut membalik urutan nama.
    docking.sort(key=lambda d: d["nama_kapal"])
    docking.sort(key=lambda d: d["tahun"], reverse=True)

    n_kapal = len({d["nama_kapal"] for d in docking if d["nama_kapal"]})
    tahun = [d["tahun"] for d in docking if d["tahun"]]

    ringkas = None
    if satuan is None:
        alasan = "tanpa_satuan"
    elif n_kapal < MIN_KAPAL:
        alasan = "kapal_kurang"
    else:
        bawah, tengah, atas = _nilai_tengah([float(d["harga"]) for d in docking])
        ringkas = {"median": round(tengah), "bawah": round(bawah), "atas": round(atas)}
        alasan = "menyebar" if bawah > 0 and atas >= RASIO_SEBAR * bawah else None

    # Patokan "harga terakhir" (disepakati 22 Oktober 2026): bos lebih suka ada satu angka
    # pegangan, juga ketika median disembunyikan. Yang dikirim SEMUA docking di tahun
    # terbaru, bukan satu yang dipilih -- kalau dua kapal di 2026 harganya 4,5 jt dan 7 jt,
    # memilih salah satu menurut abjad nama kapal sama saja dengan mengarang patokan. Asalnya
    # (kapal, klien) selalu ikut, supaya angka dari satu nego yang alot bisa dinilai sendiri.
    terakhir = None
    if tahun:
        tahun_terbaru = max(tahun)
        terakhir = {
            "tahun": tahun_terbaru,
            "docking": [
                {k: d[k] for k in ("nama_kapal", "klien", "harga", "n_baris")}
                for d in docking
                if d["tahun"] == tahun_terbaru
            ],
        }

    return {
        "satuan": satuan,
        # Dikenal = ejaannya ada di `satuan_alias`. Yang belum dikenal tetap jadi kelompok
        # sendiri dengan ejaan aslinya, supaya daftar alias bisa dilengkapi dari layar.
        "dikenali": all(r["satuan_baku"] for r in rows),
        "borongan": bool(borongan.get(satuan, False)),
        "ejaan": sorted({r["satuan_tertulis"].strip() for r in rows if r["satuan_tertulis"]}),
        "n_baris": len(rows),
        "n_docking": len(docking),
        "n_kapal": n_kapal,
        "tahun_min": min(tahun) if tahun else None,
        "tahun_max": max(tahun) if tahun else None,
        "ringkas": ringkas,
        "tampilkan_ringkas": ringkas is not None and alasan is None,
        "alasan": alasan,
        "terakhir": terakhir,
        "docking": docking,
    }
