"""Perbaikan 1 -- penomoran ID ikut transaksi pemanggil, terkunci per kapal+tahun."""

import threading

import pytest
from sqlalchemy import text

from app.database import engine
from app.schemas.catalog import BulkCatalogCreate, CatalogItemBase, TipePerjanjian
from app.services.catalog import _next_ids, bulk_create

PREFIX = "KMP._RHAMA_GIRI_NUSA-2025-"


def _sisipkan(conn, id_: str) -> None:
    conn.execute(
        text(
            "INSERT INTO tabel_katalog_harga (id, nama_kapal, tahun, uraian_pekerjaan, harga_satuan) "
            "VALUES (:id, 'KMP. RHAMA GIRI NUSA', '2025', 'tes', 1)"
        ),
        {"id": id_},
    )


def test_melanjutkan_nomor_dalam_transaksi_yang_sama(conn):
    """Baris yang belum commit HARUS ikut terhitung.

    Ini inti Perbaikan 1: kalau `_next_ids` membuka koneksinya sendiri, panggilan kedua
    tidak melihat baris pertama dan mengulang dari 001 -- persis penyebab duplicate key
    saat Induk dan Addendum disatukan dalam satu transaksi.
    """
    pertama = _next_ids(conn, PREFIX, 3)
    assert pertama == [f"{PREFIX}001", f"{PREFIX}002", f"{PREFIX}003"]

    for id_ in pertama:
        _sisipkan(conn, id_)

    kedua = _next_ids(conn, PREFIX, 2)
    assert kedua == [f"{PREFIX}004", f"{PREFIX}005"], (
        "penomoran mengulang dari awal -- baris yang belum commit tidak terlihat"
    )


def test_prefix_dicocokkan_harfiah_bukan_pola_like(conn):
    """`_` di LIKE berarti 'satu karakter apa saja'.

    Slug nama kapal penuh `_`, jadi dengan LIKE, ID milik kapal lain yang hurufnya beda
    di posisi `_` ikut terhitung dan nomor urut kapal ini melompat.
    """
    _sisipkan(conn, "KMP.XRHAMAXGIRIXNUSA-2025-900")

    ids = _next_ids(conn, PREFIX, 1)
    assert ids == [f"{PREFIX}001"], (
        f"baris umpan kapal lain ikut terhitung, dapat {ids[0]} bukan {PREFIX}001"
    )


def test_id_tidak_bocor_antar_tahun(conn):
    _sisipkan(conn, "KMP._RHAMA_GIRI_NUSA-2024-050")
    assert _next_ids(conn, PREFIX, 1) == [f"{PREFIX}001"]


def test_dua_impor_bersamaan_kapal_sama_tidak_menabrak():
    """Tanpa kunci penasihat, kedua thread membaca nomor terakhir yang sama lalu tabrakan.

    Dijalankan lewat `bulk_create` supaya yang diuji jalur nyata, bukan fungsi telanjang.
    """
    galat: list[Exception] = []
    mulai = threading.Barrier(2)

    def impor(tag: str):
        try:
            mulai.wait(timeout=10)
            bulk_create(
                BulkCatalogCreate(
                    nama_perusahaan="PT TES",
                    nama_kapal="KMP. RHAMA GIRI NUSA",
                    tahun="2025",
                    tipe_perjanjian=TipePerjanjian.induk,
                    items=[
                        CatalogItemBase(
                            kategori_pekerjaan="TES",
                            uraian_pekerjaan=f"{tag}-{i}",
                            volume_satuan="Ls",
                            harga_satuan=1000,
                        )
                        for i in range(20)
                    ],
                ),
                aktor="tes",
            )
        except Exception as e:  # noqa: BLE001 -- dikumpulkan untuk dilaporkan di assert
            galat.append(e)

    t1 = threading.Thread(target=impor, args=("A",))
    t2 = threading.Thread(target=impor, args=("B",))
    t1.start(), t2.start()
    t1.join(timeout=60), t2.join(timeout=60)

    assert not galat, f"impor bersamaan gagal: {galat!r}"

    with engine.connect() as c:
        total = c.execute(text("SELECT COUNT(*) FROM tabel_katalog_harga")).scalar()
        unik = c.execute(text("SELECT COUNT(DISTINCT id) FROM tabel_katalog_harga")).scalar()
    assert total == 40, f"harusnya 40 baris tersimpan, dapat {total}"
    assert unik == 40, "ada ID yang dobel"


def test_format_id_tidak_berubah(conn):
    """4.239 baris lama memakai format ini -- tiga digit ber-nol di depan."""
    ids = _next_ids(conn, PREFIX, 2)
    assert all(i.startswith(PREFIX) for i in ids)
    assert ids[0].split("-")[-1] == "001"
    assert len(ids[0].split("-")[-1]) == 3


def test_nomor_lanjut_dari_baris_yang_sudah_ada(conn):
    _sisipkan(conn, f"{PREFIX}050")
    assert _next_ids(conn, PREFIX, 1) == [f"{PREFIX}051"]


@pytest.mark.parametrize("rusak", ["KMP._RHAMA_GIRI_NUSA-2025-ABC", "KMP._RHAMA_GIRI_NUSA-2025-"])
def test_id_tak_berformat_diabaikan_bukan_bikin_gagal(conn, rusak):
    _sisipkan(conn, rusak)
    _sisipkan(conn, f"{PREFIX}007")
    assert _next_ids(conn, PREFIX, 1) == [f"{PREFIX}008"]
