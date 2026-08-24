"""Setup tes: SELALU ke Postgres lokal, tidak pernah ke produksi.

`DATABASE_URL` di-set SEBELUM modul aplikasi diimpor, karena `app.database` membuat engine
saat modul dimuat. Kalau di-set belakangan, engine sudah terlanjur menunjuk ke Railway.
"""

import os

import pytest

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres@127.0.0.1:5432/shipyard_test"
)

# Palang pengaman: kalau URL tesnya entah bagaimana menunjuk ke host jauh, hentikan
# sebelum satu baris pun ditulis.
_RAGU = ("railway", "rlwy.net", "proxy.rlwy", "amazonaws", "supabase")
if any(t in TEST_DB_URL.lower() for t in _RAGU):
    raise RuntimeError(
        f"TEST_DATABASE_URL menunjuk ke host jauh ({TEST_DB_URL!r}). "
        "Tes ini hanya boleh jalan di Postgres lokal."
    )

os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ.setdefault("JWT_SECRET", "rahasia-tes-saja")

from sqlalchemy import text  # noqa: E402

from app.database import engine, ensure_katalog_kolom_rincian  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def kolom_rincian_siap():
    """Kolom nullable tambahan di `tabel_katalog_harga`, sekali per sesi tes.

    Sama persis dengan yang dilakukan `main.py` waktu app start. Tanpa ini, database tes
    lokal tertinggal dari kode -- setiap INSERT katalog akan gagal di kolom yang belum
    ada, dan errornya menuding tesnya, bukan setup DB-nya.
    """
    ensure_katalog_kolom_rincian()


@pytest.fixture(autouse=True)
def db_bersih():
    """Kosongkan tabel sebelum tiap tes supaya urutan tes tidak saling memengaruhi."""
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE tabel_katalog_harga"))
        conn.execute(text("TRUNCATE audit_log RESTART IDENTITY"))
    yield


@pytest.fixture
def conn():
    with engine.begin() as c:
        yield c
