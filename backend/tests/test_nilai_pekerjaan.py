"""Analitik "ke mana uangnya pergi": penyebut cakupan, dan dua nama yang sebenarnya satu.

Tiga hal di sini gampang rusak tanpa bersuara, dan ketiganya membuat layar tetap terlihat
benar sambil menampilkan angka yang salah:

1. `n_baris_bernilai` bisa diam-diam jadi sama dengan `n_baris` kalau suatu saat ada yang
   menambahkan `WHERE volume IS NOT NULL` ke query per-kapal. Penyebutnya hilang, tiap
   kapal terlihat 100% terukur, dan nilai yang cuma memotret seperempat pekerjaan
   terbaca sebagai nilai penuh. Per 22 September 2026 baru 40% baris punya volume.
2. Dua ejaan PT yang satu induk (`AGUNG TAMA RAYA` / `AGUNG TRANSINA RAYA`) akan terhitung
   sebagai dua klien, jadi perbandingan klien membelah satu klien jadi dua yang
   masing-masing terlihat setengah.
3. Nama kapal berspasi ganda (`KMP. PRIMA  NUSANTARA`) terpisah dari kembarannya yang
   berspasi tunggal -- satu kapal jadi dua baris perbandingan.
"""

import pytest
from sqlalchemy import text

from app.database import ensure_klien_induk, engine
from app.services.analitik import nilai_pekerjaan


@pytest.fixture(autouse=True)
def klien_induk_siap():
    ensure_klien_induk()


def _baris(conn, id_, kapal, pt, *, volume, harga=1000, tahun="2026"):
    conn.execute(
        text(
            "INSERT INTO tabel_katalog_harga "
            "(id, nama_kapal, nama_perusahaan, tahun, uraian_pekerjaan, "
            " kategori_pekerjaan, harga_satuan, volume) "
            "VALUES (:id, :kapal, :pt, :tahun, 'tes', 'PELAYANAN UMUM', :harga, :volume)"
        ),
        {"id": id_, "kapal": kapal, "pt": pt, "tahun": tahun, "harga": harga, "volume": volume},
    )


def test_penyebut_cakupan_ikut_baris_yang_tidak_punya_volume(conn):
    """Kapal dengan 1 dari 3 baris bervolume harus melapor 1/3, bukan 1/1."""
    _baris(conn, "T-1", "KMP. TES", "PT. TES", volume=2, harga=1000)
    _baris(conn, "T-2", "KMP. TES", "PT. TES", volume=None)
    _baris(conn, "T-3", "KMP. TES", "PT. TES", volume=None)
    conn.commit()

    (kapal,) = nilai_pekerjaan()["per_kapal"]
    assert kapal["n_baris"] == 3, "penyebutnya harus seluruh baris berharga, bukan yang bervolume saja"
    assert kapal["n_baris_bernilai"] == 1
    assert int(kapal["nilai"]) == 2000


def test_kapal_tanpa_volume_sama_sekali_tetap_muncul(conn):
    """Kalau dia raib, perbandingan kehilangan peserta tanpa memberi tahu siapa pun."""
    _baris(conn, "T-1", "KMP. TAK TERUKUR", "PT. TES", volume=None)
    conn.commit()

    (kapal,) = nilai_pekerjaan()["per_kapal"]
    assert kapal["n_baris"] == 1
    assert kapal["n_baris_bernilai"] == 0
    assert int(kapal["nilai"]) == 0


def test_dua_ejaan_pt_satu_induk_jadi_satu_klien(conn):
    _baris(conn, "T-1", "KMP. SINDU DWITAMA", "PT. AGUNG TAMA RAYA", volume=1)
    _baris(conn, "T-2", "KMP. SINDU DWITAMA", "PT. AGUNG TRANSINA RAYA", volume=1)
    conn.commit()

    per_kapal = nilai_pekerjaan()["per_kapal"]
    assert {r["klien"] for r in per_kapal} == {"PT. AGUNG TAMA RAYA"}
    assert len(per_kapal) == 1, "kapal+klien+tahun yang sama harus jadi satu baris"
    assert per_kapal[0]["n_baris"] == 2


def test_spasi_ganda_di_nama_kapal_tidak_membelah_satu_kapal(conn):
    _baris(conn, "T-1", "KMP. PRIMA NUSANTARA", "PT. TES", volume=1)
    _baris(conn, "T-2", "KMP. PRIMA  NUSANTARA", "PT. TES", volume=1)
    conn.commit()

    per_kapal = nilai_pekerjaan()["per_kapal"]
    assert len(per_kapal) == 1
    assert per_kapal[0]["nama_kapal"] == "KMP. PRIMA NUSANTARA"
    assert nilai_pekerjaan()["cakupan"]["total_kapal"] == 1


@pytest.mark.parametrize(
    "kapal, jenis",
    [
        ("KMP. GILIMANUK", "KMP"),
        ("KMP PRATHITA IV", "KMP"),   # tanpa titik
        ("KMP.  MUNIC 1", "KMP"),     # spasi ganda sesudah titik
        ("KN SAR 207", "KN"),
        ("KLM. ALIIKAI", "KLM"),
        ("LCT. ARJHUNA", "LCT"),
        ("MV. BALI HAI II", "MV"),
    ],
)
def test_jenis_kapal_diturunkan_dari_nama(conn, kapal, jenis):
    _baris(conn, "T-1", kapal, "PT. TES", volume=1)
    conn.commit()
    assert nilai_pekerjaan()["per_kapal"][0]["jenis"] == jenis


def test_baris_berharga_nol_tidak_ikut_menghitung_apa_pun(conn):
    """`harga_satuan > 0` dipakai seragam dengan `tren_harga_jasa()`."""
    _baris(conn, "T-1", "KMP. TES", "PT. TES", volume=5, harga=0)
    conn.commit()

    assert nilai_pekerjaan()["per_kapal"] == []
    assert nilai_pekerjaan()["cakupan"]["total_baris"] == 0
