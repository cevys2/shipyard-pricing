from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.auth import get_current_user
from app.services import analitik as analitik_service
from app.services import audit as audit_service
from app.services import harga_wajar as harga_wajar_service

router = APIRouter(prefix="/analitik", tags=["analitik"])


@router.get("/tren-jasa")
def tren_jasa(
    _: Annotated[dict, Depends(get_current_user)],
    kategori: str | None = None,
    min_sampel: int = 3,
):
    return analitik_service.tren_harga_jasa(kategori=kategori, min_sampel=max(1, min_sampel))


@router.get("/tren-jasa/kategori")
def tren_jasa_kategori(
    _: Annotated[dict, Depends(get_current_user)],
    min_sampel: int = 3,
):
    # min_sampel harus sama dengan yang dipakai /tren-jasa, kalau tidak daftar opsinya
    # bisa memuat kategori yang grafiknya kosong.
    return analitik_service.kategori_options(min_sampel=max(1, min_sampel))


@router.get("/nilai-pekerjaan")
def nilai_pekerjaan(_: Annotated[dict, Depends(get_current_user)]):
    # Tanpa parameter: agregatnya sudah kecil (puluhan baris) dan seluruh pengirisan --
    # per tahun, per jenis kapal, per klien -- dikerjakan di layar. Menambah filter di
    # sini berarti dua tempat yang harus sepakat soal apa yang disaring.
    return analitik_service.nilai_pekerjaan()


@router.get("/harga-wajar")
def harga_wajar(
    _: Annotated[dict, Depends(get_current_user)],
    q: Annotated[str, Query(max_length=200)] = "",
):
    # Satu parameter saja. Ambang kapan median boleh tampil sengaja tidak bisa diatur dari
    # request -- aturannya satu, di services/harga_wajar.py, dan layar membaca `aturan`
    # dari respons supaya kalimat penjelasnya tidak bisa berbeda dari yang dihitung.
    #
    # max_length menggantikan pemotongan 8 kata: di mode ketat tiap kata adalah syarat AND,
    # jadi memotong diam-diam justru melonggarkan hasil. Kata kunci yang terlalu panjang
    # ditolak terang-terangan (422), bukan dipotong.
    return harga_wajar_service.harga_wajar(q)


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
