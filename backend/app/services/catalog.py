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

TABLE = settings.catalog_table


def _load_all_rows() -> list[dict[str, Any]]:
    query = f"""
    SELECT id, nama_perusahaan, nama_kapal, tipe_perjanjian, tahun,
           kategori_pekerjaan, uraian_pekerjaan, volume_satuan, harga_satuan
    FROM {TABLE}
    ORDER BY nama_kapal, id
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)
    for col in ["nama_perusahaan", "nama_kapal", "tipe_perjanjian", "tahun", "kategori_pekerjaan"]:
        df[col] = df[col].fillna("-").astype(str)
    df["uraian_pekerjaan"] = df["uraian_pekerjaan"].fillna("-").astype(str)
    return df.to_dict(orient="records")


def list_catalog(
    *,
    perusahaan: str | None = None,
    kapal: str | None = None,
    kategori: str | None = None,
    tahun: str | None = None,
    tipe: str | None = None,
    search: str | None = None,
) -> list[CatalogRowOut]:
    rows = _load_all_rows()
    df = pd.DataFrame(rows)
    if df.empty:
        return []

    def eq(col: str, val: str | None):
        nonlocal df
        if val and val != "Semua":
            df = df[df[col] == val]

    eq("nama_perusahaan", perusahaan)
    eq("nama_kapal", kapal)
    eq("kategori_pekerjaan", kategori)
    eq("tahun", tahun)
    eq("tipe_perjanjian", tipe)
    if search:
        df = df[df["uraian_pekerjaan"].str.contains(search, case=False, na=False)]

    return [CatalogRowOut(**r) for r in df.to_dict(orient="records")]


def catalog_stats(**filters) -> CatalogStats:
    rows = list_catalog(**filters)
    if not rows:
        return CatalogStats(total_item=0, total_klien=0, total_kapal=0, total_tahun=0)
    df = pd.DataFrame([r.model_dump() for r in rows])
    return CatalogStats(
        total_item=len(df),
        total_klien=df["nama_perusahaan"].nunique(),
        total_kapal=df["nama_kapal"].nunique(),
        total_tahun=df["tahun"].nunique(),
    )


def filter_options() -> dict[str, list[str]]:
    rows = _load_all_rows()
    df = pd.DataFrame(rows)
    if df.empty:
        return {
            "perusahaan": ["Semua"],
            "kapal": ["Semua"],
            "kategori": ["Semua"],
            "tahun": ["Semua"],
            "tipe": ["Semua"],
        }

    def opts(col: str) -> list[str]:
        return ["Semua"] + sorted(df[col].dropna().unique().tolist())

    return {
        "perusahaan": opts("nama_perusahaan"),
        "kapal": opts("nama_kapal"),
        "kategori": opts("kategori_pekerjaan"),
        "tahun": opts("tahun"),
        "tipe": opts("tipe_perjanjian"),
    }


def _next_ids(prefix: str, count: int, all_rows: list[dict]) -> list[str]:
    df_cek = [r for r in all_rows if str(r["id"]).startswith(prefix)]
    try:
        last_num = max(int(str(r["id"]).split("-")[-1]) for r in df_cek) if df_cek else 0
    except ValueError:
        last_num = len(df_cek)
    ids = []
    for i in range(count):
        last_num += 1
        ids.append(f"{prefix}{last_num:03d}")
    return ids


def bulk_create(payload: BulkCatalogCreate) -> int:
    all_rows = _load_all_rows()
    slug = payload.nama_kapal.strip().replace(" ", "_").upper()
    prefix = f"{slug}-{payload.tahun.strip()}-"
    ids = _next_ids(prefix, len(payload.items), all_rows)

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
    return len(payload.items)


def bulk_patch(body: BulkPatchRequest) -> dict[str, int]:
    deleted = 0
    updated = 0
    with engine.begin() as conn:
        if body.delete_ids:
            del_q = text(f"DELETE FROM {TABLE} WHERE id = :id")
            for del_id in body.delete_ids:
                conn.execute(del_q, {"id": del_id})
            deleted = len(body.delete_ids)

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
