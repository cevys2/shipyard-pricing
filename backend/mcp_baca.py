"""Server MCP read-only: Claude bisa mencari katalog harga & material langsung dari database.

Jalankan dari folder backend (butuh .env yang sama dengan app):  python mcp_baca.py
Didaftarkan ke Claude lewat .mcp.json di root repo.

Tidak ada satu pun jalur tulis di sini. Pencarian memakai fungsi yang sama dengan layar app
(services.catalog / services.material), jadi hasilnya sama dengan yang terlihat di dashboard.
"""

import os
import re
from pathlib import Path

os.chdir(Path(__file__).parent)  # .env dibaca relatif ke folder backend

from mcp.server.mcpserver import MCPServer  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.database import engine  # noqa: E402
from app.services import catalog, material  # noqa: E402

mcp = MCPServer(
    "shipyard-pricing",
    instructions=(
        "Database harga PT Dukuh Raya (galangan kapal). Read-only. "
        "Pakai cari_katalog untuk harga jasa/pekerjaan docking, cari_material untuk harga "
        "material. query() untuk yang tidak tercakup; panggil skema() dulu."
    ),
)

_MAKS_BARIS = 200


@mcp.tool()
def cari_katalog(kata: str, kapal: str | None = None, tahun: str | None = None, limit: int = 30) -> list[dict]:
    """Cari harga jasa/pekerjaan di katalog harga docking (sama dengan kotak cari di app).

    Urutan kata bebas, "plat 10mm" cocok dengan "Plat 10 mm". kapal/tahun harus persis.
    """
    rows = catalog.list_catalog(search=kata, kapal=kapal, tahun=tahun)
    return [r.model_dump(mode="json") for r in rows[: min(limit, _MAKS_BARIS)]]


@mcp.tool()
def cari_material(kata: str, limit: int = 30) -> list[dict]:
    """Cari material beserta harga terkininya (sama dengan tab Katalog Material)."""
    rows = material.list_material(search=kata)
    return [r.model_dump(mode="json") for r in rows[: min(limit, _MAKS_BARIS)]]


@mcp.tool()
def skema() -> dict[str, list[str]]:
    """Daftar tabel/view di schema public beserta kolomnya."""
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT table_name, column_name || ' ' || data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' ORDER BY table_name, ordinal_position"
        )).all()
    out: dict[str, list[str]] = {}
    for t, c in rows:
        out.setdefault(t, []).append(c)
    return out


@mcp.tool()
def query(sql: str) -> list[dict]:
    """Jalankan SATU perintah SELECT/WITH, read-only, maks 200 baris, batas waktu 15 detik."""
    sql = sql.strip().rstrip(";")
    if not re.match(r"(select|with)\b", sql, re.I):
        raise ValueError("Hanya SELECT / WITH.")
    # Tanpa parameter, pg8000 mengirim lewat simple protocol yang menerima banyak perintah
    # sekaligus -- "select 1; commit; delete ..." akan keluar dari transaksi READ ONLY.
    # Titik koma di dalam string literal ikut tertolak; harga yang wajar untuk pagar ini.
    if ";" in sql:
        raise ValueError("Satu perintah saja, tanpa ';'.")
    with engine.connect() as conn:
        # Transaksi READ ONLY + snapshot sudah diambil (SELECT 1) -> Postgres menolak
        # SET TRANSACTION READ WRITE dan semua INSERT/UPDATE/DELETE/DDL.
        # ponytail: role DB yang read-only adalah pagar yang sebenarnya; ini pagar app.
        conn.execute(text("SET TRANSACTION READ ONLY"))
        conn.execute(text("SET LOCAL statement_timeout = '15s'"))
        conn.execute(text("SELECT 1"))
        # `%` digandakan: pg8000 berparamstyle "format" (lihat _OP_MIRIP di pencarian.py).
        res = conn.execute(text(sql.replace("%", "%%")))
        rows = [dict(r) for r in res.mappings().fetchmany(_MAKS_BARIS)]
        conn.rollback()
    return [{k: (v if isinstance(v, (int, float, str, bool, type(None))) else str(v)) for k, v in r.items()} for r in rows]


if __name__ == "__main__":
    mcp.run()
