import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.config import settings
from app.database import (
    ensure_ahsp_tables,
    ensure_audit_table,
    ensure_material_tables,
    ensure_partno_unique,
    ensure_pencarian_index,
)
from app.routers.ahsp import router as ahsp_router
from app.routers.analitik import router as analitik_router
from app.routers.catalog import router as catalog_router
from app.routers.material import router as material_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_material_tables()
    ensure_partno_unique()
    # Setelah material: ahsp_komponen punya foreign key ke sumber_daya.
    ensure_ahsp_tables()
    ensure_audit_table()
    # Paling akhir: index pencarian menempel ke sumber_daya dan tabel_katalog_harga,
    # jadi keduanya harus sudah ada.
    ensure_pencarian_index()
    yield


app = FastAPI(
    title="Dukuh Raya Maintenance API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(catalog_router)
app.include_router(material_router)
app.include_router(analitik_router)
app.include_router(ahsp_router)

logger = logging.getLogger(__name__)


# Eksepsi yang tidak tertangani berakhir di ServerErrorMiddleware, yang berada DI LUAR
# CORSMiddleware. Responsnya polos tanpa Access-Control-Allow-Origin, jadi browser
# memblokirnya dan JavaScript cuma bisa melapor "Failed to fetch" -- sebab aslinya hilang.
# Itu yang bikin kegagalan impor 31 Juli 2026 sulit dibaca.
#
# Penangan BERTIPE lewat ExceptionMiddleware, yang berada DI DALAM CORSMiddleware, sehingga
# responsnya membawa header CORS. Sengaja tidak mendaftarkan penangan untuk `Exception`
# polos: Starlette memperlakukan itu sebagai kasus khusus dan memasangnya di
# ServerErrorMiddleware juga, jadi masalahnya tidak selesai.


@app.exception_handler(IntegrityError)
def tangani_duplikat(request: Request, exc: IntegrityError):
    logger.exception("IntegrityError di %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=409,
        content={
            "detail": "Sebagian data ini sepertinya sudah tersimpan. Muat ulang halaman "
            "dan cek tabelnya dulu sebelum menyimpan lagi."
        },
    )


@app.exception_handler(SQLAlchemyError)
def tangani_error_db(request: Request, exc: SQLAlchemyError):
    # Isi eksepsi sengaja tidak dikirim ke pengguna -- detail lengkapnya sudah masuk log.
    logger.exception("SQLAlchemyError di %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Gagal menyimpan ke database. Coba lagi; kalau tetap gagal, laporkan "
            "waktu kejadiannya supaya bisa dicek di log."
        },
    )


@app.get("/health")
def health():
    return {"status": "ok"}
