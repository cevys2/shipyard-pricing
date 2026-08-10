"""Pencarian toleran: urutan kata bebas, salah ketik dimaafkan, hasil diperingkat.

Yang dijaga di sini adalah janji utamanya: kotak cari tidak boleh mengembalikan nol baris
untuk barang yang jelas-jelas ada di tabel hanya karena kata kuncinya ditulis dengan urutan
atau ejaan yang sedikit berbeda. Kegagalan seperti itu tidak kelihatan seperti bug -- orang
menyimpulkan datanya belum diinput, lalu menginput ulang barang yang sudah ada.
"""

import pytest
from sqlalchemy import text

from app.database import (
    engine,
    ensure_ahsp_tables,
    ensure_kategori_table,
    ensure_material_tables,
    ensure_pencarian_index,
)
from app.schemas.material import BulkMaterialCreate, MaterialItemCreate
from app.services import material as svc
from app.services import pencarian


@pytest.fixture(autouse=True)
def tabel_material_bersih():
    ensure_material_tables()
    # Urutan yang sama dengan lifespan: ahsp.kategori_id menunjuk ke kategori(id).
    ensure_kategori_table()
    ensure_ahsp_tables()
    # Menyalakan pg_trgm juga di DB tes -- kalau ekstensinya tidak ada, cabang fuzzy mati
    # sendiri dan tes yang membutuhkannya di-skip, bukan gagal.
    ensure_pencarian_index()
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE ahsp, ahsp_komponen, sumber_daya, sumber_daya_harga, supplier "
                "RESTART IDENTITY CASCADE"
            )
        )
    yield


def _simpan(nama: str, spesifikasi: str = "", satuan: str = "Kg") -> None:
    svc.bulk_create(
        BulkMaterialCreate(
            items=[
                MaterialItemCreate(
                    nama=nama,
                    spesifikasi=spesifikasi,
                    satuan=satuan,
                    harga_satuan=100_000.0,
                    tahun_pembelian=2026,
                )
            ]
        ),
        aktor="tes",
        jenis="BAHAN",
    )


def _cari(q: str) -> list[str]:
    return [r.nama for r in svc.list_material(search=q)]


# --- pecah(): murni, tanpa DB -------------------------------------------------------


@pytest.mark.parametrize(
    "kunci, harapan",
    [
        ("plat 10mm baja", ["plat", "10mm", "baja"]),
        ("M10x50", ["m10x50"]),
        # Desimal tidak boleh pecah jadi "1" dan "5": token "1" cocok dengan hampir semua
        # baris, dan filter AND-nya jadi tidak menyaring apa pun.
        ("1.5 mm", ["1.5", "mm"]),
        ("PLAT   plat  Plat", ["plat"]),
        ("", []),
        ("   ", []),
    ],
)
def test_pecah_kata_kunci(kunci, harapan):
    assert pencarian.pecah(kunci) == harapan


def test_kata_kunci_kosong_tidak_menyaring():
    assert pencarian.bangun("", ("nama",)) is None
    assert pencarian.bangun(None, ("nama",)) is None


def test_jumlah_kata_dibatasi():
    """Menempel satu paragraf ke kotak cari tidak boleh bikin query raksasa."""
    assert len(pencarian.pecah(" ".join(f"kata{i}" for i in range(50)))) == 8


# --- perilaku pencarian di DB -------------------------------------------------------


def test_urutan_kata_bebas():
    """Regresi utama: dulu ILIKE '%...%' satu potong, jadi ini mengembalikan nol baris."""
    _simpan("Plat Baja", spesifikasi="10 mm A36")

    assert _cari("plat baja") == ["Plat Baja"]
    assert _cari("baja plat") == ["Plat Baja"]
    assert _cari("plat 10mm baja") == ["Plat Baja"]
    assert _cari("a36 plat") == ["Plat Baja"]


def test_semua_kata_harus_cocok():
    """Longgar bukan berarti asal lolos -- kata yang tidak ada tetap menggugurkan baris."""
    _simpan("Plat Baja", spesifikasi="10 mm")

    assert _cari("plat kuningan") == []


def test_kata_dicari_lintas_kolom():
    """Satu kata dari `nama`, satu dari `spesifikasi`, tetap harus ketemu."""
    _simpan("Plat Baja", spesifikasi="A36 tebal 10 mm")

    assert _cari("plat a36") == ["Plat Baja"]


def test_part_number_beda_pemisah_tetap_ketemu():
    """"SKF 6205" dan "SKF-6205" itu barang yang sama, ditulis beda antar dokumen."""
    _simpan("Bearing", spesifikasi="SKF 6205 2RS")

    assert _cari("skf-6205") == ["Bearing"]
    assert _cari("skf6205") == ["Bearing"]


def test_persen_dan_underscore_dianggap_huruf_biasa():
    """`%` yang diketik orang tidak boleh jadi wildcard yang mencocokkan segalanya."""
    _simpan("Cat Epoxy")
    _simpan("Kuas Roll")

    # Dulu "%%" jadi pola LIKE '%%%' -> semua baris. Sekarang `%` bukan kata, jadi yang
    # tersisa cuma "cat".
    assert _cari("%cat%") == ["Cat Epoxy"]


def test_hasil_paling_relevan_di_atas():
    """Tanpa peringkat, yang cocok persis tenggelam di urutan alfabetis."""
    _simpan("Anoda Zinc", spesifikasi="cat pelindung")
    _simpan("Cat Epoxy", spesifikasi="primer")
    _simpan("Zeta Cat Thinner", spesifikasi="pengencer cat")

    hasil = _cari("cat epoxy")
    # "Cat Epoxy" punya kedua kata DAN sebagai frasa utuh, jadi harus paling atas --
    # padahal secara alfabetis "Anoda Zinc" duluan.
    assert hasil[0] == "Cat Epoxy"


def test_tanpa_kata_kunci_urutannya_tetap_alfabetis():
    """Peringkat relevansi hanya berlaku saat ada yang dicari; sisanya tidak boleh berubah."""
    _simpan("Zinc Anode")
    _simpan("Cat Epoxy")
    _simpan("Majun")

    assert _cari("") == ["Cat Epoxy", "Majun", "Zinc Anode"]


def test_salah_ketik_dimaafkan():
    if not pencarian.trgm_siap():
        pytest.skip("pg_trgm tidak terpasang di DB tes")
    _simpan("Gasket Karet", spesifikasi="tebal 3 mm")

    assert _cari("gaskit") == ["Gasket Karet"]
    assert _cari("gasket karett") == ["Gasket Karet"]


def test_kata_pendek_tidak_ikut_fuzzy():
    """Kata 3 huruf punya terlalu sedikit trigram -- kalau ikut fuzzy, hasilnya ngawur."""
    if not pencarian.trgm_siap():
        pytest.skip("pg_trgm tidak terpasang di DB tes")
    _simpan("Aki Kering", spesifikasi="12V")
    _simpan("Kaki Meja", spesifikasi="besi")

    # "aki" cocok persis di dua-duanya (substring), tapi tidak boleh melebar lebih jauh.
    assert sorted(_cari("aki")) == ["Aki Kering", "Kaki Meja"]
    assert _cari("aku") == []


def test_stats_ikut_kata_kunci_yang_sama():
    """KPI di atas tabel harus menghitung baris yang sama dengan yang tampil di tabel."""
    _simpan("Plat Baja", spesifikasi="10 mm")
    _simpan("Cat Epoxy")

    hasil = _cari("baja plat")
    stats = svc.material_stats(search="baja plat")

    assert len(hasil) == stats.total_material == 1
