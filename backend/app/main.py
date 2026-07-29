from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import ensure_audit_table, ensure_material_tables
from app.routers.analitik import router as analitik_router
from app.routers.catalog import router as catalog_router
from app.routers.material import router as material_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_material_tables()
    ensure_audit_table()
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


@app.get("/health")
def health():
    return {"status": "ok"}
