"""Template laporan docking tidak seragam, dan tiap ketidakseragaman pernah bikin nol baris.

Empat berkas di arsip gagal terbaca sama sekali sebelum perbaikan 24 Agustus 2026, dan
semuanya gagal DIAM-DIAM: parser mengembalikan daftar kosong, bukan error. Berkas yang
"berhasil diimpor 0 baris" terlihat sama persis dengan berkas yang memang kosong.

Yang ditiru di sini bentuk kepalanya saja, secukupnya untuk memicu tiap kegagalan.
"""

import datetime
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


# --- sub-header harga bernama "Sat", bukan "Satuan" -------------------------------------

def _berkas_prathita(**sel_baris) -> bytes:
    """Bentuk kepala "Docking DEAL KMP. PRATHITA IV": sub-kolom harga satuan berjudul "Sat".

    Kata yang sama persis dengan sub-kolom satuan di grup VOLUME, dan itu yang bikin
    pencocokan sama-persis meleset.
    """
    return _berkas(
        [_baris(c0="DATA - DATA KAPAL"), _baris(c0=2, c1="NAMA KAPAL", c4=": KMP PRATHITA IV")],
        _baris(c0="No", c1="URAIAN", c13="VOLUME", c15="HARGA (Rp.)", c17="KETERANGAN"),
        _baris(c13="Qty", c14="Sat", c15="Sat", c16="Jumlah"),
        [_baris(c0="I", c1="BAGIAN UMUM"), _baris(**sel_baris)],
    )


def test_sub_header_sat_tidak_bikin_angka_total_jadi_harga_satuan():
    """Kegagalan paling mahal sejauh ini, dan sepenuhnya tanpa suara.

    Fallback lama `cols[-1]` memilih kolom TERAKHIR grup HARGA -- kolom Jumlah -- lalu
    seluruh 154 baris berkas PRATHITA IV masuk katalog dengan angka total sebagai harga
    satuan. Jumlah seluruh "harga satuan" persis sama dengan angka JUMLAH di berkas.
    """
    hasil = parse_docking_file(
        _berkas_prathita(c0=3, c1="Penggunaan listrik harian",
                         c13=19, c14="hari", c15=700_000, c16=13_300_000),
        "Docking  DEAL  KMP. PRATHITA IV.xlsx",
    )

    (baris,) = hasil["induk"]
    assert baris["harga"] == 700_000, "kolom Jumlah terbaca sebagai harga satuan"
    assert baris["volume"] == 19
    assert baris["volume"] * baris["harga"] == 13_300_000


def test_palang_bunyi_kalau_satuan_dan_jumlah_jatuh_ke_kolom_yang_sama():
    """Grup harga tiga kolom yang sub-header satuannya hilang sama sekali.

    'satuan' jatuh ke posisi paling kiri, dan di situ justru duduk "Jumlah". Parser tidak
    punya cara tahu mana yang benar -- yang penting dia bilang, bukan diam.
    """
    hasil = parse_docking_file(
        _berkas(
            [_baris(c0="NAMA KAPAL", c2=":", c3="KMP. TES")],
            _baris(c0="No", c1="URAIAN", c13="VOLUME", c15="HARGA (Rp.)", c18="KETERANGAN"),
            _baris(c13="Qty", c14="Sat", c15="Jumlah"),
            [_baris(c0=1, c1="Kerja", c13=2, c14="Ls", c15=1_000_000)],
        ),
        "aneh.xlsx",
    )

    assert any("kolom yang sama" in w for w in hasil["warnings"])


# --- label dan nilai menyatu di satu sel ------------------------------------------------

def test_titik_dua_yang_menyatu_dengan_nilai_tidak_ikut_terbaca():
    """": KMP PRATHITA IV" dalam SATU sel, bukan ":" dan nilainya di sel terpisah.

    Titik duanya dulu ikut ke nama kapal, lalu ikut jadi prefix ID baris.
    """
    kepala = [
        _baris(c0=2, c1="NAMA KAPAL", c4=": KMP PRATHITA IV"),
        _baris(c0=3, c1="PEMILIK", c4=": PT. ASDP Indonesia Ferry (persero)"),
    ]

    kapal, pemilik, _ = guess_header(kepala, "x.xlsx")

    assert kapal == "KMP PRATHITA IV"
    assert pemilik == "PT. ASDP Indonesia Ferry (persero)"


# --- tahun untuk berkas yang tidak menyebut PERIODE DOCKING -----------------------------

def test_tahun_dari_tanggal_naik_dock_diambil_tahunnya_saja():
    kepala = [
        _baris(c0="NAMA KAPAL", c2=":", c3="KMP. TES"),
        _baris(c0="NAIK DOCK", c2=":", c3=datetime.datetime(2025, 2, 10)),
    ]

    _, _, tahun = guess_header(kepala, "tanpa-tahun.xlsx")

    assert tahun == "2025", "tanggal penuh tidak boleh masuk utuh ke kolom Tahun"


def test_tahun_ditebak_dari_sel_tanggal_dan_dikatakan_bahwa_itu_tebakan():
    """PRATHITA IV tidak punya PERIODE DOCKING dan nama berkasnya tidak menyebut tahun.

    Satu-satunya waktu yang tertulis: dua sel tanggal telanjang di blok tanda tangan.
    """
    kepala = [_baris(c0="NAMA KAPAL", c2=":", c3="KMP. TES"), _baris(c20=datetime.datetime(2025, 2, 10))]
    catatan: list[str] = []

    _, _, tahun = guess_header(kepala, "tanpa-tahun.xlsx", "Sheet1", catatan)

    assert tahun == "2025"
    assert any("ditebak" in c for c in catatan), "tebakan harus terdengar, bukan diam"


def test_tahun_pembuatan_kapal_tidak_dikira_tahun_pekerjaan():
    """Kapal yang dibangun sesudah 2000 punya angka yang lolos YEAR_RE."""
    kepala = [
        _baris(c0="TAHUN PEMBUATAN", c2=":", c3=datetime.datetime(2015, 6, 1)),
        _baris(c20=datetime.datetime(2025, 2, 10)),
    ]

    _, _, tahun = guess_header(kepala, "tanpa-tahun.xlsx")

    assert tahun == "2025"
