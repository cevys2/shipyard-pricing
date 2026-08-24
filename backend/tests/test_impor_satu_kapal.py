"""Satu berkas = satu kapal + satu tahun.

Sebelum palang ini, `parse_spreadsheet()` mengambil Kapal, Tahun, Perusahaan, dan Tipe dari
BARIS PERTAMA YANG TERISI lalu memakainya untuk seluruh berkas. Berkas berisi tiga kapal
tetap diproses sampai selesai: semua barisnya tercatat atas nama kapal yang kebetulan
muncul paling atas, tanpa peringatan apa pun.

Ini bukan hipotesis. Zip repair list yang masuk 22 Agustus 2026 berisi tiga kapal, dan
menggabungkannya jadi satu berkas supaya "sekali impor" adalah hal yang wajar dilakukan
orang. Kalau itu terjadi, 385 baris masuk atas nama kapal yang salah -- dan karena kapal
dan tahun ikut membentuk prefix ID baris, salahnya permanen di primary key.

Kapal dan tahun MENOLAK berkasnya. Perusahaan dan tipe cuma memperingatkan: keduanya tidak
ikut ke ID, jadi masih bisa diperbaiki lewat layar edit.
"""

import io

import pytest
from openpyxl import Workbook

from app.services.catalog import parse_spreadsheet

HEADER = ("Nama Kapal", "Tahun", "Perusahaan", "Tipe", "Kategori", "Uraian Pekerjaan", "Satuan", "Harga")


def _excel(baris, header=HEADER) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(list(header))
    for b in baris:
        ws.append(list(b))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _baris(kapal, tahun="2026", pt="BASARNAS", tipe="Induk", uraian="Sandblasting lambung"):
    return [kapal, tahun, pt, tipe, "DOCKING", uraian, "m2", 50000]


def test_berkas_tiga_kapal_ditolak_bukan_diam_diam_dipakai_yang_pertama():
    bulk, errors = parse_spreadsheet(
        _excel(
            [
                _baris("KN SAR 207"),
                _baris("KN SAR ANTAREJA 233"),
                _baris("KN SAR WIDURA 225"),
            ]
        ),
        "gabungan.xlsx",
    )

    assert bulk is None, "berkas tiga kapal masih diproses -- semua baris akan salah kapal"
    (pesan,) = errors
    assert "3 kapal" in pesan
    for kapal in ("KN SAR 207", "KN SAR ANTAREJA 233", "KN SAR WIDURA 225"):
        assert kapal in pesan, "pesan harus menyebut kapalnya, bukan cuma bilang gagal"


def test_berkas_dua_tahun_juga_ditolak():
    bulk, errors = parse_spreadsheet(
        _excel([_baris("KMP. MISHIMA", "2025"), _baris("KMP. MISHIMA", "2026")]),
        "dua-tahun.xlsx",
    )

    assert bulk is None
    assert "2 tahun" in errors[0]
    assert "2025" in errors[0] and "2026" in errors[0]


def test_satu_kapal_satu_tahun_lewat_seperti_biasa():
    """Palangnya tidak boleh mengubah perilaku berkas yang selama ini sudah benar."""
    bulk, errors = parse_spreadsheet(
        _excel([_baris("KMP. MISHIMA", uraian="Sandblasting"), _baris("KMP. MISHIMA", uraian="Pengecatan AC")]),
        "normal.xlsx",
    )

    assert bulk is not None
    assert errors == []
    assert bulk.nama_kapal == "KMP. MISHIMA"
    assert bulk.tahun == "2026"
    assert len(bulk.items) == 2


def test_tahun_2026_dan_2026_koma_nol_bukan_dua_tahun():
    """Satu sel kosong di kolom Tahun membuat pandas membaca seluruh kolomnya float64.

    Kalau pembulatannya tidak ikut dipakai waktu menghitung nilai unik, berkas yang
    sebenarnya seragam akan tertolak palang ini gara-gara "2026" vs "2026.0".
    """
    baris = [_baris("KMP. MISHIMA", 2026), _baris("KMP. MISHIMA", 2026)]
    baris.append([None, None, None, None, None, "TOTAL", None, 100000])

    bulk, errors = parse_spreadsheet(_excel(baris), "float.xlsx")

    assert bulk is not None, f"tertolak padahal tahunnya sama: {errors}"
    assert bulk.tahun == "2026"


@pytest.mark.parametrize(
    "kolom,nilai_a,nilai_b,sebut",
    [("pt", "BASARNAS", "PT JEMLA FERRY", "Perusahaan"), ("tipe", "Induk", "Addendum", "Tipe")],
)
def test_perusahaan_dan_tipe_cuma_memperingatkan(kolom, nilai_a, nilai_b, sebut):
    """Tidak ikut ke prefix ID, jadi masih bisa dibetulkan -- tapi tetap harus berbunyi."""
    bulk, errors = parse_spreadsheet(
        _excel(
            [
                _baris("KMP. MISHIMA", **{kolom: nilai_a}),
                _baris("KMP. MISHIMA", **{kolom: nilai_b}),
            ]
        ),
        "campur.xlsx",
    )

    assert bulk is not None, "ini peringatan, bukan penolakan"
    assert any(sebut in e and nilai_a in e for e in errors), errors


def test_kolom_kapal_kosong_sebagian_tidak_dianggap_dua_kapal():
    """Sel kosong di tengah berkas lazim (baris pemisah); yang dihitung cuma yang terisi."""
    baris = [_baris("KMP. MISHIMA"), [None, None, None, None, None, "Pengecatan", "m2", 60000]]

    bulk, errors = parse_spreadsheet(_excel(baris), "kosong.xlsx")

    assert bulk is not None, errors
    assert bulk.nama_kapal == "KMP. MISHIMA"


def test_kolom_baru_ikut_terbaca_kalau_ada():
    """Vol / Sat / Induk / Ket boleh ada di berkas rapi, dan tidak wajib."""
    header = (*HEADER, "Vol", "Sat", "Induk", "Ket")
    baris = [(*_baris("KMP. MISHIMA"), 269, "m2", "Lambung Kapal Dibawah Garis Air", "catatan")]

    bulk, errors = parse_spreadsheet(_excel(baris, header), "lengkap.xlsx")

    assert bulk is not None, errors
    (item,) = bulk.items
    assert item.volume == 269
    assert item.satuan == "m2"
    assert item.induk_uraian == "Lambung Kapal Dibawah Garis Air"
    assert item.keterangan == "catatan"
    assert item.volume_satuan == "m2", "kolom lama tidak boleh berubah artinya"


def test_kolom_satuan_lama_tetap_mengisi_volume_satuan():
    """Berkas lama tidak punya Vol/Sat; kolom "Satuan" harus tetap ke `volume_satuan`."""
    bulk, _ = parse_spreadsheet(_excel([_baris("KMP. MISHIMA")]), "lama.xlsx")

    (item,) = bulk.items
    assert item.volume_satuan == "m2"
    assert item.volume is None
    assert item.satuan is None
