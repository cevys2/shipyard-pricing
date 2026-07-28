from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.database import engine
from app.schemas.material import (
    BulkMaterialCreate,
    BulkPatchMaterialRequest,
    MaterialItemCreate,
    MaterialRowOut,
    MaterialStats,
)

_LIST_QUERY = """
    SELECT sd.id, sd.nama, sd.spesifikasi, sd.satuan,
           h.harga_satuan, h.mata_uang, h.nama_kapal, h.tahun_pembelian, h.berlaku_dari,
           sup.nama AS supplier_nama
    FROM   sumber_daya sd
    LEFT JOIN v_harga_terkini h ON h.sumber_daya_id = sd.id
    LEFT JOIN supplier sup ON sup.id = h.supplier_id
    WHERE  sd.jenis = 'BAHAN' AND sd.aktif
"""


def _build_where(
    *,
    supplier: str | None = None,
    satuan: str | None = None,
    kapal: str | None = None,
    tahun: str | None = None,
    search: str | None = None,
) -> tuple[str, dict[str, Any]]:
    clauses = []
    params: dict[str, Any] = {}
    if supplier and supplier != "Semua":
        clauses.append("sup.nama = :supplier")
        params["supplier"] = supplier
    if satuan and satuan != "Semua":
        clauses.append("sd.satuan = :satuan")
        params["satuan"] = satuan
    if kapal and kapal != "Semua":
        clauses.append("h.nama_kapal = :kapal")
        params["kapal"] = kapal
    if tahun and tahun != "Semua":
        clauses.append("h.tahun_pembelian = :tahun")
        params["tahun"] = int(tahun)
    if search:
        clauses.append("(sd.nama ILIKE :search OR sd.spesifikasi ILIKE :search)")
        params["search"] = f"%{search}%"
    where = (" AND " + " AND ".join(clauses)) if clauses else ""
    return where, params


def list_material(
    *,
    supplier: str | None = None,
    satuan: str | None = None,
    kapal: str | None = None,
    tahun: str | None = None,
    search: str | None = None,
) -> list[MaterialRowOut]:
    where, params = _build_where(supplier=supplier, satuan=satuan, kapal=kapal, tahun=tahun, search=search)
    query = text(f"{_LIST_QUERY} {where} ORDER BY sd.nama, sd.id")
    with engine.connect() as conn:
        rows = conn.execute(query, params).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("spesifikasi") is None:
            d["spesifikasi"] = ""
        out.append(MaterialRowOut(**d))
    return out


def material_stats(
    *,
    supplier: str | None = None,
    satuan: str | None = None,
    kapal: str | None = None,
    tahun: str | None = None,
    search: str | None = None,
) -> MaterialStats:
    where, params = _build_where(supplier=supplier, satuan=satuan, kapal=kapal, tahun=tahun, search=search)
    query = text(
        f"""
        SELECT COUNT(DISTINCT sd.id) AS total_material,
               COUNT(DISTINCT sup.id) AS total_supplier,
               COUNT(DISTINCT h.nama_kapal) AS total_kapal,
               MAX(h.berlaku_dari) AS update_terakhir
        FROM   sumber_daya sd
        LEFT JOIN v_harga_terkini h ON h.sumber_daya_id = sd.id
        LEFT JOIN supplier sup ON sup.id = h.supplier_id
        WHERE  sd.jenis = 'BAHAN' AND sd.aktif {where}
        """
    )
    with engine.connect() as conn:
        row = conn.execute(query, params).mappings().first()
    if not row:
        return MaterialStats(total_material=0, total_supplier=0, total_kapal=0, update_terakhir=None)
    return MaterialStats(**dict(row))


def filter_options(
    *,
    supplier: str | None = None,
    satuan: str | None = None,
    kapal: str | None = None,
    tahun: str | None = None,
    search: str | None = None,
) -> dict[str, list[str]]:
    active = {"supplier": supplier, "satuan": satuan, "kapal": kapal, "tahun": tahun}
    result: dict[str, list[str]] = {}
    with engine.connect() as conn:
        for key, col_expr in (
            ("supplier", "sup.nama"),
            ("satuan", "sd.satuan"),
            ("kapal", "h.nama_kapal"),
            ("tahun", "h.tahun_pembelian"),
        ):
            others = {k: v for k, v in active.items() if k != key}
            where, params = _build_where(**others, search=search)
            rows = conn.execute(
                text(
                    f"""
                    SELECT DISTINCT {col_expr}
                    FROM   sumber_daya sd
                    LEFT JOIN v_harga_terkini h ON h.sumber_daya_id = sd.id
                    LEFT JOIN supplier sup ON sup.id = h.supplier_id
                    WHERE  sd.jenis = 'BAHAN' AND sd.aktif {where}
                    ORDER  BY {col_expr}
                    """
                ),
                params,
            ).all()
            result[key] = ["Semua"] + [str(r[0]) for r in rows if r[0] is not None]
    return result


def _multi_values(columns: list[str], rows: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    """Bangun klausa VALUES (:c0_0, :c1_0), (:c0_1, :c1_1), ... buat insert banyak baris dalam
    SATU round-trip ke DB -- penting karena DB-nya remote (Railway), jadi tiap round-trip kena
    latency jaringan. Insert satu-satu (loop per baris) kerasa lambat pas paste banyak baris."""
    placeholders = []
    params: dict[str, Any] = {}
    for i, row in enumerate(rows):
        keys = [f"{col}{i}" for col in columns]
        placeholders.append("(" + ", ".join(f":{k}" for k in keys) + ")")
        for col, key in zip(columns, keys):
            params[key] = row[col]
    return ", ".join(placeholders), params


def _resolve_suppliers(conn: Connection, raw_names: list[str]) -> dict[str, int]:
    """Cari-atau-buat semua supplier yang dibutuhkan dalam SATU query (bukan satu query per baris).
    ON CONFLICT DO UPDATE (bukan DO NOTHING) dipakai supaya RETURNING tetap ngasih balik id
    supplier yang sudah ada juga, nggak cuma yang baru dibuat."""
    names = sorted({n.strip() for n in raw_names if n and n.strip()})
    if not names:
        return {}
    values_sql, params = _multi_values(["nama"], [{"nama": n} for n in names])
    rows = conn.execute(
        text(
            f"INSERT INTO supplier (nama) VALUES {values_sql} "
            "ON CONFLICT (nama) DO UPDATE SET nama = EXCLUDED.nama "
            "RETURNING id, nama"
        ),
        params,
    ).all()
    return {nama: id_ for id_, nama in rows}


def _insert_harga(conn: Connection, sumber_daya_id: int, item: MaterialItemCreate, supplier_id: int | None) -> None:
    conn.execute(
        text(
            """
            INSERT INTO sumber_daya_harga
            (sumber_daya_id, supplier_id, harga_satuan, mata_uang, nama_kapal, tahun_pembelian,
             berlaku_dari, sumber, no_dokumen, catatan)
            VALUES (:sd_id, :sup_id, :harga, :mata_uang, :kapal, :tahun, :tgl, :sumber, :no_dok, :catatan)
            """
        ),
        {
            "sd_id": sumber_daya_id,
            "sup_id": supplier_id,
            "harga": item.harga_satuan,
            "mata_uang": item.mata_uang,
            "kapal": item.nama_kapal or None,
            "tahun": item.tahun_pembelian,
            "tgl": item.berlaku_dari or date.today(),
            "sumber": item.sumber or None,
            "no_dok": item.no_dokumen or None,
            "catatan": item.catatan or None,
        },
    )


def bulk_create(payload: BulkMaterialCreate) -> int:
    with engine.begin() as conn:
        supplier_map = _resolve_suppliers(conn, [item.supplier_nama for item in payload.items])

        sd_values_sql, sd_params = _multi_values(
            ["nama", "spesifikasi", "satuan"],
            [
                {
                    "nama": item.nama,
                    "spesifikasi": item.spesifikasi or None,
                    "satuan": item.satuan,
                }
                for item in payload.items
            ],
        )
        sd_ids = conn.execute(
            text(f"INSERT INTO sumber_daya (nama, spesifikasi, satuan) VALUES {sd_values_sql} RETURNING id"),
            sd_params,
        ).scalars().all()

        harga_rows = [
            {
                "sumber_daya_id": sd_id,
                "supplier_id": supplier_map.get(item.supplier_nama.strip()) if item.supplier_nama.strip() else None,
                "harga_satuan": item.harga_satuan,
                "mata_uang": item.mata_uang,
                "nama_kapal": item.nama_kapal or None,
                "tahun_pembelian": item.tahun_pembelian,
                "berlaku_dari": item.berlaku_dari or date.today(),
                "sumber": item.sumber or None,
                "no_dokumen": item.no_dokumen or None,
                "catatan": item.catatan or None,
            }
            for sd_id, item in zip(sd_ids, payload.items, strict=True)
        ]
        harga_values_sql, harga_params = _multi_values(
            [
                "sumber_daya_id",
                "supplier_id",
                "harga_satuan",
                "mata_uang",
                "nama_kapal",
                "tahun_pembelian",
                "berlaku_dari",
                "sumber",
                "no_dokumen",
                "catatan",
            ],
            harga_rows,
        )
        conn.execute(
            text(
                "INSERT INTO sumber_daya_harga "
                "(sumber_daya_id, supplier_id, harga_satuan, mata_uang, nama_kapal, tahun_pembelian, "
                "berlaku_dari, sumber, no_dokumen, catatan) "
                f"VALUES {harga_values_sql}"
            ),
            harga_params,
        )
    return len(payload.items)


def bulk_patch(body: BulkPatchMaterialRequest) -> dict[str, int]:
    deleted = 0
    updated = 0
    with engine.begin() as conn:
        if body.delete_ids:
            conn.execute(
                text("DELETE FROM sumber_daya WHERE id = ANY(:ids)"), {"ids": body.delete_ids}
            )
            deleted = len(body.delete_ids)

        if body.updates:
            supplier_map = _resolve_suppliers(conn, [u.data.supplier_nama for u in body.updates])
            upd_q = text(
                """
                UPDATE sumber_daya
                SET nama = :nama, spesifikasi = :spesifikasi, satuan = :satuan
                WHERE id = :id
                """
            )
            for u in body.updates:
                d = u.data
                conn.execute(
                    upd_q,
                    {
                        "nama": d.nama,
                        "spesifikasi": d.spesifikasi or None,
                        "satuan": d.satuan,
                        "id": u.id,
                    },
                )
                supplier_id = supplier_map.get(d.supplier_nama.strip()) if d.supplier_nama.strip() else None
                _insert_harga(conn, u.id, d, supplier_id)
            updated = len(body.updates)
    return {"deleted": deleted, "updated": updated}
