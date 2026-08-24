"""Template laporan docking tidak seragam, dan tiap ketidakseragaman pernah bikin nol baris.

Empat berkas di arsip gagal terbaca sama sekali sebelum perbaikan 24 Agustus 2026, dan
semuanya gagal DIAM-DIAM: parser mengembalikan daftar kosong, bukan error. Berkas yang
"berhasil diimpor 0 baris" terlihat sama persis dengan berkas yang memang kosong.

Yang ditiru di sini bentuk kepalanya saja, secukupnya untuk memicu tiap kegagalan.
"""

import io

import pytest
from openpyxl import Workbook

from app.services.docking_parser import guess_header, parse_docking_file

LEBAR = 24


def _baris(**sel) -> list:
    row = [None] * LEBAR
    for ci, v in sel.items():
        row[int(ci[1:])] = v
    return row


def _berkas(kepala: list[list], judul: list, sub: list, isi: list[list], sheet="Sheet1") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    for row in kepala:
        ws.append(row)
    ws.append(judul)
    ws.append(sub)
    for row in isi:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --- kolom uraian bernama "Nama Barang" -------------------------------------------------

def test_kolom_uraian_boleh_bernama_nama_barang():
    """Lampiran Perjanjian KMP. Portlink II 2026 memakai "Nama Barang", bukan "URAIAN".

    `find_header_idx` dulu mensyaratkan kata "uraian", jadi baris judulnya tidak pernah
    ketemu dan seluruh berkas (141 baris) terbaca nol.
    """
    hasil = parse_docking_file(
        _berkas(
            [_baris(c0="DATA - DATA KAPAL"), _baris(c0=2, c1="NAMA KAPAL", c5=":", c6="KMP. TES")],
            _baris(c0="No.", c1="Nama Barang", c10="Volume", c12="Harga (Rp.)", c14="KETERANGAN"),
            _baris(c10="Qty", c11="Sat", c12="Satuan", c13="Jumlah"),
            [_baris(c0="I", c1="PELAYANAN UMUM"),
             _baris(c0=1, c1="Kapal naik dock", c10=1, c11="Ls", c12=7_500_000)],
        ),
        "portlink.xlsx",
    )

    assert [i["uraian"] for i in hasil["induk"]] == ["Kapal naik dock"]
    assert hasil["induk"][0]["harga"] == 7_500_000


# --- kolom harga bernama "INDUK (Rp.)" --------------------------------------------------

def test_kolom_harga_boleh_bernama_induk():
    """Laporan realisasi (LCT. ARJHUNA 2025) menamai kolom harga pokoknya "INDUK (Rp.)",
    berdampingan dengan BATAL / TAMBAHAN / REALISASI. Tanpa alternatif ini tidak ada
    satu pun kolom harga yang ketemu, dan 214 baris terbaca nol."""
    hasil = parse_docking_file(
        _berkas(
            [_baris(c1="NAMA KAPAL", c4=":", c5="LCT. TES")],
            _baris(c0="NO.", c1="URAIAN PEKERJAAN", c9="VOLUME", c13="INDUK (Rp.)",
                   c15="BATAL (Rp.)", c17="TAMBAHAN (Rp.)", c19="REALISASI (Rp.)", c21="KETERANGAN"),
            _baris(c9="Qty", c10="Sat", c13="Satuan", c14="Jumlah",
                   c15="Satuan", c16="Jumlah", c17="Satuan", c18="Jumlah"),
            [_baris(c0="I", c1="PELAYANAN UMUM"),
             _baris(c0=1, c1="Kapal masuk dan keluar dock", c9=1, c10="Ls", c13=7_500_000)],
        ),
        "arjhuna.xlsx",
    )

    assert [i["uraian"] for i in hasil["induk"]] == ["Kapal masuk dan keluar dock"]
    assert hasil["induk"][0]["harga"] == 7_500_000


def test_kolom_tambahan_tetap_masuk_addendum():
    """Jangan sampai menerima "INDUK" bikin kolom TAMBAHAN ikut terbaca sebagai harga pokok."""
    hasil = parse_docking_file(
        _berkas(
            [_baris(c1="NAMA KAPAL", c4=":", c5="LCT. TES")],
            _baris(c0="NO.", c1="URAIAN PEKERJAAN", c9="VOLUME", c13="INDUK (Rp.)",
                   c17="TAMBAHAN (Rp.)", c21="KETERANGAN"),
            _baris(c9="Qty", c10="Sat", c13="Satuan", c14="Jumlah", c17="Satuan", c18="Jumlah"),
            [_baris(c0="I", c1="PELAYANAN UMUM"),
             _baris(c0=1, c1="Kerja pokok", c9=1, c10="Ls", c13=1_000_000),
             _baris(c0=2, c1="Kerja ekstra", c9=1, c10="Ls", c17=500_000, c21="pekerjaan tambahan")],
        ),
        "arjhuna.xlsx",
    )

    assert [i["uraian"] for i in hasil["induk"]] == ["Kerja pokok"]
    assert [i["uraian"] for i in hasil["addendum"]] == ["Kerja ekstra"]


# --- nama kapal tanpa label "NAMA KAPAL" ------------------------------------------------

def _kepala_lampiran():
    return [
        _baris(c0="Lampiran ", c3=":  2.00143/SW08/DK/SPJ/JN/II/2024"),
        _baris(c0="Tanggal", c3=":  05 Februari 2024"),
        _baris(c0="Pengadaan", c3=":  Perjanjian pekerjaan docking induk"),
        _baris(c0="Lokasi", c3=":  KMP. Marina Segunda di Galangan PT. Dukuh Raya"),
    ]


def test_nama_kapal_terbaca_dari_baris_lokasi():
    """Berkas Lampiran Perjanjian tidak punya label "NAMA KAPAL" sama sekali."""
    kapal, _, _ = guess_header(_kepala_lampiran(), "01. LAMPIRAN PERJANJIAN.xlsx", "LAMPIRAN")

    assert kapal == "KMP. Marina Segunda"


def test_keterangan_tempat_dipotong_dari_nama_kapal():
    assert guess_header(_kepala_lampiran(), "x.xlsx")[0] == "KMP. Marina Segunda"


def test_tahun_diambil_dari_tanggal_perjanjian():
    """Lebih dekat ke waktu pekerjaan daripada tahun di nama berkas."""
    _, _, tahun = guess_header(_kepala_lampiran(), "tanpa-tahun.xlsx")

    assert tahun == "2024"


def test_label_nama_kapal_tetap_menang_atas_tebakan():
    kepala = _kepala_lampiran() + [_baris(c0="NAMA KAPAL", c2=":", c3="KMP. YANG BENAR")]

    assert guess_header(kepala, "x.xlsx")[0] == "KMP. YANG BENAR"


@pytest.mark.parametrize(
    "teks,harapan",
    [
        (":  KMP. Prima Nusantara di dock", "KMP. Prima Nusantara"),
        (":  LCT. Arjhuna pada galangan", "LCT. Arjhuna"),
        (":  MV. Aqua Blu", "MV. Aqua Blu"),
    ],
)
def test_bermacam_awalan_nama_kapal(teks, harapan):
    assert guess_header([_baris(c0="Lokasi", c3=teks)], "x.xlsx")[0] == harapan


def test_kata_biasa_tidak_disangka_nama_kapal():
    """Pola nama kapal tidak boleh menangkap kata yang kebetulan diawali huruf yang sama."""
    kepala = [_baris(c0="Lokasi", c3=":  Galangan Kmpuh Raya"), _baris(c0="Catatan", c3="TBC")]

    assert guess_header(kepala, "tanpa-kapal.xlsx")[0] == ""


# --- tahun terpecah di dua sel ----------------------------------------------------------

def test_tahun_terpecah_bulan_dan_angka_di_sel_berbeda():
    """"PERIODE DOCKING : Nopember 2025" ditulis di dua sel; sel pertama cuma bulannya.

    Sebelum ini kolom Tahun terisi "Nopember", dan nilai itu ikut jadi prefix ID baris.
    """
    kepala = [
        _baris(c0="NAMA KAPAL", c2=":", c3="MV. TES"),
        _baris(c0="PERIODE DOCKING", c2=":", c3="Nopember", c4=2025),
    ]

    _, _, tahun = guess_header(kepala, "berkas.xlsx")

    assert tahun == "2025"


def test_tahun_yang_sudah_benar_tidak_diutak_atik():
    kepala = [_baris(c0="PERIODE DOCKING", c2=":", c3="2026")]

    assert guess_header(kepala, "x.xlsx")[2] == "2026"


def test_tahun_dari_nama_sheet_kalau_kepala_diam():
    _, _, tahun = guess_header([_baris(c0="Lokasi", c3="KMP. TES")], "tanpa.xlsx", "KMP. TES - 2026")

    assert tahun == "2026"
