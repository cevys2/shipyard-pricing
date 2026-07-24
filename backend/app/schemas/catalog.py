from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator


class TipePerjanjian(str, Enum):
    induk = "Induk"
    addendum = "Addendum"


class CatalogItemBase(BaseModel):
    """Satu baris pekerjaan di katalog — Pydantic menolak data rusak sebelum masuk DB."""

    kategori_pekerjaan: str = Field(default="-", max_length=500)
    uraian_pekerjaan: str = Field(min_length=1, max_length=2000)
    volume_satuan: str = Field(default="-", max_length=100)
    harga_satuan: float = Field(ge=0, description="Rupiah, tidak boleh negatif")

    @field_validator("uraian_pekerjaan")
    @classmethod
    def uraian_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v or v == "-":
            raise ValueError("Uraian pekerjaan wajib diisi")
        return v


class BulkCatalogCreate(BaseModel):
    """Header + banyak baris — sama seperti form Streamlit bulk entry."""

    nama_perusahaan: str = Field(default="", max_length=300)
    nama_kapal: Annotated[str, Field(min_length=1, max_length=200)]
    tahun: Annotated[str, Field(min_length=1, max_length=20)]
    tipe_perjanjian: TipePerjanjian = TipePerjanjian.induk
    items: Annotated[list[CatalogItemBase], Field(min_length=1)]

    @field_validator("nama_kapal", "tahun", "nama_perusahaan", mode="before")
    @classmethod
    def strip_strings(cls, v):
        if v is None:
            return v
        return str(v).strip()


class CatalogRowUpdate(BaseModel):
    nama_perusahaan: str
    nama_kapal: str
    tipe_perjanjian: TipePerjanjian
    tahun: str
    kategori_pekerjaan: str
    uraian_pekerjaan: str
    volume_satuan: str
    harga_satuan: float = Field(ge=0)


class CatalogRowOut(BaseModel):
    id: str
    nama_perusahaan: str
    nama_kapal: str
    tipe_perjanjian: str
    tahun: str
    kategori_pekerjaan: str
    uraian_pekerjaan: str
    volume_satuan: str
    harga_satuan: float


class CatalogStats(BaseModel):
    total_item: int
    total_klien: int
    total_kapal: int
    total_tahun: int


class BulkDeleteRequest(BaseModel):
    ids: list[str] = Field(min_length=1)


class BulkUpdateItem(BaseModel):
    id: str
    data: CatalogRowUpdate


class BulkPatchRequest(BaseModel):
    updates: list[BulkUpdateItem] = Field(default_factory=list)
    delete_ids: list[str] = Field(default_factory=list)


class DockingParsedItem(BaseModel):
    row: int
    kategori: str | None = None
    uraian: str
    volume_satuan: str = "-"
    keterangan: str = ""
    harga: float = 0


class DockingImportPreview(BaseModel):
    sheet_name: str
    detected_nama_kapal: str = ""
    detected_nama_perusahaan: str = ""
    detected_tahun: str = ""
    induk: list[DockingParsedItem]
    addendum: list[DockingParsedItem]
    warnings: list[str]


class DockingImportCommit(BaseModel):
    nama_perusahaan: str = ""
    nama_kapal: Annotated[str, Field(min_length=1, max_length=200)]
    tahun: Annotated[str, Field(min_length=1, max_length=20)]
    induk_items: list[CatalogItemBase] = Field(default_factory=list)
    addendum_items: list[CatalogItemBase] = Field(default_factory=list)
