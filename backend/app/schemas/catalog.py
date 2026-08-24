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
    # Empat kolom nullable, semuanya boleh kosong. `volume_satuan` di atas TIDAK diganti
    # olehnya -- yang lama tetap menyimpan apa yang tertulis di berkas, yang baru
    # menyimpan angkanya supaya bisa dihitung. Lihat ensure_katalog_kolom_rincian().
    volume: float | None = Field(default=None, ge=0)
    satuan: str | None = Field(default=None, max_length=100)
    induk_uraian: str | None = Field(default=None, max_length=2000)
    keterangan: str | None = Field(default=None, max_length=2000)

    @field_validator("satuan", "induk_uraian", "keterangan", mode="before")
    @classmethod
    def kosong_jadi_none(cls, v):
        """Teks kosong dan "-" disimpan sebagai NULL, bukan sebagai string.

        Kalau tidak, kolomnya punya dua cara mengatakan "tidak tahu" -- NULL dan "-" --
        dan tiap query harus menangani keduanya. Yang lama (`volume_satuan`) memang sudah
        memakai "-", tapi itu tidak jadi alasan menularkannya ke kolom baru.
        """
        if v is None:
            return None
        t = str(v).strip()
        return t if t and t != "-" else None

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
    volume: float | None = None
    satuan: str | None = None
    induk_uraian: str | None = None
    keterangan: str | None = None


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
    # Qty dan Sat dari berkas, terpisah. `volume_satuan` di atas isinya satuan saja dan
    # tetap dipertahankan apa adanya supaya jalur lama tidak berubah artinya.
    volume: float | None = None
    satuan: str | None = None


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


class RepairListParsedItem(BaseModel):
    """Satu baris berharga hasil baca repair list, sebelum manusia memeriksanya."""

    row: int
    kategori: str | None = None
    induk_uraian: str | None = None
    uraian: str
    volume: float | None = None
    satuan: str | None = None
    harga: float = 0
    # Nilai kolom TOTAL apa adanya di berkas. Tidak ikut disimpan ke katalog -- adanya di
    # sini supaya layar pratinjau bisa menunjukkan kalau VOL x harga tidak sama dengan
    # TOTAL yang tertulis, alih-alih diam-diam memilih salah satunya.
    total_berkas: float | None = None
    keterangan: str = ""


class RepairListRekonsiliasi(BaseModel):
    """Palang verifikasi impor: yang terbaca vs yang tertulis di dokumen.

    Kalau `selisih` bukan nol, ada baris yang tidak terbaca atau terbaca dua kali. Ini
    satu-satunya cara aplikasi tahu impornya utuh tanpa orang menghitung manual di luar.
    """

    jumlah_dokumen: float | None = None
    ppn_dokumen: float | None = None
    total_dokumen: float | None = None
    jumlah_terbaca: float = 0
    selisih: float | None = None
    cocok: bool = False


class RepairListPreview(BaseModel):
    sheet_name: str
    detected_nama_kapal: str = ""
    detected_nama_perusahaan: str = ""
    # Selalu kosong: repair list tidak memuat tahun di mana pun, dan menebaknya dari nama
    # berkas sudah terbukti salah di jalur docking -- itu tahun terbit dokumen, bukan
    # tahun pekerjaannya. Diisi manusia di layar pratinjau.
    detected_tahun: str = ""
    detected_jenis_dokumen: str = ""
    detected_judul: str = ""
    items: list[RepairListParsedItem]
    rekonsiliasi: RepairListRekonsiliasi
    warnings: list[str]


class RepairListCommit(BaseModel):
    nama_perusahaan: str = ""
    nama_kapal: Annotated[str, Field(min_length=1, max_length=200)]
    tahun: Annotated[str, Field(min_length=1, max_length=20)]
    items: list[CatalogItemBase] = Field(min_length=1)
