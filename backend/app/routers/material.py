from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user
from app.schemas.material import (
    BulkMaterialCreate,
    BulkPatchMaterialRequest,
    MaterialRowOut,
    MaterialStats,
    PriceCreate,
    PriceHistoryRow,
)
from app.services import material as material_service

router = APIRouter(prefix="/material", tags=["material"])


@router.get("", response_model=list[MaterialRowOut])
def get_material(
    _: Annotated[dict, Depends(get_current_user)],
    supplier: str | None = None,
    satuan: str | None = None,
    kapal: str | None = None,
    tahun: str | None = None,
    search: str | None = None,
):
    return material_service.list_material(
        supplier=supplier, satuan=satuan, kapal=kapal, tahun=tahun, search=search
    )


@router.get("/stats", response_model=MaterialStats)
def get_stats(
    _: Annotated[dict, Depends(get_current_user)],
    supplier: str | None = None,
    satuan: str | None = None,
    kapal: str | None = None,
    tahun: str | None = None,
    search: str | None = None,
):
    return material_service.material_stats(
        supplier=supplier, satuan=satuan, kapal=kapal, tahun=tahun, search=search
    )


@router.get("/filters")
def get_filters(
    _: Annotated[dict, Depends(get_current_user)],
    supplier: str | None = None,
    satuan: str | None = None,
    kapal: str | None = None,
    tahun: str | None = None,
    search: str | None = None,
):
    return material_service.filter_options(
        supplier=supplier, satuan=satuan, kapal=kapal, tahun=tahun, search=search
    )


@router.post("/bulk/preview")
def preview_bulk(
    body: BulkMaterialCreate,
    _: Annotated[dict, Depends(get_current_user)],
):
    """Apa yang akan terjadi kalau paste ini disimpan -- tanpa menulis apa pun."""
    return material_service.preview_bulk(body)


@router.post("/bulk")
def create_bulk(
    body: BulkMaterialCreate,
    user: Annotated[dict, Depends(get_current_user)],
):
    return material_service.bulk_create(body, aktor=user["username"])


@router.patch("")
def patch_material(
    body: BulkPatchMaterialRequest,
    user: Annotated[dict, Depends(get_current_user)],
):
    if not body.updates and not body.delete_ids:
        raise HTTPException(status_code=400, detail="Tidak ada perubahan")
    return material_service.bulk_patch(body, aktor=user["username"])


@router.get("/{sumber_daya_id}/harga", response_model=list[PriceHistoryRow])
def get_price_history(
    sumber_daya_id: int,
    _: Annotated[dict, Depends(get_current_user)],
):
    return material_service.price_history(sumber_daya_id)


@router.post("/{sumber_daya_id}/harga")
def add_price(
    sumber_daya_id: int,
    body: PriceCreate,
    user: Annotated[dict, Depends(get_current_user)],
):
    try:
        new_id = material_service.add_price(sumber_daya_id, body, aktor=user["username"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"id": new_id}


@router.delete("/harga/{harga_id}")
def delete_price(
    harga_id: int,
    user: Annotated[dict, Depends(get_current_user)],
):
    try:
        material_service.delete_price(harga_id, aktor=user["username"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"deleted": 1}
