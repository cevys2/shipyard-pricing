"""Sesi 3.0 -- UPAH/ALAT/KONSUMABEL lewat jalur yang sama dengan BAHAN.

Yang dijaga di sini bukan fitur barunya, tapi batas antar-jenis: tab Katalog Material
yang sekarang tidak boleh berubah isinya sedikit pun gara-gara ada baris upah.
"""

import pytest
from sqlalchemy import text

from app.database import engine, ensure_ahsp_tables, ensure_kategori_table, ensure_material_tables
from app.schemas.material import BulkMaterialCreate, MaterialItemCreate
from app.services import material as svc


@pytest.fixture(autouse=True)
def tabel_material_bersih():
    """DB tes cuma punya tabel_katalog_harga + audit_log, jadi tabel material dibikin dulu.

    Tabel AHSP ikut dibikin karena `bulk_patch` sekarang memeriksa `ahsp_komponen` sebelum
    menghapus -- sama seperti urutan di lifespan aplikasi sungguhan.
    """
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


def _item(nama: str, satuan: str = "Kg", harga: float = 100_000.0, **kw) -> MaterialItemCreate:
    return MaterialItemCreate(
        nama=nama, satuan=satuan, harga_satuan=harga, tahun_pembelian=2026, **kw
    )


def _simpan(nama: str, jenis: str, **kw) -> dict:
    return svc.bulk_create(
        BulkMaterialCreate(items=[_item(nama, **kw)]), aktor="tes", jenis=jenis
    )


def test_default_tetap_bahan_dan_upah_tidak_ikut_muncul():
    """Regresi terpenting sesi ini: tab Bahan tidak boleh kemasukan baris upah."""
    _simpan("Cat Epoxy", "BAHAN")
    _simpan("Tukang Cat", "UPAH", satuan="OH", harga=150_000.0)

    bahan = svc.list_material()
    upah = svc.list_material(jenis="UPAH")

    assert [r.nama for r in bahan] == ["Cat Epoxy"]
    assert [r.nama for r in upah] == ["Tukang Cat"]


def test_baris_upah_benar_benar_tersimpan_sebagai_upah():
    """Menjaga INSERT di _resolve_sumber_daya().

    Kalau kolom `jenis` tidak disebut di INSERT, baris ini jatuh ke DEFAULT 'BAHAN' dan
    tetap lolos semua tes lain yang cuma memanggil list_material(jenis="UPAH")... sampai
    seseorang membuka tab Bahan dan menemukannya di sana.
    """
    _simpan("Tukang Las", "UPAH", satuan="OH", harga=175_000.0)
    with engine.connect() as conn:
        jenis = conn.execute(
            text("SELECT jenis FROM sumber_daya WHERE nama = 'Tukang Las'")
        ).scalar()
    assert jenis == "UPAH"


def test_paste_upah_yang_sama_dua_kali_dilewati_bukan_error():
    """Ini yang menguji _peta_identitas() ikut disaring per jenis.

    Sebelum diperbaiki, kemunculan kedua dianggap barang baru lalu ditabrak
    uq_sd_identitas sebagai IntegrityError -- pengguna cuma melihat pesan menyesatkan.
    """
    pertama = _simpan("Tukang Cat", "UPAH", satuan="OH", harga=150_000.0)
    kedua = _simpan("Tukang Cat", "UPAH", satuan="OH", harga=150_000.0)

    assert pertama["saved"] == 1
    assert kedua["saved"] == 0 and kedua["dilewati"] == 1

    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT COUNT(*) FROM sumber_daya WHERE jenis = 'UPAH'")
        ).scalar()
    assert n == 1, "master upah kembar -- riwayat harganya bakal terbelah dua"


def test_pratinjau_menandai_kemunculan_kedua_sebagai_dilewati():
    _simpan("Tukang Cat", "UPAH", satuan="OH", harga=150_000.0)
    hasil = svc.preview_bulk(
        BulkMaterialCreate(items=[_item("Tukang Cat", satuan="OH", harga=150_000.0)]),
        jenis="UPAH",
    )
    assert hasil["baris"][0]["status"] == "dilewati"
    assert hasil["ringkas"]["material_baru"] == 0


def test_pratinjau_jenis_lain_tidak_melihat_baris_upah():
    """Nama yang sama di jenis berbeda memang barang berbeda -- uq_sd_identitas juga begitu."""
    _simpan("Pengecatan", "UPAH", satuan="OH", harga=150_000.0)
    hasil = svc.preview_bulk(
        BulkMaterialCreate(items=[_item("Pengecatan", satuan="OH", harga=150_000.0)]),
        jenis="ALAT",
    )
    assert hasil["baris"][0]["status"] == "material_baru"


def test_riwayat_harga_jalan_untuk_upah_tanpa_kode_tambahan():
    _simpan("Tukang Cat", "UPAH", satuan="OH", harga=150_000.0)
    sd_id = svc.list_material(jenis="UPAH")[0].id
    riwayat = svc.price_history(sd_id)
    assert len(riwayat) == 1 and riwayat[0].harga_satuan == 150_000.0


def test_stats_dan_filter_ikut_jenis():
    _simpan("Cat Epoxy", "BAHAN")
    _simpan("Tukang Cat", "UPAH", satuan="OH", harga=150_000.0)

    assert svc.material_stats().total_material == 1
    assert svc.material_stats(jenis="UPAH").total_material == 1
    assert svc.filter_options(jenis="UPAH")["satuan"] == ["Semua", "OH"]


def test_jenis_ngawur_ditolak_bukan_mengembalikan_kosong():
    """Jenis salah eja yang diam-diam mengembalikan 0 baris terbaca seperti 'belum ada data'."""
    with pytest.raises(ValueError):
        svc.list_material(jenis="SUBKON")
