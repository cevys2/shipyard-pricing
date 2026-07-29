from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.services import analitik as analitik_service
from app.services import audit as audit_service

router = APIRouter(prefix="/analitik", tags=["analitik"])


@router.get("/tren-jasa")
def tren_jasa(
    _: Annotated[dict, Depends(get_current_user)],
    kategori: str | None = None,
    min_sampel: int = 3,
):
    return analitik_service.tren_harga_jasa(kategori=kategori, min_sampel=max(1, min_sampel))


@router.get("/tren-jasa/kategori")
def tren_jasa_kategori(_: Annotated[dict, Depends(get_current_user)]):
    return analitik_service.kategori_options()


@router.get("/tren-material")
def tren_material(_: Annotated[dict, Depends(get_current_user)]):
    return analitik_service.tren_material()


@router.get("/log")
def audit_log(
    _: Annotated[dict, Depends(get_current_user)],
    entitas: str | None = None,
    limit: int = 100,
):
    return audit_service.list_log(entitas=entitas, limit=limit)
