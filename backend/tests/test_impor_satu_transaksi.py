"""Perbaikan 3 -- Induk dan Addendum harus hidup-mati bersama dalam satu transaksi."""

import pytest
from sqlalchemy import text

from app.database import engine
from app.schemas.catalog import BulkCatalogCreate, CatalogItemBase, TipePerjanjian
from app.services.catalog import bulk_create

KAPAL = "KMP. RHAMA GIRI NUSA"
TAHUN = "2025"


def _items(n: int, tag: str) -> list[CatalogItemBase]:
    return [
        CatalogItemBase(
            kategori_pekerjaan="DOCKING",
            uraian_pekerjaan=f"{tag}-{i}",
            volume_satuan="Ls",
            harga_satuan=1000 + i,
        )
        for i in range(n)
    ]


def _jumlah() -> int:
    with engine.connect() as c:
        return c.execute(text("SELECT COUNT(*) FROM tabel_katalog_harga")).scalar()


def _payload(tipe: TipePerjanjian, items):
    return BulkCatalogCreate(
        nama_perusahaan="PT TES",
        nama_kapal=KAPAL,
        tahun=TAHUN,
        tipe_perjanjian=tipe,
        items=items,
    )


def test_induk_dan_addendum_bernomor_lanjut_bukan_mengulang():
    """Inti Perbaikan 1 + 3 bersama: dalam satu transaksi, Addendum melanjutkan nomor Induk.

    Kalau penomoran tidak ikut transaksi, Addendum mengulang dari 001 dan langsung
    tabrakan primary key -- setiap kali, bukan sesekali.
    """
    with engine.begin() as conn:
        bulk_create(_payload(TipePerjanjian.induk, _items(50, "I")), aktor="tes", conn=conn)
        bulk_create(_payload(TipePerjanjian.addendum, _items(30, "A")), aktor="tes", conn=conn)

    with engine.connect() as c:
        rows = c.execute(
            text("SELECT id, tipe_perjanjian FROM tabel_katalog_harga ORDER BY id")
        ).all()
    assert len(rows) == 80
    nomor = sorted(int(r[0].split("-")[-1]) for r in rows)
    assert nomor == list(range(1, 81)), "nomor urut bolong atau mengulang"


def test_addendum_gagal_maka_induk_ikut_batal():
    """Setengah data masuk harus mustahil.

    Kegagalan dipicu dari dalam transaksi setelah Induk tersimpan; seluruhnya harus
    ter-rollback, termasuk baris auditnya.
    """
    assert _jumlah() == 0

    with pytest.raises(Exception):
        with engine.begin() as conn:
            bulk_create(_payload(TipePerjanjian.induk, _items(50, "I")), aktor="tes", conn=conn)
            # ID yang dipaksa tabrakan: mensimulasikan kegagalan apa pun di tengah jalan.
            conn.execute(
                text(
                    "INSERT INTO tabel_katalog_harga (id, uraian_pekerjaan, harga_satuan) "
                    "VALUES ((SELECT id FROM tabel_katalog_harga LIMIT 1), 'tabrakan', 1)"
                )
            )

    assert _jumlah() == 0, "Induk tetap tersimpan padahal Addendum gagal -- separuh data masuk"

    with engine.connect() as c:
        audit = c.execute(text("SELECT COUNT(*) FROM audit_log")).scalar()
    assert audit == 0, "baris audit tertinggal padahal datanya batal"


def test_tanpa_conn_tetap_jalan_seperti_sebelumnya():
    """`/catalog/bulk` dan `/catalog/import` memanggil tanpa `conn` -- jangan sampai rusak."""
    n = bulk_create(_payload(TipePerjanjian.induk, _items(5, "X")), aktor="tes")
    assert n == 5
    assert _jumlah() == 5


def test_dua_panggilan_tanpa_conn_tetap_terpisah():
    """Perilaku lama dipertahankan: tanpa `conn`, masing-masing commit sendiri."""
    bulk_create(_payload(TipePerjanjian.induk, _items(3, "P")), aktor="tes")
    assert _jumlah() == 3
    bulk_create(_payload(TipePerjanjian.addendum, _items(2, "Q")), aktor="tes")
    assert _jumlah() == 5


def test_audit_dua_baris_satu_per_tipe():
    with engine.begin() as conn:
        bulk_create(_payload(TipePerjanjian.induk, _items(4, "I")), aktor="tes", conn=conn)
        bulk_create(_payload(TipePerjanjian.addendum, _items(4, "A")), aktor="tes", conn=conn)

    with engine.connect() as c:
        baris = c.execute(
            text("SELECT jumlah, detail->>'tipe_perjanjian' FROM audit_log ORDER BY id")
        ).all()
    assert len(baris) == 2
    assert [b[0] for b in baris] == [4, 4]
    assert [b[1] for b in baris] == ["Induk", "Addendum"]
