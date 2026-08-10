"""Sesi 3.1 -- perhitungan AHSP.

Yang diuji di sini bukan "apakah angkanya keluar", tapi apakah aplikasinya menolak
mengeluarkan angka waktu memang tidak boleh: komponen tanpa harga tidak dianggap nol,
mata uang campur tidak dijumlahkan, dan simpan separuh tidak pernah terjadi.
"""

from decimal import Decimal

import pytest
from sqlalchemy import text

from app.database import engine, ensure_ahsp_tables, ensure_kategori_table, ensure_material_tables
from app.schemas.ahsp import AhspCreate, KomponenInput
from app.schemas.material import BulkMaterialCreate, BulkPatchMaterialRequest, MaterialItemCreate
from app.services import ahsp as svc
from app.services import material as material_svc


@pytest.fixture(autouse=True)
def tabel_ahsp_bersih():
    ensure_material_tables()
    # Urutan yang sama dengan lifespan: ahsp.kategori_id menunjuk ke kategori(id).
    ensure_kategori_table()
    ensure_ahsp_tables()
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE ahsp, ahsp_komponen, sumber_daya, sumber_daya_harga, supplier "
                "RESTART IDENTITY CASCADE"
            )
        )
    yield


def _sumber_daya(nama: str, jenis: str, harga: float, satuan: str = "Kg", mata_uang: str = "IDR") -> int:
    """Bikin satu master + satu titik harga lewat jalur yang dipakai aplikasi sungguhan."""
    material_svc.bulk_create(
        BulkMaterialCreate(
            items=[
                MaterialItemCreate(
                    nama=nama,
                    satuan=satuan,
                    harga_satuan=harga,
                    mata_uang=mata_uang,
                    tahun_pembelian=2026,
                )
            ]
        ),
        aktor="tes",
        jenis=jenis,
    )
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT id FROM sumber_daya WHERE nama = :n AND jenis = :j"),
            {"n": nama, "j": jenis},
        ).scalar()


def _sumber_daya_tanpa_harga(nama: str, jenis: str, satuan: str = "Ls") -> int:
    """Master tanpa satu pun baris harga -- ini yang tidak boleh dihitung sebagai nol."""
    with engine.begin() as conn:
        return conn.execute(
            text(
                "INSERT INTO sumber_daya (nama, satuan, jenis) VALUES (:n, :s, :j) RETURNING id"
            ),
            {"n": nama, "s": satuan, "j": jenis},
        ).scalar()


def _ahsp(uraian: str = "Pengecatan lambung", satuan: str = "m2") -> int:
    return svc.create_ahsp(AhspCreate(uraian=uraian, satuan=satuan), aktor="tes")


def test_dua_komponen_berharga_harga_jual_sama_dengan_jumlah_subtotal():
    cat = _sumber_daya("Cat Epoxy", "BAHAN", 100_000.0)
    tukang = _sumber_daya("Tukang Cat", "UPAH", 150_000.0, satuan="OH")
    a = _ahsp()
    svc.ganti_komponen(
        a,
        [
            KomponenInput(sumber_daya_id=cat, kelompok="BAHAN", qty=Decimal("2")),
            KomponenInput(sumber_daya_id=tukang, kelompok="UPAH", qty=Decimal("1")),
        ],
        aktor="tes",
    )

    h = svc.hitung(a)
    assert h["subtotal"]["BAHAN"] == Decimal("200000")
    assert h["subtotal"]["UPAH"] == Decimal("150000")
    assert h["subtotal_total"] == Decimal("350000")
    assert h["harga_jual"] == h["subtotal_total"], "tidak boleh ada markup di tingkat AHSP"
    assert h["rumus_terpasang"] is True
    assert h["lengkap"] is True and h["alasan"] == []


def test_empat_pengali_dikalikan_semua():
    """qty x shift x jml_hari x harga -- 4 orang, 1 shift, 0,07 hari, 50.000 = 14.000.

    Sengaja dengan Decimal: dalam float hasilnya 14000.000000000002.
    """
    tukang = _sumber_daya("Tukang Las", "UPAH", 50_000.0, satuan="OH")
    a = _ahsp("Penggantian plat", "kg")
    svc.ganti_komponen(
        a,
        [
            KomponenInput(
                sumber_daya_id=tukang,
                kelompok="UPAH",
                qty=Decimal("4"),
                shift=Decimal("1"),
                jml_hari=Decimal("0.07"),
            )
        ],
        aktor="tes",
    )
    assert svc.hitung(a)["subtotal"]["UPAH"] == Decimal("14000")


def test_komponen_tanpa_harga_bukan_nol_dan_disebut_di_alasan():
    cat = _sumber_daya("Cat Epoxy", "BAHAN", 100_000.0)
    sandblasting = _sumber_daya_tanpa_harga("Sandblasting", "ALAT")
    a = _ahsp()
    svc.ganti_komponen(
        a,
        [
            KomponenInput(sumber_daya_id=cat, kelompok="BAHAN"),
            KomponenInput(sumber_daya_id=sandblasting, kelompok="ALAT"),
        ],
        aktor="tes",
    )

    h = svc.hitung(a)
    assert h["lengkap"] is False
    assert any("Sandblasting" in a_ for a_ in h["alasan"])
    # Subtotal ALAT tetap nol karena memang belum ada angkanya -- yang penting
    # AHSP-nya tidak lolos sebagai "lengkap" dan harga jualnya ditahan.
    assert h["subtotal"]["BAHAN"] == Decimal("100000")
    assert h["harga_jual"] is None, "AHSP yang bolong tidak boleh mengeluarkan harga jual"


def test_komponen_non_idr_tidak_dijumlahkan_dan_tidak_dikonversi():
    lokal = _sumber_daya("Elektroda", "KONSUMABEL", 50_000.0)
    impor = _sumber_daya("Seal Impor", "BAHAN", 45.10, mata_uang="EUR")
    a = _ahsp()
    svc.ganti_komponen(
        a,
        [
            KomponenInput(sumber_daya_id=lokal, kelompok="KONSUMABEL"),
            KomponenInput(sumber_daya_id=impor, kelompok="BAHAN"),
        ],
        aktor="tes",
    )

    h = svc.hitung(a)
    assert h["lengkap"] is False
    assert any("EUR" in a_ for a_ in h["alasan"])
    assert h["subtotal"]["BAHAN"] == Decimal("0"), "harga EUR tidak boleh ikut dijumlahkan"
    assert h["subtotal"]["KONSUMABEL"] == Decimal("50000")


def test_put_komponen_dengan_satu_baris_rusak_tidak_menyimpan_apa_pun():
    """Rollback penuh. Separuh tersimpan lebih berbahaya daripada gagal seluruhnya."""
    cat = _sumber_daya("Cat Epoxy", "BAHAN", 100_000.0)
    a = _ahsp()
    svc.ganti_komponen(a, [KomponenInput(sumber_daya_id=cat, kelompok="BAHAN")], aktor="tes")

    with pytest.raises(Exception):
        svc.ganti_komponen(
            a,
            [
                KomponenInput(sumber_daya_id=cat, kelompok="BAHAN", qty=Decimal("9")),
                KomponenInput(sumber_daya_id=999_999, kelompok="UPAH"),  # tidak ada di sumber_daya
            ],
            aktor="tes",
        )

    sisa = svc.komponen(a)
    assert len(sisa) == 1 and sisa[0]["qty"] == Decimal("1.000000"), (
        "DELETE lama ikut ter-rollback, jadi rincian sebelumnya harus utuh apa adanya"
    )


def test_komponen_kembar_ditolak_dengan_pesan_yang_menjelaskan():
    cat = _sumber_daya("Cat Epoxy", "BAHAN", 100_000.0)
    a = _ahsp()
    with pytest.raises(ValueError, match="dua kali"):
        svc.ganti_komponen(
            a,
            [
                KomponenInput(sumber_daya_id=cat, kelompok="BAHAN"),
                KomponenInput(sumber_daya_id=cat, kelompok="BAHAN"),
            ],
            aktor="tes",
        )


def test_ahsp_tanpa_komponen_belum_lengkap():
    a = _ahsp()
    h = svc.hitung(a)
    assert h["lengkap"] is False and h["subtotal_total"] == Decimal("0")
    assert h["harga_jual"] is None


def test_ringkas_menghitung_yang_lengkap_saja():
    cat = _sumber_daya("Cat Epoxy", "BAHAN", 100_000.0)
    kosong = _sumber_daya_tanpa_harga("Perancah", "ALAT")

    penuh = _ahsp("Pengecatan lambung", "m2")
    svc.ganti_komponen(penuh, [KomponenInput(sumber_daya_id=cat, kelompok="BAHAN")], aktor="tes")
    bolong = _ahsp("Sandblasting", "m2")
    svc.ganti_komponen(bolong, [KomponenInput(sumber_daya_id=kosong, kelompok="ALAT")], aktor="tes")
    _ahsp("Belum diisi", "Ls")

    r = svc.ringkas()
    assert r["total"] == 3 and r["lengkap"] == 1 and r["komponen_tanpa_harga"] == 1


def test_urutan_kelompok_ikut_kolom_urutan_bukan_abjad_jenis():
    """Di file asli urutan kelompok berbeda-beda per pekerjaan, jadi tidak boleh dipatok."""
    cat = _sumber_daya("Cat Epoxy", "BAHAN", 100_000.0)
    tukang = _sumber_daya("Tukang Cat", "UPAH", 150_000.0, satuan="OH")
    a = _ahsp()
    svc.ganti_komponen(
        a,
        [
            KomponenInput(sumber_daya_id=cat, kelompok="BAHAN", urutan=2),
            KomponenInput(sumber_daya_id=tukang, kelompok="UPAH", urutan=1),
        ],
        aktor="tes",
    )
    assert [k["kelompok"] for k in svc.komponen(a)] == ["UPAH", "BAHAN"]


def test_hapus_material_yang_dipakai_ahsp_ditolak_dengan_sebabnya():
    """Foreign key ahsp_komponen -> sumber_daya menolak penghapusan ini.

    Tanpa pemeriksaan di aplikasi, penolakan itu jatuh ke penangan SQLAlchemyError dan
    pengguna cuma melihat "Gagal menyimpan ke database" -- benar bahwa datanya aman, tapi
    tidak menyebut barang mana, dipakai di mana, atau apa yang harus dilakukan.
    """
    cat = _sumber_daya("Cat Epoxy", "BAHAN", 100_000.0)
    a = _ahsp("Pengecatan lambung", "m2")
    svc.ganti_komponen(a, [KomponenInput(sumber_daya_id=cat, kelompok="BAHAN")], aktor="tes")

    with pytest.raises(ValueError) as e:
        material_svc.bulk_patch(BulkPatchMaterialRequest(delete_ids=[cat]), aktor="tes")

    pesan = str(e.value)
    assert "Cat Epoxy" in pesan and "Pengecatan lambung" in pesan, (
        f"pesannya harus menyebut barang dan analisanya, dapat: {pesan}"
    )

    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM sumber_daya WHERE id = :i"), {"i": cat}).scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM ahsp_komponen")).scalar() == 1


def test_material_yang_tidak_dipakai_tetap_bisa_dihapus():
    """Penjaga di atas tidak boleh ikut memblokir penghapusan biasa."""
    cat = _sumber_daya("Cat Epoxy", "BAHAN", 100_000.0)
    nganggur = _sumber_daya("Kuas", "BAHAN", 25_000.0, satuan="Bh")
    a = _ahsp("Pengecatan lambung", "m2")
    svc.ganti_komponen(a, [KomponenInput(sumber_daya_id=cat, kelompok="BAHAN")], aktor="tes")

    hasil = material_svc.bulk_patch(BulkPatchMaterialRequest(delete_ids=[nganggur]), aktor="tes")
    assert hasil["deleted"] == 1


def test_penerimaan_dr05_delapan_juta_lima_ratus_ribu():
    """Uji penerimaan dari file Excel asli: DR.05 Docking undocking, per Kali.

    3.250.000 upah + 2.900.000 alat + 2.350.000 bahan = 8.500.000 persis. DR.05 dipilih
    karena satu-satunya blok yang subtotal tiap kelompoknya benar-benar sama dengan
    jumlah barisnya (bagian 1B.3 rencana).
    """
    upah = _sumber_daya("Tenaga kerja docking", "UPAH", 3_250_000.0, satuan="Ls")
    alat = _sumber_daya("Peralatan docking", "ALAT", 2_900_000.0, satuan="Ls")
    bahan = _sumber_daya("Bahan docking", "BAHAN", 2_350_000.0, satuan="Ls")

    a = _ahsp("Docking undocking", "Kali")
    svc.ganti_komponen(
        a,
        [
            KomponenInput(sumber_daya_id=upah, kelompok="UPAH", urutan=1),
            KomponenInput(sumber_daya_id=alat, kelompok="ALAT", urutan=2),
            KomponenInput(sumber_daya_id=bahan, kelompok="BAHAN", urutan=3),
        ],
        aktor="tes",
    )

    h = svc.hitung(a)
    assert h["harga_jual"] == Decimal("8500000")
