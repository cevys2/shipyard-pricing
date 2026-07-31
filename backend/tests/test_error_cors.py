"""Perbaikan 4 -- error database harus tetap membawa header CORS.

Kalau tidak, browser memblokir responsnya dan pengguna cuma melihat "Failed to fetch",
sementara sebab aslinya (misalnya duplicate key) tidak pernah sampai ke layar.
"""

import time

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.config import settings
from app.database import engine
from app.main import app

ORIGIN = "http://localhost:5173"


@pytest.fixture
def client():
    # raise_server_exceptions=False supaya TestClient mengembalikan respons apa adanya,
    # bukan melempar ulang eksepsinya -- yang diuji di sini justru bentuk responsnya.
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def token():
    return jwt.encode(
        {"sub": "tes@contoh.com", "role": "admin", "exp": int(time.time()) + 600},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def _payload(uraian: str = "tes"):
    return {
        "nama_perusahaan": "PT TES",
        "nama_kapal": "KMP. RHAMA GIRI NUSA",
        "tahun": "2025",
        "tipe_perjanjian": "Induk",
        "items": [
            {
                "kategori_pekerjaan": "DOCKING",
                "uraian_pekerjaan": uraian,
                "volume_satuan": "Ls",
                "harga_satuan": 1000,
            }
        ],
    }


@pytest.fixture
def paksa_integrity_error(monkeypatch):
    """Paksa IntegrityError dari dalam service.

    Tabrakan primary key yang dulu terjadi di produksi sekarang MUSTAHIL direproduksi
    lewat jalur normal -- Perbaikan 1 membuat penomoran melanjutkan dari baris yang sudah
    ada, jadi menaruh baris penghalang justru cuma menggeser nomornya. Yang diuji di sini
    memang bukan tabrakannya (itu urusan Perbaikan 1 dan 3), melainkan bentuk respons
    ketika error database apa pun terjadi.
    """
    from app.routers import catalog as router_catalog

    def meledak(*args, **kwargs):
        raise IntegrityError("INSERT ...", {}, Exception("duplicate key value"))

    monkeypatch.setattr(router_catalog.catalog_service, "bulk_create", meledak)


def test_integrity_error_jadi_409_berheader_cors(client, token, paksa_integrity_error):
    r = client.post(
        "/catalog/bulk",
        json=_payload(),
        headers={"Authorization": f"Bearer {token}", "Origin": ORIGIN},
    )

    assert r.status_code == 409, f"harusnya 409, dapat {r.status_code}"
    assert r.headers.get("access-control-allow-origin") == ORIGIN, (
        "respons error tidak membawa header CORS -- browser akan memblokirnya dan "
        "pengguna cuma melihat 'Failed to fetch'"
    )
    assert "sudah tersimpan" in r.json()["detail"]


def test_respons_sukses_juga_berheader_cors(client, token):
    r = client.post(
        "/catalog/bulk",
        json=_payload("baris sah"),
        headers={"Authorization": f"Bearer {token}", "Origin": ORIGIN},
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == ORIGIN


def test_pesan_error_tidak_membocorkan_isi_eksepsi(client, token, paksa_integrity_error):
    r = client.post(
        "/catalog/bulk",
        json=_payload(),
        headers={"Authorization": f"Bearer {token}", "Origin": ORIGIN},
    )
    detail = r.json()["detail"].lower()
    for bocor in ("psycopg", "pg8000", "sqlalchemy", "traceback", "constraint", "pkey", "insert"):
        assert bocor not in detail, f"pesan ke pengguna membocorkan '{bocor}'"


def test_error_db_lain_jadi_500_berheader_cors(client, token, monkeypatch):
    """SQLAlchemyError selain IntegrityError tetap 500, tapi tetap terbaca browser."""
    from app.routers import catalog as router_catalog

    def meledak(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("koneksi putus"))

    monkeypatch.setattr(router_catalog.catalog_service, "bulk_create", meledak)

    r = client.post(
        "/catalog/bulk",
        json=_payload(),
        headers={"Authorization": f"Bearer {token}", "Origin": ORIGIN},
    )
    assert r.status_code == 500
    assert r.headers.get("access-control-allow-origin") == ORIGIN
    assert "Gagal menyimpan" in r.json()["detail"]


def test_impor_docking_yang_gagal_tidak_menyisakan_baris(client, token, monkeypatch):
    """Gabungan Perbaikan 3 + 4: error di Addendum, Induk ikut batal, responsnya terbaca."""
    from app.routers import catalog as router_catalog

    asli = router_catalog.catalog_service.bulk_create
    panggilan = {"n": 0}

    def kadang_meledak(*args, **kwargs):
        panggilan["n"] += 1
        if panggilan["n"] == 2:  # panggilan kedua = Addendum
            raise IntegrityError("INSERT ...", {}, Exception("duplicate key value"))
        return asli(*args, **kwargs)

    monkeypatch.setattr(router_catalog.catalog_service, "bulk_create", kadang_meledak)

    item = {
        "kategori_pekerjaan": "DOCKING",
        "uraian_pekerjaan": "induk-x",
        "volume_satuan": "Ls",
        "harga_satuan": 1000,
    }
    r = client.post(
        "/catalog/import/docking-commit",
        json={
            "nama_perusahaan": "PT TES",
            "nama_kapal": "KMP. RHAMA GIRI NUSA",
            "tahun": "2025",
            "induk_items": [item] * 5,
            "addendum_items": [item],
        },
        headers={"Authorization": f"Bearer {token}", "Origin": ORIGIN},
    )

    assert r.status_code == 409
    assert r.headers.get("access-control-allow-origin") == ORIGIN
    with engine.connect() as c:
        sisa = c.execute(text("SELECT COUNT(*) FROM tabel_katalog_harga")).scalar()
    assert sisa == 0, "Induk tersimpan padahal Addendum gagal -- separuh data masuk"
