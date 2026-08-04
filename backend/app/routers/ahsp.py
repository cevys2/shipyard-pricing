from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_admin
from app.schemas.ahsp import (
    AhspCreate,
    AhspOut,
    AhspUpdate,
    HitungOut,
    KomponenInput,
    KomponenOut,
    RingkasOut,
)
from app.services import ahsp as ahsp_service

# Seluruh tab dibatasi admin (A6 di rencana): isinya harga beli dan tarif upah, yang lebih
# sensitif daripada harga jual di tab katalog. Mudah dilonggarkan kalau klien memutuskan lain.
router = APIRouter(prefix="/ahsp", tags=["ahsp"])


@router.get("", response_model=list[AhspOut])
def get_ahsp(_: Annotated[dict, Depends(require_admin)]):
    return ahsp_service.list_ahsp()


# Didaftarkan sebelum /{ahsp_id} supaya "ringkas" tidak ditangkap sebagai id.
@router.get("/ringkas", response_model=RingkasOut)
def get_ringkas(_: Annotated[dict, Depends(require_admin)]):
    return ahsp_service.ringkas()


@router.post("")
def create_ahsp(body: AhspCreate, user: Annotated[dict, Depends(require_admin)]):
    return {"id": ahsp_service.create_ahsp(body, aktor=user["username"])}


@router.patch("/{ahsp_id}")
def patch_ahsp(ahsp_id: int, body: AhspUpdate, user: Annotated[dict, Depends(require_admin)]):
    if not ahsp_service.update_ahsp(ahsp_id, body, aktor=user["username"]):
        raise HTTPException(status_code=404, detail="AHSP tidak ditemukan")
    return {"updated": 1}


@router.delete("/{ahsp_id}")
def hapus_ahsp(ahsp_id: int, user: Annotated[dict, Depends(require_admin)]):
    if not ahsp_service.delete_ahsp(ahsp_id, aktor=user["username"]):
        raise HTTPException(status_code=404, detail="AHSP tidak ditemukan")
    return {"deleted": 1}


@router.get("/{ahsp_id}/komponen", response_model=list[KomponenOut])
def get_komponen(ahsp_id: int, _: Annotated[dict, Depends(require_admin)]):
    return ahsp_service.komponen(ahsp_id)


@router.put("/{ahsp_id}/komponen")
def put_komponen(
    ahsp_id: int,
    body: list[KomponenInput],
    user: Annotated[dict, Depends(require_admin)],
):
    """Ganti seluruh rincian sekaligus, satu transaksi -- tidak ada simpan separuh."""
    try:
        n = ahsp_service.ganti_komponen(ahsp_id, body, aktor=user["username"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"komponen": n}


@router.get("/{ahsp_id}/hitung", response_model=HitungOut)
def get_hitung(ahsp_id: int, _: Annotated[dict, Depends(require_admin)]):
    hasil = ahsp_service.hitung(ahsp_id)
    if hasil is None:
        raise HTTPException(status_code=404, detail="AHSP tidak ditemukan")
    return hasil
