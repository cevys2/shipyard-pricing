from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user
from app.schemas.material import (
    BulkMaterialCreate,
    BulkPatchMaterialRequest,
    MaterialRowOut,
    MaterialStats,
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


@router.post("/bulk")
def create_bulk(
    body: BulkMaterialCreate,
    _: Annotated[dict, Depends(get_current_user)],
):
    count = material_service.bulk_create(body)
    return {"saved": count}


@router.patch("")
def patch_material(
    body: BulkPatchMaterialRequest,
    _: Annotated[dict, Depends(get_current_user)],
):
    if not body.updates and not body.delete_ids:
        raise HTTPException(status_code=400, detail="Tidak ada perubahan")
    return material_service.bulk_patch(body)
