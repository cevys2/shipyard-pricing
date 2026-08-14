"""Tahun dari sel Excel harus jadi "2026", bukan "2026.0".

Kolom angka yang punya satu sel kosong saja -- baris TOTAL, baris pemisah -- dibaca pandas
sebagai float64, dan `str(np.float64(2026.0))` menghasilkan "2026.0". Tahun ikut membentuk
prefix ID (`KMP._MISHIMA-2026.0-001`), jadi salahnya permanen di primary key: impor lewat
Excel dan impor lewat Laporan Docking menghasilkan dua rangkaian penomoran untuk kapal dan
tahun yang sama, dan filter "Tahun" di dashboard menampilkan 2026 dua kali.

Memformat sel sebagai teks di Excel tidak menolong -- yang menebak tipe itu pandas, bukan
format selnya.

Bagian kedua berkas ini menguji hal yang sama di `docking_parser.find_label_value`. Di
sanalah 764 baris "2026.0" di produksi sebenarnya lahir: sel tahun di laporan docking
tersimpan sebagai angka, hasil bacaannya mengisi kolom Tahun di form impor, dan apa pun
yang ada di kolom itu ikut jadi prefix ID.
"""

import io

import pytest
from openpyxl import Workbook

from app.services.catalog import parse_spreadsheet
from app.services.docking_parser import find_label_value, guess_header


def _excel(baris, header=("Nama Kapal", "Tahun", "Kategori", "Uraian Pekerjaan", "Satuan", "Harga")):
    """Berkas .xlsx di memori. `baris` ditulis apa adanya, termasuk sel kosong (None)."""
    wb = Workbook()
    ws = wb.active
    ws.append(list(header))
    for b in baris:
        ws.append(list(b))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _dua_baris(tahun):
    return [
        ["KMP. MISHIMA", tahun, "DOCKING", "Sandblasting lambung", "m2", 50000],
        ["KMP. MISHIMA", tahun, "DOCKING", "Pengecatan AC", "m2", 60000],
    ]


def test_tahun_angka_dengan_baris_total_tidak_jadi_desimal():
    """Pemicu sebenarnya: satu sel kosong di kolom Tahun membuat seluruh kolom float64."""
    baris = _dua_baris(2026)
    baris.append([None, None, None, "TOTAL", None, 110000])

    bulk, _ = parse_spreadsheet(_excel(baris), "docking.xlsx")

    assert bulk is not None
    assert bulk.tahun == "2026", f"tahun terbaca {bulk.tahun!r} -- '.0' akan menempel di ID baris"


def test_tahun_angka_penuh_tetap_utuh():
    """Tanpa sel kosong kolomnya int64 dan sudah benar; jangan sampai perbaikannya merusak ini."""
    bulk, _ = parse_spreadsheet(_excel(_dua_baris(2026)), "docking.xlsx")

    assert bulk is not None
    assert bulk.tahun == "2026"


def test_prefix_id_sama_dengan_jalur_impor_docking():
    """Inti kerugiannya: ID dari Excel harus seragam dengan ID dari Laporan Docking."""
    baris = _dua_baris(2026)
    baris.append([None, None, None, "TOTAL", None, 110000])

    bulk, _ = parse_spreadsheet(_excel(baris), "docking.xlsx")

    slug = bulk.nama_kapal.strip().replace(" ", "_").upper()
    assert f"{slug}-{bulk.tahun.strip()}-" == "KMP._MISHIMA-2026-"


@pytest.mark.parametrize("tahun", ["2025/2026", "2026 (Addendum)", "TA 2026"])
def test_tahun_bukan_angka_tidak_ikut_diutak_atik(tahun):
    """Tahun yang memang teks harus lewat apa adanya."""
    baris = _dua_baris(tahun)
    baris.append([None, None, None, "TOTAL", None, 110000])

    bulk, _ = parse_spreadsheet(_excel(baris), "docking.xlsx")

    assert bulk is not None
    assert bulk.tahun == tahun


def test_nama_kapal_bernomor_tidak_jadi_desimal():
    """Bukan cuma tahun -- nama kapal yang isinya angka semua kena hal yang sama."""
    baris = [
        [88, 2026, "DOCKING", "Sandblasting lambung", "m2", 50000],
        [88, 2026, "DOCKING", "Pengecatan AC", "m2", 60000],
        [None, None, None, "TOTAL", None, 110000],
    ]

    bulk, _ = parse_spreadsheet(_excel(baris), "docking.xlsx")

    assert bulk is not None
    assert bulk.nama_kapal == "88", f"nama kapal terbaca {bulk.nama_kapal!r}"


# --- jalur Laporan Docking -- masalah yang sama, modul lain ------------------------

def _kepala_docking(tahun):
    """Bentuk baris kepala laporan docking: label, ':', lalu nilainya di sel berikutnya."""
    return [
        ["LAMPIRAN PEKERJAAN PERJANJIAN", None, None, None],
        ["NAMA KAPAL", ":", "KMP. MISHIMA", None],
        ["PEMILIK", ":", "PT. JEMLA FERRY", None],
        ["PERIODE DOCKING", ":", tahun, None],
    ]


def test_tahun_docking_dari_sel_angka_tidak_jadi_desimal():
    """Inilah asal 764 baris "2026.0" di produksi -- bukan jalur impor Excel biasa."""
    _, _, tahun = guess_header(_kepala_docking(2026.0), "Biaya Docking KMP. MISHIMA.xls")

    assert tahun == "2026", f"tahun terdeteksi {tahun!r} -- nilai ini mengisi form impor apa adanya"


def test_kepala_docking_lain_tetap_terbaca():
    kapal, pemilik, _ = guess_header(_kepala_docking(2026.0), "berkas.xls")

    assert kapal == "KMP. MISHIMA"
    assert pemilik == "PT. JEMLA FERRY"


@pytest.mark.parametrize("nilai,harapan", [("Nopember", "Nopember"), ("2025/2026", "2025/2026")])
def test_nilai_teks_di_kepala_docking_lewat_apa_adanya(nilai, harapan):
    """Yang bukan angka tidak boleh ikut diutak-atik.

    "Nopember" memang salah sebagai tahun -- selnya berbunyi "PERIODE DOCKING : Nopember
    2025" dengan bulan dan tahun di dua sel terpisah -- tapi itu cacat yang lain, dan
    perbaikan pembulatan ini sengaja tidak berpura-pura menanganinya.
    """
    assert find_label_value(_kepala_docking(nilai), ["periodedocking"]) == harapan


def test_angka_pecahan_tidak_dibulatkan():
    """Pembulatan hanya untuk bilangan bulat; sisanya jangan disentuh."""
    assert find_label_value(_kepala_docking(2026.5), ["periodedocking"]) == "2026.5"
