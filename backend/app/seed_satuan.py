"""Satuan baku + ejaan-ejaannya, dipakai layar Harga Wajar.

Kolom `volume_satuan` di `tabel_katalog_harga` merekam satuan apa adanya dari berkas, jadi
satu satuan nyata punya beberapa ejaan: `m²`/`m2`, `mtr`/`m`/`mter`, `pcs`/`pc`/`buah`/`bh`.
Tanpa pemetaan ini, layar yang menjawab "harga per m² wajarnya berapa" membelah satu
kelompok jadi dua yang masing-masing separuh -- dan tidak ada yang kelihatan salah.

Pemetaannya disetujui 22 Oktober 2026, berangkat dari daftar ejaan di CLAUDE.md. Yang
sengaja TIDAK dipetakan:

- `m'` (5 baris per 22 September 2026). Bisa meter lari, bisa juga salah ketik m². Salah
  gabung lebih berbahaya daripada dibiarkan terpisah, jadi dia tetap kelompok sendiri
  sampai ada yang memastikan artinya.
- Ejaan apa pun yang belum pernah diperiksa. Satuan yang tidak ada di sini TIDAK dibuang:
  dia tampil dengan ejaannya sendiri dan ditandai belum diperiksa, supaya daftar ini bisa
  dilengkapi dari apa yang benar-benar ada di produksi.

Alias ditulis dalam bentuk hasil `database.satuan_norm_sql()` -- huruf kecil, tanpa spasi
di tepi, tanpa titik di ujung. Kalau ditulis dalam bentuk lain, resolver diam-diam tidak
menemukan pasangannya; `tests/test_satuan.py` menjaga itu.

Data Python, bukan berkas .sql, dengan alasan yang sama seperti `seed_kategori.py`.
"""

# Nama baku -> ejaan yang digabung ke sana. Nama baku sendiri juga harus ada di daftarnya.
PETA: dict[str, tuple[str, ...]] = {
    "m²": ("m²", "m2"),
    "m": ("m", "mtr", "mter"),
    "pcs": ("pcs", "pc", "buah", "bh"),
    "tangki": ("tangki", "tanki"),
    "liter": ("liter", "ltr"),
    "segel": ("segel", "shackle"),
    "Hari": ("hari",),
    "Kali": ("kali",),
    "Ls": ("ls", "lumpsum", "lump sum"),
    "Lot": ("lot",),
    "Paket": ("paket",),
}

# Harga borongan tetap ditampilkan, tapi ditandai: satu "Ls" di kapal kecil dan di kapal
# besar bisa berarti lingkup kerja yang jauh berbeda, jadi membandingkannya perlu hati-hati.
BORONGAN = frozenset({"Ls", "Lot", "Paket"})


def baris_satuan() -> list[dict[str, object]]:
    """Satuan baku beserta tanda borongannya, siap dipakai executemany."""
    return [{"nama": nama, "borongan": nama in BORONGAN} for nama in PETA]


def baris_alias() -> list[dict[str, str]]:
    """Pasangan (alias, nama satuan baku), siap dipakai executemany."""
    return [{"alias": alias, "nama": nama} for nama, daftar in PETA.items() for alias in daftar]
