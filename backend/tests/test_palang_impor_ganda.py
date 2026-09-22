"""Palang berkas yang diimpor dua kali.

Bukan hipotesis: per 22 September 2026 produksi memuat berkas MISHIMA TIGA kali (591
baris, seharusnya 197) dan MUNIC 1 EMPAT kali (716, seharusnya 179). Nilai MISHIMA
terbaca Rp 3,5 miliar padahal sebenarnya Rp 1,3 miliar, dan tidak ada satu pun tanda di
layar -- nama kapalnya sama, jadi di dropdown dia tetap satu kapal.

Dua sifat yang paling gampang rusak dan keduanya diuji di sini:

1. Palang yang DIAM waktu seharusnya bunyi -> masalahnya kembali tanpa suara.
2. Palang yang BUNYI waktu seharusnya diam -> orang belajar mengabaikannya, dan palang
   yang diabaikan tidak menjaga apa pun. Baris Addendum yang sah nyaris tidak beririsan
   dengan Induk (diukur di 13 kapal berbatch ganda di produksi: 0-11%), jadi ambang 30%
   harus tetap membiarkannya lewat.
"""

import pytest
from sqlalchemy import text

from app.services.catalog import peringatan_impor_ganda


@pytest.fixture
def isi(conn):
    """20 baris untuk satu kapal, mirip hasil impor docking."""
    baris = [(f"Pekerjaan {i}", 100000.0 + i, float(i + 1)) for i in range(20)]
    conn.execute(
        text(
            "INSERT INTO tabel_katalog_harga "
            "(id, nama_kapal, nama_perusahaan, tahun, uraian_pekerjaan, kategori_pekerjaan,"
            " harga_satuan, volume) "
            "VALUES (:id, 'KMP. UJI', 'PT. UJI', '2026', :u, 'PELAYANAN UMUM', :h, :v)"
        ),
        [{"id": f"U-{i:03d}", "u": u, "h": h, "v": v} for i, (u, h, v) in enumerate(baris)],
    )
    conn.commit()
    return baris


def test_berkas_yang_sama_diimpor_lagi_memicu_peringatan(conn, isi):
    w = peringatan_impor_ganda("KMP. UJI", isi)
    assert w, "berkas identik harus memicu peringatan"
    assert "20 dari 20" in w[0] and "100%" in w[0]


def test_kapal_yang_belum_pernah_diimpor_diam(conn, isi):
    assert peringatan_impor_ganda("KMP. BELUM ADA", isi) == []


def test_isi_yang_seluruhnya_baru_diam(conn, isi):
    baru = [(f"Pekerjaan lain {i}", 55000.0 + i, float(i)) for i in range(20)]
    assert peringatan_impor_ganda("KMP. UJI", baru) == []


def test_addendum_yang_sah_tidak_memicu_bunyi_palsu(conn, isi):
    """2 dari 20 beririsan (10%) -- di bawah ambang, harus lewat tanpa suara."""
    addendum = list(isi[:2]) + [(f"Tambahan {i}", 77000.0 + i, 1.0) for i in range(18)]
    assert peringatan_impor_ganda("KMP. UJI", addendum) == []


def test_ambang_tepat_di_batas_tetap_bunyi(conn, isi):
    """6 dari 20 = 30%, tepat di ambang."""
    campur = list(isi[:6]) + [(f"Tambahan {i}", 77000.0 + i, 1.0) for i in range(14)]
    assert peringatan_impor_ganda("KMP. UJI", campur)


def test_newline_dan_awalan_strip_tetap_terbaca_sama(conn, isi):
    """Berkas yang sama sebelum dan sesudah parser diperbaiki harus tetap cocok.

    Impor lama menyimpan newline di tengah teks, dan penanganan pengisi tata letak
    ("- " di depan uraian) berubah 1 September 2026. Tanpa normalisasi ini, berkas yang
    sama terlihat sebagai isi yang sama sekali berbeda dan palangnya diam.
    """
    kotor = [(f"-  Pekerjaan\n  {i}", h, v) for (u, h, v), i in zip(isi, range(20))]
    w = peringatan_impor_ganda("KMP. UJI", kotor)
    assert w and "20 dari 20" in w[0]


def test_nama_kapal_berspasi_ganda_tetap_ketemu(conn, isi):
    """Impor MISHIMA pertama masuk sebagai "MISHIMA", berikutnya "KMP. MISHIMA"."""
    assert peringatan_impor_ganda("KMP.  UJI", isi)
