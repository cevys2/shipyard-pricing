import io
from typing import Any

import pandas as pd
from pydantic import ValidationError
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.schemas.catalog import (
    BulkCatalogCreate,
    BulkPatchRequest,
    CatalogItemBase,
    CatalogRowOut,
    CatalogStats,
    TipePerjanjian,
)
from app.services import audit

TABLE = settings.catalog_table

_COLUMNS = (
    "id, nama_perusahaan, nama_kapal, tipe_perjanjian, tahun, "
    "kategori_pekerjaan, uraian_pekerjaan, volume_satuan, harga_satuan"
)

_FILTER_COLS = {
    "perusahaan": "nama_perusahaan",
    "kapal": "nama_kapal",
    "kategori": "kategori_pekerjaan",
    "tahun": "tahun",
    "tipe": "tipe_perjanjian",
}


def _build_where(
    *,
    perusahaan: str | None = None,
    kapal: str | None = None,
    kategori: str | None = None,
    tahun: str | None = None,
    tipe: str | None = None,
    search: str | None = None,
) -> tuple[str, dict[str, Any]]:
    clauses = []
    params: dict[str, Any] = {}
    filters = {"perusahaan": perusahaan, "kapal": kapal, "kategori": kategori, "tahun": tahun, "tipe": tipe}
    for key, val in filters.items():
        if val and val != "Semua":
            col = _FILTER_COLS[key]
            clauses.append(f"{col} = :{key}")
            params[key] = val
    if search:
        clauses.append("uraian_pekerjaan ILIKE :search")
        params["search"] = f"%{search}%"
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def list_catalog(
    *,
    perusahaan: str | None = None,
    kapal: str | None = None,
    kategori: str | None = None,
    tahun: str | None = None,
    tipe: str | None = None,
    search: str | None = None,
) -> list[CatalogRowOut]:
    where, params = _build_where(
        perusahaan=perusahaan, kapal=kapal, kategori=kategori, tahun=tahun, tipe=tipe, search=search
    )
    query = text(f"SELECT {_COLUMNS} FROM {TABLE} {where} ORDER BY nama_kapal, id")
    with engine.connect() as conn:
        rows = conn.execute(query, params).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        for col in ("nama_perusahaan", "nama_kapal", "tipe_perjanjian", "tahun", "kategori_pekerjaan", "uraian_pekerjaan"):
            if d.get(col) is None:
                d[col] = "-"
        out.append(CatalogRowOut(**d))
    return out


def catalog_stats(
    *,
    perusahaan: str | None = None,
    kapal: str | None = None,
    kategori: str | None = None,
    tahun: str | None = None,
    tipe: str | None = None,
    search: str | None = None,
) -> CatalogStats:
    where, params = _build_where(
        perusahaan=perusahaan, kapal=kapal, kategori=kategori, tahun=tahun, tipe=tipe, search=search
    )
    query = text(
        f"""
        SELECT COUNT(*) AS total_item,
               COUNT(DISTINCT nama_perusahaan) AS total_klien,
               COUNT(DISTINCT nama_kapal) AS total_kapal,
               COUNT(DISTINCT tahun) AS total_tahun
        FROM {TABLE} {where}
        """
    )
    with engine.connect() as conn:
        row = conn.execute(query, params).mappings().first()
    if not row:
        return CatalogStats(total_item=0, total_klien=0, total_kapal=0, total_tahun=0)
    return CatalogStats(**dict(row))


def filter_options(
    *,
    perusahaan: str | None = None,
    kapal: str | None = None,
    kategori: str | None = None,
    tahun: str | None = None,
    tipe: str | None = None,
    search: str | None = None,
) -> dict[str, list[str]]:
    active = {"perusahaan": perusahaan, "kapal": kapal, "kategori": kategori, "tahun": tahun, "tipe": tipe}
    result: dict[str, list[str]] = {}
    with engine.connect() as conn:
        for key, col in _FILTER_COLS.items():
            others = {k: v for k, v in active.items() if k != key}
            where, params = _build_where(**others, search=search)
            rows = conn.execute(
                text(f"SELECT DISTINCT {col} FROM {TABLE} {where} ORDER BY {col}"), params
            ).all()
            result[key] = ["Semua"] + [r[0] for r in rows if r[0]]
    return result


def _next_ids(prefix: str, count: int) -> list[str]:
    with engine.connect() as conn:
        existing = conn.execute(
            text(f"SELECT id FROM {TABLE} WHERE id LIKE :prefix"), {"prefix": f"{prefix}%"}
        ).all()
    last_num = 0
    for (id_,) in existing:
        try:
            n = int(str(id_).split("-")[-1])
            last_num = max(last_num, n)
        except ValueError:
            continue
    ids = []
    for _ in range(count):
        last_num += 1
        ids.append(f"{prefix}{last_num:03d}")
    return ids


def bulk_create(payload: BulkCatalogCreate, *, aktor: str, sumber: str = "form") -> int:
    slug = payload.nama_kapal.strip().replace(" ", "_").upper()
    prefix = f"{slug}-{payload.tahun.strip()}-"
    ids = _next_ids(prefix, len(payload.items))

    insert_sql = text(
        f"""
        INSERT INTO {TABLE}
        (id, nama_perusahaan, nama_kapal, tipe_perjanjian, tahun,
         kategori_pekerjaan, uraian_pekerjaan, volume_satuan, harga_satuan)
        VALUES (:id, :pt, :kpl, :tipe, :thn, :kat, :urai, :sat, :hrg)
        """
    )

    pt = payload.nama_perusahaan.upper() if payload.nama_perusahaan else ""
    kpl = payload.nama_kapal.upper()
    tipe = payload.tipe_perjanjian.value

    with engine.begin() as conn:
        for new_id, item in zip(ids, payload.items, strict=True):
            conn.execute(
                insert_sql,
                {
                    "id": new_id,
                    "pt": pt,
                    "kpl": kpl,
                    "tipe": tipe,
                    "thn": payload.tahun,
                    "kat": item.kategori_pekerjaan or "-",
                    "urai": item.uraian_pekerjaan,
                    "sat": item.volume_satuan or "-",
                    "hrg": float(item.harga_satuan),
                },
            )
        audit.catat(
            conn,
            aktor=aktor,
            aksi="create",
            entitas="katalog_harga",
            jumlah=len(payload.items),
            detail={
                "nama_kapal": kpl,
                "tahun": payload.tahun,
                "tipe_perjanjian": tipe,
                "sumber": sumber,
                "id_range": [ids[0], ids[-1]] if ids else [],
            },
        )
    return len(payload.items)


def bulk_patch(body: BulkPatchRequest, *, aktor: str) -> dict[str, int]:
    deleted = 0
    updated = 0
    with engine.begin() as conn:
        if body.delete_ids:
            del_q = text(f"DELETE FROM {TABLE} WHERE id = :id")
            for del_id in body.delete_ids:
                conn.execute(del_q, {"id": del_id})
            deleted = len(body.delete_ids)
            audit.catat(
                conn,
                aktor=aktor,
                aksi="delete",
                entitas="katalog_harga",
                jumlah=deleted,
                detail={"ids": body.delete_ids[:50]},
            )

        if body.updates:
            upd_q = text(
                f"""
                UPDATE {TABLE}
                SET nama_perusahaan = :pt, nama_kapal = :kpl, tipe_perjanjian = :tipe, tahun = :thn,
                    kategori_pekerjaan = :kat, uraian_pekerjaan = :urai,
                    volume_satuan = :sat, harga_satuan = :hrg
                WHERE id = :id
                """
            )
            for u in body.updates:
                d = u.data
                conn.execute(
                    upd_q,
                    {
                        "pt": d.nama_perusahaan,
                        "kpl": d.nama_kapal,
                        "tipe": d.tipe_perjanjian.value,
                        "thn": d.tahun,
                        "kat": d.kategori_pekerjaan,
                        "urai": d.uraian_pekerjaan,
                        "sat": d.volume_satuan,
                        "hrg": d.harga_satuan,
                        "id": u.id,
                    },
                )
            updated = len(body.updates)
            audit.catat(
                conn,
                aktor=aktor,
                aksi="update",
                entitas="katalog_harga",
                jumlah=updated,
                detail={"ids": [u.id for u in body.updates][:50]},
            )
    return {"deleted": deleted, "updated": updated}


def parse_spreadsheet(file_bytes: bytes, filename: str) -> tuple[BulkCatalogCreate | None, list[str]]:
    """
    Otomatis: upload Excel/CSV → Pydantic validasi per baris.
    Format kolom: Kategori | Uraian | Satuan | Harga (+ sheet/header opsional untuk kapal/tahun).
    """
    errors: list[str] = []
    name = filename.lower()

    if name.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(file_bytes))
    elif name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(file_bytes))
    else:
        return None, ["File harus .csv, .xlsx, atau .xls"]

    df.columns = [str(c).strip() for c in df.columns]

    col_map = {
        "kategori_pekerjaan": ["kategori", "kategori pekerjaan", "kategori_pekerjaan"],
        "uraian_pekerjaan": ["uraian", "uraian pekerjaan", "uraian_pekerjaan"],
        "volume_satuan": ["satuan", "volume", "volume_satuan", "satuan (volume)"],
        "harga_satuan": ["harga", "harga satuan", "harga_satuan"],
    }

    def find_col(keys: list[str]) -> str | None:
        lower = {c.lower(): c for c in df.columns}
        for k in keys:
            if k in lower:
                return lower[k]
        return None

    mapped = {}
    for field, keys in col_map.items():
        col = find_col(keys)
        if col:
            mapped[field] = col

    if "uraian_pekerjaan" not in mapped:
        return None, ["Kolom 'Uraian Pekerjaan' tidak ditemukan di file"]

    header_cols = {
        "nama_kapal": ["nama kapal", "kapal", "nama_kapal"],
        "tahun": ["tahun"],
        "nama_perusahaan": ["perusahaan", "klien", "nama perusahaan", "nama_perusahaan"],
        "tipe_perjanjian": ["tipe", "tipe perjanjian", "tipe_perjanjian"],
    }

    header: dict[str, str] = {}
    for field, keys in header_cols.items():
        col = find_col(keys)
        if col and len(df[col].dropna()) > 0:
            val = df[col].dropna().iloc[0]
            header[field] = str(val).strip()

    items: list[CatalogItemBase] = []
    for idx, row in df.iterrows():
        raw = {}
        for field, col in mapped.items():
            val = row[col]
            if pd.isna(val):
                val = "-" if field != "harga_satuan" else 0
            raw[field] = val
        if str(raw.get("uraian_pekerjaan", "")).strip() in ("", "-", "nan"):
            continue
        try:
            items.append(CatalogItemBase(**raw))
        except ValidationError as e:
            errors.append(f"Baris {int(idx) + 2}: {e.errors()[0]['msg']}")

    if not items:
        return None, errors or ["Tidak ada baris valid di file"]

    if "nama_kapal" not in header or "tahun" not in header:
        return None, [
            "Tambahkan kolom 'Nama Kapal' dan 'Tahun' di Excel (isi sama di setiap baris), "
            "atau gunakan form JSON bulk di API."
        ]

    tipe = header.get("tipe_perjanjian", "Induk")
    try:
        tipe_enum = TipePerjanjian(tipe) if tipe in ("Induk", "Addendum") else TipePerjanjian.induk
    except ValueError:
        tipe_enum = TipePerjanjian.induk

    try:
        bulk = BulkCatalogCreate(
            nama_perusahaan=header.get("nama_perusahaan", ""),
            nama_kapal=header["nama_kapal"],
            tahun=header["tahun"],
            tipe_perjanjian=tipe_enum,
            items=items,
        )
    except ValidationError as e:
        return None, [f"Header invalid: {e.errors()[0]['msg']}"]

    return bulk, errors
