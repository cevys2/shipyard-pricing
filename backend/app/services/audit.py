import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.database import engine


def catat(
    conn: Connection,
    *,
    aktor: str,
    aksi: str,
    entitas: str,
    jumlah: int = 1,
    detail: dict[str, Any] | None = None,
) -> None:
    """Tulis satu baris audit di dalam transaksi pemanggil.

    Sengaja menerima `conn` (bukan bikin koneksi sendiri) supaya jejaknya ikut
    rollback kalau operasi utamanya gagal -- audit yang mencatat perubahan yang
    ternyata batal lebih menyesatkan daripada tidak ada audit sama sekali.

    pg8000 tidak otomatis mengadaptasi dict ke JSONB, jadi di-serialize manual lalu
    di-CAST di SQL.
    """
    conn.execute(
        text(
            """
            INSERT INTO audit_log (aktor, aksi, entitas, jumlah, detail)
            VALUES (:aktor, :aksi, :entitas, :jumlah, CAST(:detail AS JSONB))
            """
        ),
        {
            "aktor": aktor,
            "aksi": aksi,
            "entitas": entitas,
            "jumlah": jumlah,
            "detail": json.dumps(detail, default=str) if detail else None,
        },
    )


def list_log(*, entitas: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    clause = "WHERE entitas = :entitas" if entitas and entitas != "Semua" else ""
    params: dict[str, Any] = {"limit": min(limit, 500)}
    if clause:
        params["entitas"] = entitas
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT id, aktor, aksi, entitas, jumlah, detail, dibuat_pada
                FROM   audit_log {clause}
                ORDER  BY dibuat_pada DESC, id DESC
                LIMIT  :limit
                """
            ),
            params,
        ).mappings().all()
    return [dict(r) for r in rows]
