from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

# Paste dari Excel bisa datang dalam format apa aja tergantung format sel/regional
# settings pengguna -- coba yang paling umum dipakai orang Indonesia, urutan dari
# yang paling ketat (ISO) ke yang paling longgar.
_DATE_FORMATS = ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y", "%d/%m/%Y", "%d-%m-%Y")


class MaterialItemCreate(BaseModel):
    """Satu baris material -- master (sumber_daya) + harga awal (sumber_daya_harga)."""

    kode: str | None = Field(default=None, max_length=100)
    nama: Annotated[str, Field(min_length=1, max_length=500)]
    spesifikasi: str = Field(default="", max_length=1000)
    satuan: Annotated[str, Field(min_length=1, max_length=50)]
    harga_satuan: float = Field(gt=0, description="Rupiah, harus lebih dari 0")
    supplier_nama: str = Field(default="", max_length=300)
    berlaku_dari: date | None = None
    sumber: str = Field(default="", max_length=100)
    no_dokumen: str = Field(default="", max_length=200)
    catatan: str = Field(default="", max_length=1000)

    @field_validator("nama", "satuan", mode="before")
    @classmethod
    def strip_required(cls, v):
        return str(v).strip() if v is not None else v

    @field_validator("berlaku_dari", mode="before")
    @classmethod
    def parse_flexible_date(cls, v):
        if v is None or v == "" or isinstance(v, date):
            return v or None
        s = str(v).strip()
        if not s:
            return None
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        raise ValueError(
            f"Format tanggal '{s}' tidak dikenali. Pakai YYYY-MM-DD, DD-MM-YYYY, "
            "DD/MM/YYYY, atau DD-Mon-YYYY (mis. 01-Jan-2026)."
        )

    @field_validator("kode", "spesifikasi", "supplier_nama", "sumber", "no_dokumen", "catatan", mode="before")
    @classmethod
    def strip_optional(cls, v):
        if v is None:
            return v
        return str(v).strip()


class BulkMaterialCreate(BaseModel):
    items: Annotated[list[MaterialItemCreate], Field(min_length=1)]


class MaterialRowUpdate(MaterialItemCreate):
    """Dipakai buat inline edit & edit massal -- selalu insert baris histori harga baru."""


class MaterialRowOut(BaseModel):
    id: int
    kode: str | None = None
    nama: str
    spesifikasi: str = ""
    satuan: str
    harga_satuan: float | None = None
    supplier_nama: str | None = None
    berlaku_dari: date | None = None


class MaterialStats(BaseModel):
    total_material: int
    total_supplier: int
    update_terakhir: date | None = None


class BulkDeleteMaterialRequest(BaseModel):
    ids: list[int] = Field(min_length=1)


class BulkUpdateMaterialItem(BaseModel):
    id: int
    data: MaterialRowUpdate


class BulkPatchMaterialRequest(BaseModel):
    updates: list[BulkUpdateMaterialItem] = Field(default_factory=list)
    delete_ids: list[int] = Field(default_factory=list)
