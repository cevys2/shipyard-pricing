"""File Biaya Docking dari repair list: semua baris ikut, urutannya persis, rumusnya hidup.

Berkas contohnya dibangun di memori, meniru bentuk dan jebakan repair list KMP Gerbang
Samudra 3 2026 -- bukan seluruh isinya. Terhadap berkas aslinya sudah dicek di luar tes
(23 Oktober 2026): 74/74 baris sama dengan Biaya Docking GS3 final buatan tangan, dan setelah
harga finalnya diisi, Excel menghitung TOTAL Rp 733.961.970 -- persis sama -- dengan
terbilang yang benar.
"""

import io
from datetime import date, datetime

import openpyxl
import pytest
from openpyxl import Workbook

from app.services import biaya_docking
from app.services.repair_list_parser import baca_lingkup


def _berkas(rows) -> bytes:
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_GS3 = [
    ("REPAIR LIST",),
    ("(Tahun 2026)",),
    (1, "NAMA KAPAL", "KMP. CONTOH"),
    (13, "NAIK DOCK", datetime(2026, 11, 3)),
    ("NO.", "URAIAN", "QTY", "SAT.", "KETERANGAN"),
    ("I", "PELAYANAN UMUM KAPAL"),
    (1, "Docking report (6 Rangkap)", 1, "Ls"),
    ("II", "DOCKING dan UNDOCKING"),
    (4, "Kapal melaksanakan docking dan floating repair"),
    (4.1, "Docking", 14, "Hari"),
    (None, "Pembersihan dan pengecatan"),  # sub-judul tanpa nomor
    # "C" angka romawi yang sah, tapi sesudah seksi II dia bernilai 100, bukan 3.
    ("C", "Main Deck"),
    ("a.", "Valve dilepas dari kedudukannya"),
    (1, "Valve Uk. 10K 200", 1, "buah", "Owner supply"),
    (None, None, None, "Surabaya, 25 September 2026"),
    (None, "Mengetahui,"),  # blok tanda tangan yang mendarat di kolom uraian
]


def test_semua_baris_ikut_persis_urutannya():
    lingkup = baca_lingkup(_berkas(_GS3), "gs3.xlsx")
    assert [(b["no"], b["uraian"], b["qty"], b["satuan"]) for b in lingkup["baris"]] == [
        ("I", "PELAYANAN UMUM KAPAL", None, None),
        ("1", "Docking report (6 Rangkap)", 1, "Ls"),
        ("II", "DOCKING dan UNDOCKING", None, None),
        ("4", "Kapal melaksanakan docking dan floating repair", None, None),
        ("4.1", "Docking", 14, "Hari"),
        ("", "Pembersihan dan pengecatan", None, None),
        ("C", "Main Deck", None, None),
        ("a.", "Valve dilepas dari kedudukannya", None, None),
        ("1", "Valve Uk. 10K 200", 1, "buah"),
    ]
    assert [b["no"] for b in lingkup["baris"] if b["seksi"]] == ["I", "II"]
    assert lingkup["baris"][-1]["keterangan"] == "Owner supply"


def test_ekor_tanda_tangan_dibuang_dan_disebut():
    lingkup = baca_lingkup(_berkas(_GS3), "gs3.xlsx")
    assert all("Mengetahui" not in b["uraian"] for b in lingkup["baris"])
    assert any("Mengetahui" in p for p in lingkup["peringatan"])


def test_gaya_basarnas_volume_dua_kolom_dan_uraian_melebar():
    """VOL | SAT di baris sub-judul, "SATUAN" di baris judul = kolom HARGA satuan."""
    rows = [
        ("REPAIR LIST",),
        ("NO", "URAIAN PEKERJAAN", None, "VOLUME", None, "SATUAN", "TOTAL", "KET"),
        (None, None, None, "VOL", "SAT"),
        (1, 2, None, 3, 4, 5, 7, 8),  # baris penomoran kolom, bukan data
        ("A", "Pekerjaan Docking/General Service", None, 1, "Ls", 100),
        ("B", "LAMBUNG KAPAL"),
        (None, "a", "Pembersihan lambung", 273, "m²", 20),
        (None, "-", "1 x Primer", 273, "m²", 200),
    ]
    lingkup = baca_lingkup(_berkas(rows), "basarnas.xlsx")
    assert [(b["uraian"], b["qty"], b["satuan"]) for b in lingkup["baris"]] == [
        ("Pekerjaan Docking/General Service", 1, "Ls"),
        ("LAMBUNG KAPAL", None, None),
        ("a Pembersihan lambung", 273, "m²"),
        ("- 1 x Primer", 273, "m²"),
    ]


def test_qty_bukan_angka_ditulis_apa_adanya_dan_disebut():
    rows = [("NO", "URAIAN", "QTY", "SAT"), (1, "Cleaning tangki", "1 set", None), (2, "Docking", 3, "Hari")]
    lingkup = baca_lingkup(_berkas(rows), "x.xlsx")
    assert lingkup["baris"][0]["qty"] == "1 set"
    assert any("1 set" in p for p in lingkup["peringatan"])


def test_tanpa_baris_judul_gagal_keras():
    with pytest.raises(ValueError, match="URAIAN"):
        baca_lingkup(_berkas([("Daftar pekerjaan",), ("Cleaning", 1)]), "x.xlsx")


def test_file_biaya_docking_harga_kosong_rumus_hidup():
    lingkup = baca_lingkup(_berkas(_GS3), "gs3.xlsx")
    wb = openpyxl.load_workbook(io.BytesIO(biaya_docking.buat(lingkup, date(2026, 10, 23))))
    ws = wb["Biaya Docking"]
    r0 = 30
    akhir = r0 + len(lingkup["baris"]) - 1
    assert ws.cell(r0, 2).value == "PELAYANAN UMUM KAPAL"
    assert ws.cell(akhir, 2).value == "Valve Uk. 10K 200"

    for k, b in enumerate(lingkup["baris"]):
        r = r0 + k
        assert ws.cell(r, 6).value is None  # harga satuan: diisi Lutfi di Excel
        assert ws.cell(r, 7).value == (f"=F{r}*D{r}" if b["qty"] is not None else None)

    # Tepat di bawah item terakhir, tanpa apa pun di antaranya.
    assert [ws.cell(akhir + k, 6).value for k in (1, 2, 3)] == ["Jumlah Rp.", "PPN 11% Rp.", "TOTAL Rp."]
    assert ws.cell(akhir + 1, 7).value == f"=SUM(G{r0}:G{akhir})"
    assert ws.cell(akhir + 2, 7).value == f"=G{akhir + 1}*11%"
    assert ws.cell(akhir + 3, 7).value == f"=G{akhir + 1}+G{akhir + 2}"

    # Terbilang ikut TOTAL lewat sheet tersembunyi, bukan teks mati.
    tb = wb["terbilang"]
    assert tb.sheet_state == "hidden"
    assert tb["B1"].value == f"=ROUND('Biaya Docking'!G{akhir + 3},0)"
    assert ws.cell(akhir + 5, 3).value == "=terbilang!$B$6"
    assert tb.cell(115 + 1, 1).value == "Seratus Lima Belas"


@pytest.mark.parametrize(
    "n, kata",
    [
        (0, ""), (1, "Satu"), (10, "Sepuluh"), (11, "Sebelas"), (12, "Dua Belas"),
        (19, "Sembilan Belas"), (20, "Dua Puluh"), (21, "Dua Puluh Satu"), (100, "Seratus"),
        (101, "Seratus Satu"), (111, "Seratus Sebelas"), (200, "Dua Ratus"),
        (961, "Sembilan Ratus Enam Puluh Satu"), (999, "Sembilan Ratus Sembilan Puluh Sembilan"),
    ],
)
def test_kata_ratusan(n, kata):
    assert biaya_docking.kata_ratusan(n) == kata
