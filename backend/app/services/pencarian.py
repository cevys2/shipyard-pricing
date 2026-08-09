"""Pencarian teks yang toleran: urutan kata bebas, salah ketik dimaafkan, hasil diperingkat.

Sebelumnya pencarian cuma `kolom ILIKE '%kata kunci%'` -- satu potongan utuh. Akibatnya
mengetik "plat 10mm baja" mengembalikan nol baris padahal "Plat Baja 10 mm" ada di tabel,
dan orang menyimpulkan datanya belum diinput. Itu kegagalan yang paling mahal di sini:
diam-diam salah, bukan kelihatan salah.

Sekarang kata kunci dipecah jadi kata, dan SEMUA kata harus cocok (AND) -- tapi masing-masing
boleh cocok lewat cara yang berbeda, dari yang paling yakin ke yang paling longgar:

  1. substring biasa    "plat"   ~ "Plat Baja 10 mm"
  2. bentuk rapat       "m10x50" ~ "M 10 x 50"      (semua non-alfanumerik dibuang dulu)
  3. kemiripan trigram  "gaskit" ~ "Gasket"          (butuh ekstensi pg_trgm)

Cara ke-3 mati sendiri kalau pg_trgm tidak terpasang -- lihat `set_trgm()`. Jadi kalau
`CREATE EXTENSION` ditolak di server produksi, pencarian tetap jalan dengan cara 1 dan 2,
bukan meledak 500.

Tiap cara punya bobot berbeda supaya hasilnya bisa diurutkan: yang cocok persis naik ke
atas, yang cuma mirip turun ke bawah. Tanpa peringkat, "flexible" malah bikin hasil yang
tepat tenggelam di antara yang sekadar mirip.
"""

import re
from dataclasses import dataclass
from typing import Any, Sequence

# Kata yang lebih pendek dari ini tidak diikutkan ke pencocokan trigram. Trigram sebuah kata
# 3 huruf cuma 5 buah, jadi skornya sangat berisik -- "aki" jadi mirip dengan "akhir",
# "kaki", "aku". Kata pendek tetap dicari, tapi wajib cocok persis sebagai substring.
_MIN_FUZZY = 4

# Ambang kemiripan trigram. 0.45 kira-kira memaafkan satu-dua huruf salah pada kata 6-10
# huruf. Dinaikkan -> typo tidak ketemu; diturunkan -> hasilnya mulai ngawur.
# Publik karena database.py memakainya untuk menyetel pg_trgm.word_similarity_threshold --
# nilainya harus sama persis di dua tempat itu, jadi cuma boleh ada satu sumbernya.
AMBANG = 0.45

# Batas jumlah kata yang diproses. Tiap kata menambah 3 kondisi OR + 3 parameter ke query,
# jadi tanpa batas ini seseorang bisa menempelkan satu paragraf ke kotak cari dan bikin
# query raksasa. 8 kata jauh di atas kebiasaan pemakaian nyata.
_MAKS_KATA = 8

# Angka desimal ditahan supaya "1.5" tidak pecah jadi "1" dan "5" -- "1" akan cocok dengan
# hampir semua baris dan bikin filter AND-nya tidak ada gunanya.
_POLA_KATA = re.compile(r"[a-z0-9]+(?:[.,][a-z0-9]+)*")

# Operator kemiripan-kata pg_trgm, ditulis dengan `%` GANDA dengan sengaja.
#
# pg8000 memakai paramstyle "format", jadi satu `%` di dalam teks SQL dibacanya sebagai awal
# penanda parameter, dan SQLAlchemy tidak menggandakannya sendiri di jalur `text()` ini --
# sudah dicoba, hasilnya InterfaceError "Only %s and %% are supported in the query". pg8000
# yang mengubah `%%` jadi `%` sebelum dikirim ke Postgres.
#
# Kalau driver-nya suatu saat pindah dari pg8000, baris ini harus diperiksa ulang.
_OP_MIRIP = "<%%"

_trgm_siap = False


def set_trgm(aktif: bool) -> None:
    """Dipanggil sekali saat start dari `ensure_pencarian_index()`."""
    global _trgm_siap
    _trgm_siap = aktif


def trgm_siap() -> bool:
    return _trgm_siap


def jerami_sql(kolom: Sequence[str]) -> str:
    """Semua kolom yang dicari, digabung jadi satu teks huruf kecil.

    Dipakai bareng oleh query DAN oleh definisi index di `database.py`. Definisinya HARUS
    satu tempat: index ekspresi baru kepakai kalau ekspresinya sama persis dengan yang di
    query -- kalau beda sedikit saja, index-nya terpasang tapi tidak pernah tersentuh.
    """
    return "lower(" + " || ' ' || ".join(f"coalesce({k}, '')" for k in kolom) + ")"


def rapat_sql(kolom: Sequence[str]) -> str:
    """Bentuk rapat: semua selain huruf & angka dibuang.

    Ini yang bikin "M10x50" ketemu "M 10 x 50" dan "SKF-6205" ketemu "SKF 6205". Part
    number ditulis dengan spasi/strip yang berbeda-beda antar dokumen sumber, dan itu
    perbedaan penulisan, bukan perbedaan barang.
    """
    return f"regexp_replace({jerami_sql(kolom)}, '[^a-z0-9]+', '', 'g')"


def pecah(q: str | None) -> list[str]:
    """Kata kunci -> daftar kata unik, urutan pertama dipertahankan."""
    if not q:
        return []
    kata = _POLA_KATA.findall(q.lower())
    hasil: list[str] = []
    for k in kata:
        if len(k) >= 2 and k not in hasil:
            hasil.append(k)
    # Kalau yang tersisa cuma huruf tunggal (mis. orang mencari "A"), pakai apa adanya
    # daripada mengembalikan "cari apa saja".
    if not hasil and kata:
        hasil = kata[:1]
    return hasil[:_MAKS_KATA]


def _esc(t: str) -> str:
    """Bikin `%` dan `_` yang diketik orang jadi huruf biasa, bukan wildcard.

    Backslash adalah karakter escape bawaan LIKE di PostgreSQL, jadi tidak perlu klausa
    `ESCAPE` terpisah. Dengan tokenisasi sekarang seharusnya tidak ada wildcard yang lolos
    ke sini sama sekali -- ini jaring pengaman kalau `_POLA_KATA` nanti dilonggarkan.
    """
    return t.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@dataclass(frozen=True)
class Pencarian:
    kondisi: str  # ekspresi boolean SQL
    skor: str  # ekspresi real SQL, makin besar makin relevan
    params: dict[str, Any]


def bangun(q: str | None, kolom: Sequence[str], *, prefix: str = "cari") -> Pencarian | None:
    """Rakit kondisi + ekspresi peringkat untuk satu kotak pencarian.

    `kolom` boleh pakai alias tabel ("sd.nama"); `prefix` cuma untuk memisahkan nama
    parameter kalau nanti ada dua pencarian dalam satu query.
    Mengembalikan None kalau kata kuncinya kosong -- pemanggil tidak menambah klausa apa pun.
    """
    kata = pecah(q)
    if not kata:
        return None

    jerami, rapat = jerami_sql(kolom), rapat_sql(kolom)
    kondisi: list[str] = []
    skor: list[str] = []
    params: dict[str, Any] = {}

    for i, k in enumerate(kata):
        p_sub, p_rapat, p_kata = f"{prefix}{i}s", f"{prefix}{i}r", f"{prefix}{i}k"
        params[p_sub] = f"%{_esc(k)}%"
        params[p_rapat] = "%" + _esc(re.sub(r"[^a-z0-9]", "", k)) + "%"

        cocok = [
            f"{jerami} LIKE :{p_sub}",
            f"{rapat} LIKE :{p_rapat}",
        ]
        nilai = [
            f"CASE WHEN {jerami} LIKE :{p_sub} THEN 1.0 ELSE 0.0 END::real",
            f"CASE WHEN {rapat} LIKE :{p_rapat} THEN 0.8 ELSE 0.0 END::real",
        ]
        if _trgm_siap and len(k) >= _MIN_FUZZY:
            params[p_kata] = k
            # CAST eksplisit: pg8000 mengirim parameter tanpa tipe, dan pola yang sama
            # sudah pernah bikin query lain gagal di file ini (lihat _LATERAL_HARGA).
            kata_sql = f"CAST(:{p_kata} AS TEXT)"
            mirip = f"word_similarity({kata_sql}, {jerami})"
            # Operator `<%`, bukan `word_similarity(...) >= AMBANG`. Keduanya berarti sama,
            # tapi hanya `<%` yang dikenali index GIN gin_trgm_ops. Dengan panggilan fungsi
            # biasa, cabang ini memaksa pindai seluruh tabel -- dan karena ketiga cabangnya
            # di-OR, itu bikin index untuk dua cabang lainnya ikut tidak terpakai. Sudah
            # dibuktikan lewat EXPLAIN, bukan diperkirakan.
            #
            # `<%` memakai ambang dari pg_trgm.word_similarity_threshold, yang di-set per
            # koneksi di database.py. Pembanding eksplisitnya tetap di-AND supaya kalau SET
            # itu gagal, ambangnya jatuh ke bawaan 0.6 -- lebih ketat, jadi paling banter
            # typo berat tidak ketemu. Tidak pernah jadi lebih longgar dari yang dimaksud.
            cocok.append(f"({kata_sql} {_OP_MIRIP} {jerami} AND {mirip} >= {AMBANG})")
            nilai.append(f"({mirip} * 0.7)::real")

        kondisi.append("(" + " OR ".join(cocok) + ")")
        skor.append("GREATEST(" + ", ".join(nilai) + ")")

    # Bonus kalau kata kuncinya muncul utuh berurutan. Tanpa ini, mengetik nama lengkap
    # sebuah barang menaruhnya sederajat dengan baris lain yang kebetulan punya semua
    # katanya secara terpisah.
    p_frasa = f"{prefix}_frasa"
    params[p_frasa] = f"%{_esc(' '.join(kata))}%"
    skor.append(f"CASE WHEN {jerami} LIKE :{p_frasa} THEN 1.5 ELSE 0.0 END::real")

    return Pencarian(
        kondisi="(" + " AND ".join(kondisi) + ")",
        skor=" + ".join(skor),
        params=params,
    )
