"""Bentuk data tab Struktur Biaya (AHSP). Lihat docs/rencana-langkah-3-struktur-biaya.md.

Uang dan pengali memakai Decimal, bukan float, dan itu bukan kerapian semata: koefisien
"Jml Hari" di file asli pecahan (0,07 / 0,015 / 0,002), dan 4 x 1 x 0.07 x 50000 dalam
float menghasilkan 14000.000000000002. Uji penerimaan DR.05 menuntut 8.500.000 persis.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator

JenisJual = Literal["JASA", "MATERIAL"]
KelompokKomponen = Literal["BAHAN", "UPAH", "ALAT", "KONSUMABEL"]
KELOMPOK: tuple[str, ...] = ("BAHAN", "UPAH", "ALAT", "KONSUMABEL")

_Pengali = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=6)]


class AhspCreate(BaseModel):
    uraian: Annotated[str, Field(min_length=1, max_length=500)]
    satuan: Annotated[str, Field(min_length=1, max_length=50)]
    jenis_jual: JenisJual = "JASA"
    kategori: str = Field(default="", max_length=200)
    catatan: str = Field(default="", max_length=1000)
    parameter: dict[str, Any] = Field(default_factory=dict)

    @field_validator("uraian", "satuan", "kategori", "catatan", mode="before")
    @classmethod
    def rapikan(cls, v):
        return " ".join(str(v).split()) if v is not None else v


class AhspUpdate(BaseModel):
    """Semua opsional -- PATCH hanya mengubah yang dikirim."""

    uraian: str | None = Field(default=None, min_length=1, max_length=500)
    satuan: str | None = Field(default=None, min_length=1, max_length=50)
    jenis_jual: JenisJual | None = None
    kategori: str | None = Field(default=None, max_length=200)
    catatan: str | None = Field(default=None, max_length=1000)
    parameter: dict[str, Any] | None = None
    aktif: bool | None = None

    @field_validator("uraian", "satuan", "kategori", "catatan", mode="before")
    @classmethod
    def rapikan(cls, v):
        return " ".join(str(v).split()) if v is not None else v


class KomponenInput(BaseModel):
    """Satu baris rincian. Empat pengali dipisah supaya hasilnya bisa diperiksa manusia."""

    sumber_daya_id: int
    kelompok: KelompokKomponen
    qty: _Pengali = Decimal(1)
    shift: _Pengali = Decimal(1)
    jml_hari: _Pengali = Decimal(1)
    urutan: int = 0
    catatan: str = Field(default="", max_length=500)


class KomponenOut(BaseModel):
    id: int
    sumber_daya_id: int
    nama: str
    spesifikasi: str = ""
    satuan: str
    kelompok: str
    qty: Decimal
    shift: Decimal
    jml_hari: Decimal
    urutan: int
    catatan: str = ""
    # None berarti komponen ini belum punya baris harga sama sekali. JANGAN diganti 0 --
    # nol terbaca sebagai "gratis", padahal artinya "tidak diketahui" (aturan 3.1).
    harga_satuan: Decimal | None = None
    mata_uang: str | None = None
    jumlah: Decimal | None = None


class AhspOut(BaseModel):
    id: int
    uraian: str
    satuan: str
    jenis_jual: str
    # `kategori` teks apa adanya waktu baris ini dibuat; `kategori_id` kategori kanoniknya.
    # Keduanya disimpan dengan alasan yang sama seperti di katalog jasa: yang teks catatan
    # sejarah, yang id data kerja.
    kategori: str | None = None
    kategori_id: int | None = None
    catatan: str | None = None
    parameter: dict[str, Any] = Field(default_factory=dict)
    aktif: bool
    dibuat_pada: datetime
    diubah_pada: datetime
    n_komponen: int = 0
    n_tanpa_harga: int = 0
    lengkap: bool = False
    subtotal_total: Decimal | None = None


class HitungOut(BaseModel):
    subtotal: dict[str, Decimal]
    subtotal_total: Decimal
    # null selama `lengkap` false -- lihat aturan 3.1: AHSP yang separuh biayanya belum
    # berharga tidak boleh mengeluarkan angka yang terlihat seperti harga final.
    harga_jual: Decimal | None
    rumus_terpasang: bool
    lengkap: bool
    alasan: list[str]


class RingkasOut(BaseModel):
    total: int
    lengkap: int
    komponen_tanpa_harga: int
