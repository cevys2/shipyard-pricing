"""Satuan baku untuk layar Harga Wajar: normalisasi, seed, dan resolver.

Sama seperti kategori, yang paling dijaga adalah kegagalan yang tidak bersuara. Kalau
bentuk alias di seed beda satu karakter dari hasil `satuan_norm_sql()`, ejaannya tidak
pernah cocok, `m2` dan `m²` tetap dua kelompok, dan layar harga menampilkan dua angka
yang masing-masing separuh tanpa ada yang merah.
"""

import pytest
from sqlalchemy import text

from app.config import settings
from app.database import engine, ensure_satuan_table, satuan_baku_sql, satuan_norm_sql
from app.seed_satuan import BORONGAN, PETA, baris_alias


@pytest.fixture(scope="module", autouse=True)
def satuan_siap():
    ensure_satuan_table()


def _baca(nilai: str | None) -> tuple[str | None, str | None]:
    """(satuan baku, ejaan yang dirapikan) untuk satu teks `volume_satuan`."""
    with engine.connect() as c:
        row = c.execute(
            text(f"SELECT {satuan_baku_sql(':v')} AS baku, {satuan_norm_sql(':v')} AS norm"),
            {"v": nilai},
        ).one()
    return row.baku, row.norm


def test_alias_di_seed_sudah_berbentuk_hasil_normalisasi():
    """Alias yang ditulis 'M2' atau 'bh.' di seed tidak akan pernah cocok dengan apa pun."""
    salah = []
    for b in baris_alias():
        _, norm = _baca(b["alias"])
        if norm != b["alias"]:
            salah.append((b["alias"], norm))
    assert not salah, f"alias berikut harus ditulis dalam bentuk hasil normalisasi: {salah}"


def test_nama_baku_ikut_di_daftar_ejaannya_sendiri():
    """Kalau tidak, baris yang ejaannya persis nama baku malah dianggap belum dipetakan."""
    for nama, daftar in PETA.items():
        _, norm = _baca(nama)
        assert norm in daftar, f"{nama!r} (dirapikan: {norm!r}) tidak ada di ejaannya sendiri"


def test_alias_tidak_dipakai_dua_satuan():
    """UNIQUE di tabel menolaknya juga, tapi di seed diam-diam yang terakhir menang."""
    semua = [b["alias"] for b in baris_alias()]
    assert len(semua) == len(set(semua))


@pytest.mark.parametrize(
    "tertulis, baku",
    [
        ("m2", "m²"),
        ("M2", "m²"),
        (" m² ", "m²"),
        ("m2 ", "m²"),  # spasi tak-putus dari sel Excel
        ("mtr", "m"),
        ("MTR", "m"),
        ("Mter", "m"),
        ("bh.", "pcs"),
        ("Buah", "pcs"),
        ("PC", "pcs"),
        ("Ltr.", "liter"),
        ("Ltr. ", "liter"),  # titik lalu spasi, lazim di sel Excel
        ("bh. ", "pcs"),
        ("M2. ", "m²"),
        ("Tanki", "tangki"),
        ("Shackle", "segel"),
        ("LS", "Ls"),
        ("Lump  Sum", "Ls"),
        ("Hari", "Hari"),
    ],
)
def test_ejaan_yang_dikenal_jatuh_ke_satuan_baku(tertulis, baku):
    assert _baca(tertulis)[0] == baku


def test_m_aksen_sengaja_tidak_digabung():
    """`m'` bisa meter lari, bisa m². Belum dipastikan -> tetap kelompok sendiri."""
    baku, norm = _baca("m'")
    assert baku is None
    assert norm == "m'"


def test_ejaan_belum_dipetakan_tetap_punya_nama():
    """Satuan yang belum ada di seed tidak boleh lenyap -- dia tampil dengan ejaannya."""
    assert _baca("Set") == (None, "set")


@pytest.mark.parametrize("kosong", ["-", "", "   ", " - ", None])
def test_tanpa_satuan_jadi_null(kosong):
    """'-' adalah cara `volume_satuan` bilang "tidak tahu", bukan satuan bernama '-'."""
    assert _baca(kosong) == (None, None)


def test_borongan_ditandai():
    # Dipatok ke keputusannya sendiri (22 Oktober 2026), bukan cuma ke konstanta seed --
    # membandingkan database ke konstanta yang sama yang mengisinya lulus untuk isi apa pun.
    assert BORONGAN == {"Ls", "Lot", "Paket"}
    with engine.connect() as c:
        rows = dict(c.execute(text("SELECT nama, borongan FROM satuan")).all())
    assert {n for n, b in rows.items() if b} == set(BORONGAN)


def test_mengubah_tanda_borongan_di_seed_benar_benar_sampai():
    with engine.begin() as c:
        c.execute(text("UPDATE satuan SET borongan = FALSE WHERE nama = 'Ls'"))
    ensure_satuan_table()
    with engine.connect() as c:
        assert c.execute(text("SELECT borongan FROM satuan WHERE nama = 'Ls'")).scalar() is True


def test_memindahkan_ejaan_di_seed_benar_benar_sampai():
    """DO NOTHING akan membiarkan pemetaan lama selamanya di database yang sudah terisi."""
    with engine.begin() as c:
        c.execute(
            text(
                "UPDATE satuan_alias SET satuan_id = (SELECT id FROM satuan WHERE nama = 'Kali') "
                "WHERE alias = 'm2'"
            )
        )
    assert _baca("m2")[0] == "Kali"

    ensure_satuan_table()
    assert _baca("m2")[0] == "m²"


def _jumlah() -> tuple[int, int]:
    with engine.connect() as c:
        return (
            c.execute(text("SELECT COUNT(*) FROM satuan")).scalar(),
            c.execute(text("SELECT COUNT(*) FROM satuan_alias")).scalar(),
        )


def test_dipanggil_ulang_tidak_menggandakan_apa_pun():
    # Dibandingkan dengan jumlah sebelumnya, bukan dengan panjang seed: ejaan yang pernah
    # ditambahkan lewat SQL (atau dihapus dari seed) memang sengaja tidak ikut terhapus.
    sebelum = _jumlah()
    ensure_satuan_table()
    ensure_satuan_table()
    assert _jumlah() == sebelum
    with engine.connect() as c:
        tersimpan = set(c.execute(text("SELECT alias FROM satuan_alias")).scalars())
    assert {b["alias"] for b in baris_alias()} <= tersimpan


def test_tabel_katalog_tidak_disentuh():
    """Satuan dicocokkan saat membaca. Tidak boleh ada kolom baru di tabel katalog."""
    sql = text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = :t ORDER BY 1"
    )
    with engine.connect() as c:
        sebelum = c.execute(sql, {"t": settings.catalog_table}).scalars().all()
    ensure_satuan_table()
    with engine.connect() as c:
        sesudah = c.execute(sql, {"t": settings.catalog_table}).scalars().all()
    assert sebelum == sesudah
    assert "satuan_id" not in sesudah
