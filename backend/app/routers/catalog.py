from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.auth import get_current_user, require_admin
from app.schemas.catalog import BulkCatalogCreate, BulkPatchRequest, CatalogRowOut, CatalogStats
from app.services import catalog as catalog_service

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
def get_filters(_: Annotated[dict, Depends(get_current_user)]):
    return catalog_service.filter_options()


@router.post("/bulk")
def create_bulk(
    body: BulkCatalogCreate,
    _: Annotated[dict, Depends(get_current_user)],
):
    count = catalog_service.bulk_create(body)
    return {"saved": count}


@router.post("/import")
async def import_file(
    _: Annotated[dict, Depends(get_current_user)],
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
    saved = catalog_service.bulk_create(bulk)
    return {"saved": saved, "warnings": errors}


@router.patch("")
def patch_catalog(
    body: BulkPatchRequest,
    _: Annotated[dict, Depends(get_current_user)],
):
    if not body.updates and not body.delete_ids:
        raise HTTPException(status_code=400, detail="Tidak ada perubahan")
    return catalog_service.bulk_patch(body)
