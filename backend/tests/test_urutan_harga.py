"""Tahun pembelian yang menentukan harga terkini, bukan hari orang sempat menginput.

`berlaku_dari` boleh dikosongkan di tempelan, dan kalau kosong dia jatuh ke `date.today()`.
Selama kolom itu yang mengurutkan, dua hal terjadi diam-diam: faktur yang sama ditempel di
hari berbeda jadi dua titik harga, dan pembelian lama yang baru diinput mengalahkan
pembelian yang lebih baru. Keduanya tidak pernah memunculkan error -- cuma angka yang salah,
dan angkanya ikut ke harga komponen AHSP yang hidup mengikuti `v_harga_terkini`.
"""

import datetime as dt
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.database import engine, ensure_material_tables
from app.schemas.material import BulkMaterialCreate
from app.services import material as svc


class _HariPalsu(dt.date):
    """Mengendalikan `date.today()` supaya "ditempel besoknya" bisa diuji."""

    HARI = dt.date(2026, 8, 10)

    @classmethod
    def today(cls):
        return cls.HARI


@pytest.fixture(autouse=True)
def material_bersih():
    ensure_material_tables()
    with engine.begin() as conn:
        conn.execute(
            text("TRUNCATE sumber_daya, sumber_daya_harga, supplier RESTART IDENTITY CASCADE")
        )
    _HariPalsu.HARI = dt.date(2026, 8, 10)
    yield


def _tempel(nama="Plat Baja", harga=21000, tahun=2024, spesifikasi="10 mm"):
    svc.bulk_create(
        BulkMaterialCreate(
            items=[
                {
                    "nama": nama,
                    "spesifikasi": spesifikasi,
                    "satuan": "kg",
                    "harga_satuan": harga,
                    "tahun_pembelian": tahun,
                }
            ]
        ),
        aktor="tes",
    )


def _titik_harga() -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM sumber_daya_harga")).scalar()


def _terkini() -> tuple:
    with engine.connect() as conn:
        r = conn.execute(
            text("SELECT harga_satuan, tahun_pembelian FROM v_harga_terkini")
        ).first()
    return (float(r[0]), r[1])


def test_faktur_sama_ditempel_besoknya_bukan_titik_harga_baru():
    with patch.object(svc, "date", _HariPalsu):
        _tempel()
        assert _titik_harga() == 1

        _HariPalsu.HARI = dt.date(2026, 8, 11)
        _tempel()

    assert _titik_harga() == 1, (
        "faktur yang sama ditempel besoknya tercatat sebagai perubahan harga, "
        "padahal harganya tidak bergerak"
    )


def test_pembelian_lama_yang_baru_diinput_tidak_mengalahkan_yang_lebih_baru():
    """Urutan input sengaja dibalik dari urutan pembelian."""
    with patch.object(svc, "date", _HariPalsu):
        _HariPalsu.HARI = dt.date(2026, 8, 10)
        _tempel(harga=25000, tahun=2025)

        # Faktur 2017 ditemukan belakangan dan baru diinput hari ini.
        _HariPalsu.HARI = dt.date(2026, 8, 11)
        _tempel(harga=9000, tahun=2017)

    assert _titik_harga() == 2
    assert _terkini() == (25000.0, 2025), "harga 2017 yang diinput belakangan jadi harga terkini"


def test_pembelian_yang_lebih_baru_tetap_menang_walau_diinput_lebih_dulu():
    """Kebalikannya juga harus benar, kalau tidak yang terjadi cuma urutannya kebalik."""
    with patch.object(svc, "date", _HariPalsu):
        _tempel(harga=9000, tahun=2017)
        _HariPalsu.HARI = dt.date(2026, 8, 11)
        _tempel(harga=25000, tahun=2026)

    assert _titik_harga() == 2
    assert _terkini() == (25000.0, 2026)


def test_harga_berbeda_di_tahun_sama_tetap_dua_titik():
    """Yang dibuang cuma duplikat, bukan perubahan harga yang sungguhan."""
    with patch.object(svc, "date", _HariPalsu):
        _tempel(harga=21000, tahun=2024)
        _tempel(harga=23000, tahun=2024)

    assert _titik_harga() == 2
    assert _terkini() == (23000.0, 2024)


def test_riwayat_harga_urut_dari_pembelian_terlama():
    with patch.object(svc, "date", _HariPalsu):
        _tempel(harga=25000, tahun=2026)
        _tempel(harga=9000, tahun=2017)
        _tempel(harga=15000, tahun=2021)

    with engine.connect() as conn:
        sd_id = conn.execute(text("SELECT id FROM sumber_daya LIMIT 1")).scalar()
    tahun = [r.tahun_pembelian for r in svc.price_history(sd_id)]
    assert tahun == [2017, 2021, 2026]
