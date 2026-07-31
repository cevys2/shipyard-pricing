from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.auth import get_current_user, require_admin
from app.database import engine
from app.schemas.catalog import (
    BulkCatalogCreate,
    BulkPatchRequest,
    CatalogRowOut,
    CatalogStats,
    DockingImportCommit,
    DockingImportPreview,
    TipePerjanjian,
)
from app.services import catalog as catalog_service
from app.services import docking_parser

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("", response_model=list[CatalogRowOut])
def get_catalog(
    _: Annotated[dict, Depends(get_current_user)],
    perusahaan: str | None = None,
    kapal: str | None = None,
    kategori: str | None = None,
    tahun: str | None = None,
    tipe: str | None = None,
    search: str | None = None,
):
    return catalog_service.list_catalog(
        perusahaan=perusahaan,
        kapal=kapal,
        kategori=kategori,
        tahun=tahun,
        tipe=tipe,
        search=search,
    )


@router.get("/stats", response_model=CatalogStats)
def get_stats(
    _: Annotated[dict, Depends(get_current_user)],
    perusahaan: str | None = None,
    kapal: str | None = None,
    kategori: str | None = None,
    tahun: str | None = None,
    tipe: str | None = None,
    search: str | None = None,
):
    return catalog_service.catalog_stats(
        perusahaan=perusahaan,
        kapal=kapal,
        kategori=kategori,
        tahun=tahun,
        tipe=tipe,
        search=search,
    )


@router.get("/filters")
def get_filters(
    _: Annotated[dict, Depends(get_current_user)],
    perusahaan: str | None = None,
    kapal: str | None = None,
    kategori: str | None = None,
    tahun: str | None = None,
    tipe: str | None = None,
    search: str | None = None,
):
    return catalog_service.filter_options(
        perusahaan=perusahaan,
        kapal=kapal,
        kategori=kategori,
        tahun=tahun,
        tipe=tipe,
        search=search,
    )


@router.post("/bulk")
def create_bulk(
    body: BulkCatalogCreate,
    user: Annotated[dict, Depends(get_current_user)],
):
    count = catalog_service.bulk_create(body, aktor=user["username"])
    return {"saved": count}


@router.post("/import")
async def import_file(
    user: Annotated[dict, Depends(get_current_user)],
    file: UploadFile = File(...),
    dry_run: bool = Query(False, description="True = hanya validasi, tidak simpan"),
):
    content = await file.read()
    bulk, errors = catalog_service.parse_spreadsheet(content, file.filename or "upload.xlsx")
    if bulk is None:
        raise HTTPException(status_code=400, detail={"message": "Import gagal", "errors": errors})
    if dry_run:
        return {
            "valid": True,
            "rows": len(bulk.items),
            "preview_header": {
                "nama_perusahaan": bulk.nama_perusahaan,
                "nama_kapal": bulk.nama_kapal,
                "tahun": bulk.tahun,
                "tipe_perjanjian": bulk.tipe_perjanjian.value,
            },
            "warnings": errors,
        }
    saved = catalog_service.bulk_create(bulk, aktor=user["username"], sumber="import-excel")
    return {"saved": saved, "warnings": errors}


@router.post("/import/docking-preview", response_model=DockingImportPreview)
async def import_docking_preview(
    _: Annotated[dict, Depends(get_current_user)],
    file: UploadFile = File(...),
):
    content = await file.read()
    try:
        result = docking_parser.parse_docking_file(content, file.filename or "upload.xlsx")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Gagal membaca file: {e}")
    return result


@router.post("/import/docking-commit")
def import_docking_commit(
    body: DockingImportCommit,
    user: Annotated[dict, Depends(get_current_user)],
):
    if not body.induk_items and not body.addendum_items:
        raise HTTPException(status_code=400, detail="Tidak ada baris untuk disimpan")
    saved = 0
    # SATU transaksi untuk Induk dan Addendum sekaligus. Sebelumnya masing-masing membuka
    # transaksinya sendiri, sehingga Induk bisa commit lalu Addendum gagal -- separuh data
    # masuk tanpa pengguna punya cara tahu. Persis yang terjadi 31 Juli 2026.
    with engine.begin() as conn:
        if body.induk_items:
            saved += catalog_service.bulk_create(
                BulkCatalogCreate(
                    nama_perusahaan=body.nama_perusahaan,
                    nama_kapal=body.nama_kapal,
                    tahun=body.tahun,
                    tipe_perjanjian=TipePerjanjian.induk,
                    items=body.induk_items,
                ),
                aktor=user["username"],
                sumber="import-docking",
                conn=conn,
            )
        if body.addendum_items:
            saved += catalog_service.bulk_create(
                BulkCatalogCreate(
                    nama_perusahaan=body.nama_perusahaan,
                    nama_kapal=body.nama_kapal,
                    tahun=body.tahun,
                    tipe_perjanjian=TipePerjanjian.addendum,
                    items=body.addendum_items,
                ),
                aktor=user["username"],
                sumber="import-docking",
                conn=conn,
            )
    return {"saved": saved}


@router.patch("")
def patch_catalog(
    body: BulkPatchRequest,
    user: Annotated[dict, Depends(get_current_user)],
):
    if not body.updates and not body.delete_ids:
        raise HTTPException(status_code=400, detail="Tidak ada perubahan")
    return catalog_service.bulk_patch(body, aktor=user["username"])
