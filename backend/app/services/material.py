from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.database import engine, sd_identitas_sql
from app.schemas.material import (
    BulkMaterialCreate,
    BulkPatchMaterialRequest,
    MaterialItemCreate,
    MaterialRowOut,
    MaterialStats,
    PriceHistoryRow,
    PriceCreate,
)
from app.services import audit

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


def _insert_harga(conn: Connection, sumber_daya_id: int, item: PriceCreate, supplier_id: int | None) -> None:
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


def _identitas_key(nama: str, spesifikasi: str | None, satuan: str) -> tuple[str, str, str]:
    """Versi Python dari `sd_identitas_sql()` -- harus menormalisasi dengan cara yang sama
    (lowercase, spasi beruntun jadi satu) supaya lookup di sini sepakat dengan unique index
    `uq_sd_identitas` di DB."""
    norm = lambda s: " ".join((s or "").split()).lower()  # noqa: E731
    return norm(nama), norm(spesifikasi), norm(satuan)


def _resolve_sumber_daya(conn: Connection, items: list[MaterialItemCreate]) -> list[int]:
    """Cari-atau-buat master material, kembalikan id sejajar dengan `items`.

    Dulu fungsi ini selalu INSERT, jadi paste batch yang sama dua kali bikin material
    kembar dan riwayat harganya terbelah. Sekarang material yang sudah ada dipakai ulang,
    sehingga harga baru menempel jadi TITIK RIWAYAT di material yang sama -- inilah yang
    bikin tren harga bisa terbentuk sama sekali.
    """
    keys = [_identitas_key(i.nama, i.spesifikasi, i.satuan) for i in items]
    existing: dict[tuple[str, str, str], int] = {}

    rows = conn.execute(
        text(f"SELECT id, {sd_identitas_sql()} FROM sumber_daya WHERE jenis = 'BAHAN'")
    ).all()
    for id_, n, s, sat, _jenis in rows:
        existing[(n, s, sat)] = id_

    # Batch yang sama bisa memuat material yang sama dua kali; yang kedua harus memakai
    # id hasil insert yang pertama, bukan bikin baris baru lagi.
    baru = []
    for key, item in zip(keys, items, strict=True):
        if key not in existing:
            existing[key] = -1
            baru.append(item)

    if baru:
        values_sql, params = _multi_values(
            ["nama", "spesifikasi", "satuan"],
            [{"nama": i.nama, "spesifikasi": i.spesifikasi or None, "satuan": i.satuan} for i in baru],
        )
        inserted = conn.execute(
            text(
                f"INSERT INTO sumber_daya (nama, spesifikasi, satuan) VALUES {values_sql} "
                "RETURNING id, nama, spesifikasi, satuan"
            ),
            params,
        ).all()
        for id_, nama, spek, satuan in inserted:
            existing[_identitas_key(nama, spek, satuan)] = id_

    return [existing[k] for k in keys]


def bulk_create(payload: BulkMaterialCreate, *, aktor: str) -> int:
    with engine.begin() as conn:
        supplier_map = _resolve_suppliers(conn, [item.supplier_nama for item in payload.items])
        sd_ids = _resolve_sumber_daya(conn, payload.items)

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
        audit.catat(
            conn,
            aktor=aktor,
            aksi="create",
            entitas="material",
            jumlah=len(payload.items),
            detail={"nama": [i.nama for i in payload.items[:20]]},
        )
    return len(payload.items)


def _harga_berubah(conn: Connection, sumber_daya_id: int, item: PriceCreate, supplier_id: int | None) -> bool:
    """True kalau harga yang dikirim beda dari titik harga terakhir material ini.

    Tanpa cek ini, `bulk_patch` menyisipkan baris harga baru SETIAP kali material di-edit
    -- benerin typo di kolom nama pun bikin satu "titik harga" palsu. Untuk katalog biasa
    itu tak kelihatan, tapi buat grafik tren itu racun: riwayatnya jadi campuran antara
    perubahan harga asli dan jejak penyuntingan.
    """
    row = conn.execute(
        text(
            """
            SELECT harga_satuan, mata_uang, supplier_id, berlaku_dari, tahun_pembelian, nama_kapal
            FROM   sumber_daya_harga
            WHERE  sumber_daya_id = :id
            ORDER  BY berlaku_dari DESC, id DESC
            LIMIT  1
            """
        ),
        {"id": sumber_daya_id},
    ).mappings().first()
    if row is None:
        return True
    return (
        float(row["harga_satuan"]) != float(item.harga_satuan)
        or row["mata_uang"] != item.mata_uang
        or row["supplier_id"] != supplier_id
        or row["berlaku_dari"] != (item.berlaku_dari or date.today())
        or row["tahun_pembelian"] != item.tahun_pembelian
        or (row["nama_kapal"] or "") != (item.nama_kapal or "")
    )


def bulk_patch(body: BulkPatchMaterialRequest, *, aktor: str) -> dict[str, int]:
    deleted = 0
    updated = 0
    harga_baru = 0
    with engine.begin() as conn:
        if body.delete_ids:
            nama_dihapus = conn.execute(
                text("SELECT nama FROM sumber_daya WHERE id = ANY(:ids)"), {"ids": body.delete_ids}
            ).scalars().all()
            conn.execute(
                text("DELETE FROM sumber_daya WHERE id = ANY(:ids)"), {"ids": body.delete_ids}
            )
            deleted = len(body.delete_ids)
            audit.catat(
                conn,
                aktor=aktor,
                aksi="delete",
                entitas="material",
                jumlah=deleted,
                detail={"ids": body.delete_ids, "nama": list(nama_dihapus)[:20]},
            )

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
                if _harga_berubah(conn, u.id, d, supplier_id):
                    _insert_harga(conn, u.id, d, supplier_id)
                    harga_baru += 1
            updated = len(body.updates)
            audit.catat(
                conn,
                aktor=aktor,
                aksi="update",
                entitas="material",
                jumlah=updated,
                detail={
                    "ids": [u.id for u in body.updates][:20],
                    "titik_harga_baru": harga_baru,
                },
            )
    return {"deleted": deleted, "updated": updated, "titik_harga_baru": harga_baru}


# ---------- Riwayat harga per material ----------


def price_history(sumber_daya_id: int) -> list[PriceHistoryRow]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT h.id, h.harga_satuan, h.mata_uang, h.berlaku_dari, h.tahun_pembelian,
                       h.nama_kapal, h.sumber, h.no_dokumen, h.catatan, h.dibuat_pada,
                       sup.nama AS supplier_nama
                FROM   sumber_daya_harga h
                LEFT   JOIN supplier sup ON sup.id = h.supplier_id
                WHERE  h.sumber_daya_id = :id
                ORDER  BY h.berlaku_dari ASC, h.id ASC
                """
            ),
            {"id": sumber_daya_id},
        ).mappings().all()
    return [PriceHistoryRow(**dict(r)) for r in rows]


def add_price(sumber_daya_id: int, item: PriceCreate, *, aktor: str) -> int:
    with engine.begin() as conn:
        ada = conn.execute(
            text("SELECT nama FROM sumber_daya WHERE id = :id"), {"id": sumber_daya_id}
        ).scalar()
        if ada is None:
            raise ValueError("Material tidak ditemukan")
        supplier_map = _resolve_suppliers(conn, [item.supplier_nama])
        supplier_id = supplier_map.get(item.supplier_nama.strip()) if item.supplier_nama.strip() else None
        _insert_harga(conn, sumber_daya_id, item, supplier_id)
        new_id = conn.execute(
            text("SELECT id FROM sumber_daya_harga WHERE sumber_daya_id = :id ORDER BY id DESC LIMIT 1"),
            {"id": sumber_daya_id},
        ).scalar()
        audit.catat(
            conn,
            aktor=aktor,
            aksi="create",
            entitas="material_harga",
            detail={
                "sumber_daya_id": sumber_daya_id,
                "nama": ada,
                "harga_satuan": float(item.harga_satuan),
                "mata_uang": item.mata_uang,
                "berlaku_dari": item.berlaku_dari or date.today(),
            },
        )
    return int(new_id)


def delete_price(harga_id: int, *, aktor: str) -> None:
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT sumber_daya_id, harga_satuan, berlaku_dari FROM sumber_daya_harga WHERE id = :id"),
            {"id": harga_id},
        ).mappings().first()
        if row is None:
            raise ValueError("Titik harga tidak ditemukan")
        sisa = conn.execute(
            text("SELECT COUNT(*) FROM sumber_daya_harga WHERE sumber_daya_id = :id"),
            {"id": row["sumber_daya_id"]},
        ).scalar()
        # Material tanpa harga sama sekali bakal hilang dari daftar katalog (view
        # v_harga_terkini kosong -> kolom harga null), jadi tolak di sini biar tidak
        # ada material "hantu" yang cuma bisa dibetulkan lewat SQL manual.
        if sisa is not None and int(sisa) <= 1:
            raise ValueError(
                "Ini satu-satunya titik harga material tersebut. "
                "Tambahkan harga baru dulu, atau hapus materialnya dari tabel katalog."
            )
        conn.execute(text("DELETE FROM sumber_daya_harga WHERE id = :id"), {"id": harga_id})
        audit.catat(
            conn,
            aktor=aktor,
            aksi="delete",
            entitas="material_harga",
            detail={
                "harga_id": harga_id,
                "sumber_daya_id": row["sumber_daya_id"],
                "harga_satuan": float(row["harga_satuan"]),
                "berlaku_dari": row["berlaku_dari"],
            },
        )
