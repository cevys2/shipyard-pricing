"""`kunci_data_kapal()` di app/services/repair_list_parser.py.

Semua label di bawah diambil dari berkas asli: repair list GS3 2026, Biaya Docking GS3 final,
dan Biaya Docking MV. Bounty Cruise 2026. Kalau semuanya hijau, data kapal di file Biaya
Docking ikut terisi dari repair list.
"""

import pytest

from app.services.repair_list_parser import kunci_data_kapal


@pytest.mark.parametrize(
    "label, kunci",
    [
        ("NOMOR ORDER", "nomor_order"),
        ("NAMA KAPAL", "nama_kapal"),
        (" PEMILIK ", "pemilik"),
        ("TAHUN PEMBUATAN", "tahun_pembuatan"),
        ("KLASIFIKASI KAPAL", "klasifikasi"),
        ("K L A S S", "klasifikasi"),
        ("KONSTRUKSI KAPAL", "konstruksi"),
        ("JENIS/TYPE KAPAL", "jenis_kapal"),
        ("WILAYAH OPERASI", "wilayah_operasi"),
        ("STATUS SURVEY", "status_survey"),
        ("JENIS SURVEY", "status_survey"),
        ("PANJANG SELURUHNYA ( LOA )", "loa"),
        ("Panjang Seluruh ( L.O.A )", "loa"),
        ("PANJANG GARIS AIR ( LBP )", "lbp"),
        ("Panjang Garis Antara ( L.B.P )", "lbp"),
        ("LEBAR ( B )", "lebar"),
        ("DALAM/TINGGI ( D )", "dalam"),
        ("Dalam Garis Muat ( D )", "dalam"),
        ("DRAFT / Sarat Air ( d )", "sarat"),
        ("draught( d ) max", "sarat"),
        ("GT/GRT/NRT", "gt"),
        ("GRT/NRT", "gt"),
        ("DAYA MESIN", "daya_mesin"),
        ("MAIN ENGINE", "daya_mesin"),
        ("NAIK DOCK", "naik_dock"),
        ("TURUN DOCK", "turun_dock"),
    ],
)
def test_label_dikenali(label, kunci):
    assert kunci_data_kapal(label) == kunci


@pytest.mark.parametrize(
    "teks",
    [
        "UKURAN UTAMA KAPAL",  # judul kelompok, nilainya ada di baris-baris bawahnya
        "KMP. GERBANG SAMUDRA 3",  # nilai, bukan label
        "Meter",
        "PERIODE DOCKING",  # ada kata DOCK, tapi bukan naik/turun dock
        "AUXILIARY ENGINE",  # ada kata ENGINE, tapi tidak punya tempat di Biaya Docking
        "KEAGENNAN",
        "",
    ],
)
def test_bukan_label(teks):
    assert kunci_data_kapal(teks) is None
