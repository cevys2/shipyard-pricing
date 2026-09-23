import io
import re
from collections import Counter
from typing import Any

import pandas as pd
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.config import settings
from app.database import (
    JENIS_KAPAL_SQL,
    KOLOM_CARI_KATALOG,
    NAMA_KAPAL_NORM_SQL,
    engine,
    kategori_id_sql,
)
from app.schemas.catalog import (
    BulkCatalogCreate,
    BulkPatchRequest,
    CatalogItemBase,
    CatalogRowOut,
    CatalogStats,
    TipePerjanjian,
)
from app.services import audit, pencarian

TABLE = settings.catalog_table

_COLUMNS = (
    "id, nama_perusahaan, nama_kapal, tipe_perjanjian, tahun, "
    "kategori_pekerjaan, uraian_pekerjaan, volume_satuan, harga_satuan, "
    "volume, satuan, induk_uraian, keterangan"
)

# Nilainya boleh ekspresi, bukan cuma nama kolom: `jenis` diturunkan dari nama kapal dan
# tidak punya kolom sendiri. Keduanya dipakai di dua tempat -- klausa WHERE di
# `_build_where()` dan SELECT DISTINCT di `filter_options()` -- dan ekspresi bekerja di
# kedua-duanya, jadi tidak perlu jalur khusus.
_FILTER_COLS = {
    "perusahaan": "nama_perusahaan",
    # Dinormalisasi spasinya, bukan `nama_kapal` mentah: `KMP. PRIMA  NUSANTARA` dan
    # `KMP. PRIMA NUSANTARA` itu satu kapal, dan tanpa ini dropdown-nya memuat keduanya
    # sehingga memilih salah satu menyembunyikan separuh barisnya. Baris yang ditampilkan
    # tetap membawa nama mentahnya -- yang dirapikan cuma cara menyaring dan mendaftar.
    "kapal": NAMA_KAPAL_NORM_SQL,
    "jenis": JENIS_KAPAL_SQL,
    "kategori": "kategori_pekerjaan",
    "tahun": "tahun",
    "tipe": "tipe_perjanjian",
}


def _build_where(
    *,
    perusahaan: str | None = None,
    kapal: str | None = None,
    jenis: str | None = None,
    kategori: str | None = None,
    tahun: str | None = None,
    tipe: str | None = None,
    search: str | None = None,
) -> tuple[str, dict[str, Any], pencarian.Pencarian | None]:
    clauses = []
    params: dict[str, Any] = {}
    filters = {
        "perusahaan": perusahaan,
        "kapal": kapal,
        "jenis": jenis,
        "kategori": kategori,
        "tahun": tahun,
        "tipe": tipe,
    }
    for key, val in filters.items():
        if val and val != "Semua":
            col = _FILTER_COLS[key]
            clauses.append(f"{col} = :{key}")
            params[key] = val
    # Kategori pekerjaan ikut dicari, bukan cuma uraiannya: orang mengetik "sandblasting"
    # tanpa tahu itu isi kolom kategori atau kolom uraian. Nama kapal & perusahaan sengaja
    # TIDAK ikut -- keduanya sudah punya dropdown sendiri, dan kalau ikut tercari maka
    # mengetik nama kapal akan menarik seluruh baris kapal itu dan menenggelamkan yang dicari.
    cari = pencarian.bangun(search, KOLOM_CARI_KATALOG)
    if cari:
        clauses.append(cari.kondisi)
        params.update(cari.params)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params, cari


def list_catalog(
    *,
    perusahaan: str | None = None,
    kapal: str | None = None,
    jenis: str | None = None,
    kategori: str | None = None,
    tahun: str | None = None,
    tipe: str | None = None,
    search: str | None = None,
) -> list[CatalogRowOut]:
    where, params, cari = _build_where(
        perusahaan=perusahaan,
        kapal=kapal,
        jenis=jenis,
        kategori=kategori,
        tahun=tahun,
        tipe=tipe,
        search=search,
    )
    urut = f"{cari.skor} DESC, nama_kapal, id" if cari else "nama_kapal, id"
    query = text(f"SELECT {_COLUMNS} FROM {TABLE} {where} ORDER BY {urut}")
    with engine.connect() as conn:
        rows = conn.execute(query, params).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        for col in ("nama_perusahaan", "nama_kapal", "tipe_perjanjian", "tahun", "kategori_pekerjaan", "uraian_pekerjaan"):
            if d.get(col) is None:
                d[col] = "-"
        out.append(CatalogRowOut(**d))
    return out


def catalog_stats(
    *,
    perusahaan: str | None = None,
    kapal: str | None = None,
    jenis: str | None = None,
    kategori: str | None = None,
    tahun: str | None = None,
    tipe: str | None = None,
    search: str | None = None,
) -> CatalogStats:
    where, params, _ = _build_where(
        perusahaan=perusahaan,
        kapal=kapal,
        jenis=jenis,
        kategori=kategori,
        tahun=tahun,
        tipe=tipe,
        search=search,
    )
    query = text(
        f"""
        SELECT COUNT(*) AS total_item,
               COUNT(DISTINCT nama_perusahaan) AS total_klien,
               -- Dinormalisasi, sama dengan dropdown Kapal. Kalau dihitung mentah, KPI
               -- bilang 14 kapal sementara dropdown di bawahnya mendaftar 13 -- selisih
               -- yang lahir dari spasi ganda dan mustahil ditebak dari layar.
               COUNT(DISTINCT {NAMA_KAPAL_NORM_SQL}) AS total_kapal,
               COUNT(DISTINCT tahun) AS total_tahun
        FROM {TABLE} {where}
        """
    )
    with engine.connect() as conn:
        row = conn.execute(query, params).mappings().first()
    if not row:
        return CatalogStats(total_item=0, total_klien=0, total_kapal=0, total_tahun=0)
    return CatalogStats(**dict(row))


def filter_options(
    *,
    perusahaan: str | None = None,
    kapal: str | None = None,
    jenis: str | None = None,
    kategori: str | None = None,
    tahun: str | None = None,
    tipe: str | None = None,
    search: str | None = None,
) -> dict[str, list[str]]:
    active = {
        "perusahaan": perusahaan,
        "kapal": kapal,
        "jenis": jenis,
        "kategori": kategori,
        "tahun": tahun,
        "tipe": tipe,
    }
    result: dict[str, list[str]] = {}
    with engine.connect() as conn:
        for key, col in _FILTER_COLS.items():
            others = {k: v for k, v in active.items() if k != key}
            where, params, _ = _build_where(**others, search=search)
            rows = conn.execute(
                text(f"SELECT DISTINCT {col} FROM {TABLE} {where} ORDER BY {col}"), params
            ).all()
            result[key] = ["Semua"] + [r[0] for r in rows if r[0]]
    return result


_INSERT_CHUNK = 500  # 500 x 13 kolom = 6.500 parameter; batas Postgres 65.535
_INSERT_COLS = (
    "id", "pt", "kpl", "tipe", "thn", "kat", "urai", "sat", "hrg",
    "vol", "satn", "induk", "ket",
)


def _insert_rows(conn: Connection, rows: list[dict[str, Any]]) -> None:
    """Kirim banyak baris dalam SATU perintah INSERT.

    Dulu satu perintah per baris, jadi 396 baris = 396 perjalanan ke Postgres. Waktu
    database masih beda benua itu berarti 220 detik; sekarang jauh lebih cepat, tapi
    penggabungan ini tetap berguna untuk berkas besar dan kalau suatu saat database
    dipindah lagi.

    `executemany` tidak dipakai walau terlihat seperti solusinya: pg8000 menjalankannya
    sebagai perulangan execute biasa dan SQLAlchemy tidak menulis ulang statement `text()`
    jadi multi-VALUES, sehingga jumlah perjalanannya tidak berubah sama sekali.

    Yang di-f-string HANYA nama placeholder; semua nilai tetap terikat sebagai parameter.
    """
    for start in range(0, len(rows), _INSERT_CHUNK):
        chunk = rows[start : start + _INSERT_CHUNK]
        placeholders, params = [], {}
        for i, r in enumerate(chunk):
            placeholders.append(
                "(" + ", ".join(f":{c}{i}" for c in _INSERT_COLS)
                + f", {kategori_id_sql(f':kat{i}')})"
            )
            for c in _INSERT_COLS:
                params[f"{c}{i}"] = r[c]
        conn.execute(
            text(
                f"""
                INSERT INTO {TABLE}
                (id, nama_perusahaan, nama_kapal, tipe_perjanjian, tahun,
                 kategori_pekerjaan, uraian_pekerjaan, volume_satuan, harga_satuan,
                 volume, satuan, induk_uraian, keterangan, kategori_id)
                VALUES {", ".join(placeholders)}
                """
            ),
            params,
        )


def _next_ids(conn: Connection, prefix: str, count: int) -> list[str]:
    """Nomor urut berikutnya untuk satu kapal+tahun, dihitung DI DALAM transaksi pemanggil.

    Kenapa memakai `conn` yang dioper, bukan membuka koneksi sendiri: begitu Induk dan
    Addendum disatukan dalam satu transaksi, baris Induk yang belum commit tidak akan
    terlihat oleh koneksi terpisah, sehingga penomoran Addendum mengulang dari 001 dan
    tabrakan primary key terjadi setiap kali -- bukan sesekali.

    Kunci penasihat menyerialkan penomoran per prefix. Tanpa ini, dua orang yang mengimpor
    kapal+tahun yang sama bersamaan sama-sama membaca nomor terakhir yang sama lalu
    menabrak. Kuncinya lepas sendiri saat transaksi selesai dan tidak butuh perubahan
    struktur tabel apa pun.

    `left(id, :plen) = :prefix` menggantikan `LIKE :prefix%` karena di LIKE karakter `_`
    berarti "satu karakter apa saja". Nama kapal di-slug dengan spasi menjadi `_`, jadi
    prefix `KMP._RHAMA_GIRI_NUSA-2025-` juga cocok dengan ID kapal lain yang hurufnya beda
    di posisi itu -- nomor urut satu kapal bisa melompat gara-gara baris kapal lain.
    """
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:p))"), {"p": prefix})
    existing = conn.execute(
        text(f"SELECT id FROM {TABLE} WHERE left(id, :plen) = :prefix"),
        {"plen": len(prefix), "prefix": prefix},
    ).all()
    last_num = 0
    for (id_,) in existing:
        try:
            n = int(str(id_).split("-")[-1])
            last_num = max(last_num, n)
        except ValueError:
            continue
    ids = []
    for _ in range(count):
        last_num += 1
        ids.append(f"{prefix}{last_num:03d}")
    return ids


def bulk_create(
    payload: BulkCatalogCreate,
    *,
    aktor: str,
    sumber: str = "form",
    conn: Connection | None = None,
) -> int:
    """Simpan sekumpulan baris katalog.

    `conn` opsional supaya pemanggil bisa menyatukan beberapa panggilan dalam SATU transaksi
    -- dipakai impor docking yang menyimpan Induk dan Addendum sekaligus. Kalau Induk commit
    sendiri lalu Addendum gagal, separuh data masuk tanpa pengguna punya cara tahu; itu yang
    terjadi di produksi 31 Juli 2026.

    Kalau `conn` tidak diberikan, fungsi ini membuka transaksinya sendiri seperti sebelumnya,
    jadi `/catalog/bulk` dan `/catalog/import` tidak perlu ikut berubah.
    """
    if conn is None:
        with engine.begin() as c:
            return _bulk_create(c, payload, aktor=aktor, sumber=sumber)
    return _bulk_create(conn, payload, aktor=aktor, sumber=sumber)


def _bulk_create(
    conn: Connection, payload: BulkCatalogCreate, *, aktor: str, sumber: str
) -> int:
    slug = payload.nama_kapal.strip().replace(" ", "_").upper()
    prefix = f"{slug}-{payload.tahun.strip()}-"

    pt = payload.nama_perusahaan.upper() if payload.nama_perusahaan else ""
    kpl = payload.nama_kapal.upper()
    tipe = payload.tipe_perjanjian.value

    # Penomoran ikut transaksi ini supaya baris yang belum commit tetap terhitung, dan
    # supaya kunci penasihatnya lepas bersamaan dengan commit.
    ids = _next_ids(conn, prefix, len(payload.items))
    _insert_rows(
        conn,
        [
            {
                "id": new_id,
                "pt": pt,
                "kpl": kpl,
                "tipe": tipe,
                "thn": payload.tahun,
                "kat": item.kategori_pekerjaan or "-",
                "urai": item.uraian_pekerjaan,
                "sat": item.volume_satuan or "-",
                "hrg": float(item.harga_satuan),
                "vol": item.volume,
                "satn": item.satuan,
                "induk": item.induk_uraian,
                "ket": item.keterangan,
            }
            for new_id, item in zip(ids, payload.items, strict=True)
        ],
    )
    audit.catat(
        conn,
        aktor=aktor,
        aksi="create",
        entitas="katalog_harga",
        jumlah=len(payload.items),
        detail={
            "nama_kapal": kpl,
            "tahun": payload.tahun,
            "tipe_perjanjian": tipe,
            "sumber": sumber,
            "id_range": [ids[0], ids[-1]] if ids else [],
        },
    )
    return len(payload.items)


def bulk_patch(body: BulkPatchRequest, *, aktor: str) -> dict[str, int]:
    deleted = 0
    updated = 0
    with engine.begin() as conn:
        if body.delete_ids:
            del_q = text(f"DELETE FROM {TABLE} WHERE id = :id")
            for del_id in body.delete_ids:
                conn.execute(del_q, {"id": del_id})
            deleted = len(body.delete_ids)
            audit.catat(
                conn,
                aktor=aktor,
                aksi="delete",
                entitas="katalog_harga",
                jumlah=deleted,
                detail={"ids": body.delete_ids[:50]},
            )

        if body.updates:
            # `volume`, `satuan`, `induk_uraian`, dan `keterangan` SENGAJA tidak ikut
            # di-UPDATE. Layar edit katalog cuma mengirim delapan kolom lama, jadi kalau
            # keempatnya ikut di sini, menyunting satu sel apa pun akan menimpanya jadi
            # NULL -- data provenance impor hilang tanpa jejak, persis kelas kegagalan
            # yang paling mahal karena tidak bersuara. Kalau suatu saat keempatnya perlu
            # bisa disunting, kirimkan nilainya dari layar dulu, jangan tambahkan di sini.
            upd_q = text(
                f"""
                UPDATE {TABLE}
                SET nama_perusahaan = :pt, nama_kapal = :kpl, tipe_perjanjian = :tipe, tahun = :thn,
                    kategori_pekerjaan = :kat, uraian_pekerjaan = :urai,
                    volume_satuan = :sat, harga_satuan = :hrg,
                    -- Teks kategori bisa berubah di sini; kategori_id ikut, kecuali koreksi manual.
                    kategori_id = CASE WHEN kategori_sumber = 'alias'
                                       THEN {kategori_id_sql(":kat")} ELSE kategori_id END
                WHERE id = :id
                """
            )
            for u in body.updates:
                d = u.data
                conn.execute(
                    upd_q,
                    {
                        "pt": d.nama_perusahaan,
                        "kpl": d.nama_kapal,
                        "tipe": d.tipe_perjanjian.value,
                        "thn": d.tahun,
                        "kat": d.kategori_pekerjaan,
                        "urai": d.uraian_pekerjaan,
                        "sat": d.volume_satuan,
                        "hrg": d.harga_satuan,
                        "id": u.id,
                    },
                )
            updated = len(body.updates)
            audit.catat(
                conn,
                aktor=aktor,
                aksi="update",
                entitas="katalog_harga",
                jumlah=updated,
                detail={"ids": [u.id for u in body.updates][:50]},
            )
    return {"deleted": deleted, "updated": updated}


_HEADER_WAJIB_TUNGGAL = ("nama_kapal", "tahun")
_HEADER_SEBUTAN = {
    "nama_kapal": "kapal",
    "tahun": "tahun",
    "nama_perusahaan": "perusahaan",
    "tipe_perjanjian": "tipe perjanjian",
}


def _nilai_unik(kolom) -> list[str]:
    """Nilai berbeda di satu kolom header, urut kemunculan pertama.

    Yang pertama tetap yang dipakai kalau kolomnya seragam, jadi berkas yang selama ini
    benar tidak berubah perilakunya sama sekali.

    Pembulatan float-nya bukan kosmetik: kolom angka yang punya SATU sel kosong saja
    (baris total, baris pemisah) dibaca pandas sebagai float64, jadi str(2026.0) ->
    "2026.0". Tahun ikut membentuk prefix ID baris (lihat _bulk_create), jadi ".0" itu
    menempel permanen di primary key dan memecah filter "Tahun" jadi dua nilai. Format
    sel di Excel tidak menolong -- ini inferensi tipe di pandas. np.float64 turunan float
    bawaan, jadi isinstance() di bawah ikut menangkapnya. Tanpa pembulatan ini, 2026 dan
    2026.0 di satu kolom juga akan terhitung sebagai dua tahun berbeda dan berkas yang
    sah ikut tertolak palang di atas.
    """
    urut: list[str] = []
    for val in kolom.dropna():
        if isinstance(val, float) and float(val).is_integer():
            val = int(val)
        teks = str(val).strip()
        if teks and teks not in urut:
            urut.append(teks)
    return urut


def _teks_kunci(v: object) -> str:
    """Bentuk teks untuk membandingkan dua baris dari impor yang berbeda.

    Spasi dirapikan (impor lama menyimpan newline di tengah teks) dan awalan "- " dibuang
    (penanganan pengisi tata letak di parser berubah 1 September 2026). Tanpa keduanya,
    berkas yang sama yang diimpor sebelum dan sesudah perbaikan parser terlihat berbeda.
    """
    if v is None:
        return ""
    return re.sub(r"\s+", " ", str(v)).strip().upper().lstrip("- ").strip()


def peringatan_impor_ganda(
    nama_kapal: str, item: list[tuple[str | None, float | None, float | None]]
) -> list[str]:
    """Peringatan kalau isi berkas ini sudah ada di katalog -- berkas yang masuk dua kali.

    Ini bukan hipotesis. Per 22 September 2026 produksi memuat berkas MISHIMA sebanyak
    TIGA kali (591 baris, seharusnya 197) dan MUNIC 1 EMPAT kali (716, seharusnya 179).
    Nilai MISHIMA terbaca Rp 3,5 miliar padahal sebenarnya Rp 1,3 miliar. Tidak ada satu
    pun tanda di layar; nama kapalnya sama, jadi di dropdown dia tetap satu kapal.

    Kenapa mencocokkan ISI, bukan nama berkas: berkas yang sama bisa diganti namanya, dan
    impor MISHIMA yang pertama masuk sebagai "MISHIMA" lalu yang berikutnya sebagai
    "KMP. MISHIMA" -- nama kapalnya pun berubah. Yang tidak berubah cuma isinya.

    Kenapa memperingatkan, bukan menolak: impor ulang yang DISENGAJA itu sah, misalnya
    waktu parser diperbaiki dan berkas lama perlu dibaca ulang. Yang tidak boleh terjadi
    adalah impor ulang yang tidak disadari. Palang yang menolak akan menghalangi
    perbaikan; palang yang memberi tahu tidak.

    Sengaja tidak menyebut kapan impor lamanya terjadi, walau `created_at` ada di
    produksi: kolom itu bukan buatan repo ini (`tabel_katalog_harga` dibuat di luar),
    jadi query yang bergantung padanya gagal di database mana pun yang tidak
    kebetulan punya. Tahun dan jumlah baris sudah cukup untuk mengenali berkasnya.

    Ambangnya 30%: baris Addendum yang sah nyaris tidak beririsan dengan Induk (diukur di
    13 kapal berbatch ganda: irisannya 0-11%), jadi di bawah itu peringatannya cuma bunyi
    palsu -- dan palang yang berbunyi palsu akan diabaikan, lalu berhenti menjaga apa pun.
    """
    bersih = [(_teks_kunci(u), h, v) for u, h, v in item if u]
    if not bersih:
        return []

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT uraian_pekerjaan, harga_satuan, volume, tahun
                FROM   {TABLE}
                WHERE  {NAMA_KAPAL_NORM_SQL} = :kapal
                """
            ),
            {"kapal": " ".join(str(nama_kapal).split()).strip()},
        ).mappings().all()
    if not rows:
        return []

    ada = Counter(
        (_teks_kunci(r["uraian_pekerjaan"]), r["harga_satuan"], r["volume"]) for r in rows
    )
    cocok = sum((Counter(bersih) & ada).values())
    if cocok / len(bersih) < 0.30:
        return []

    tahun = sorted({r["tahun"] for r in rows if r["tahun"]})
    return [
        f"BERKAS INI SEPERTINYA SUDAH PERNAH DIIMPOR. {cocok} dari {len(bersih)} baris "
        f"({cocok / len(bersih) * 100:.0f}%) isinya sudah ada di katalog untuk kapal ini "
        f"(tahun {', '.join(tahun)}; {len(rows)} baris tersimpan). Kalau ini impor ulang "
        f"yang disengaja, hapus dulu baris lamanya -- kalau tidak, nilainya terhitung dua kali."
    ]


def parse_spreadsheet(file_bytes: bytes, filename: str) -> tuple[BulkCatalogCreate | None, list[str]]:
    """
    Otomatis: upload Excel/CSV → Pydantic validasi per baris.
    Format kolom: Kategori | Uraian | Satuan | Harga (+ sheet/header opsional untuk kapal/tahun).
    """
    errors: list[str] = []
    name = filename.lower()

    if name.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(file_bytes))
    elif name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(file_bytes))
    else:
        return None, ["File harus .csv, .xlsx, atau .xls"]

    df.columns = [str(c).strip() for c in df.columns]

    col_map = {
        "kategori_pekerjaan": ["kategori", "kategori pekerjaan", "kategori_pekerjaan"],
        "uraian_pekerjaan": ["uraian", "uraian pekerjaan", "uraian_pekerjaan"],
        "volume_satuan": ["satuan", "volume", "volume_satuan", "satuan (volume)"],
        "harga_satuan": ["harga", "harga satuan", "harga_satuan"],
        # Empat kolom baru. Sebutannya sengaja TIDAK memakai "volume" dan "satuan" polos:
        # keduanya sudah dipetakan ke `volume_satuan` di atas, dan mengubah itu akan
        # memindahkan isi berkas yang selama ini sudah benar ke kolom lain.
        "volume": ["vol", "vol."],
        "satuan": ["sat", "sat."],
        "induk_uraian": ["induk", "induk uraian", "induk_uraian", "uraian induk"],
        "keterangan": ["ket", "keterangan"],
    }

    def find_col(keys: list[str]) -> str | None:
        lower = {c.lower(): c for c in df.columns}
        for k in keys:
            if k in lower:
                return lower[k]
        return None

    mapped = {}
    for field, keys in col_map.items():
        col = find_col(keys)
        if col:
            mapped[field] = col

    if "uraian_pekerjaan" not in mapped:
        return None, ["Kolom 'Uraian Pekerjaan' tidak ditemukan di file"]

    header_cols = {
        "nama_kapal": ["nama kapal", "kapal", "nama_kapal"],
        "tahun": ["tahun"],
        "nama_perusahaan": ["perusahaan", "klien", "nama perusahaan", "nama_perusahaan"],
        "tipe_perjanjian": ["tipe", "tipe perjanjian", "tipe_perjanjian"],
    }

    header: dict[str, str] = {}
    for field, keys in header_cols.items():
        col = find_col(keys)
        if not col:
            continue
        nilai = _nilai_unik(df[col])
        if not nilai:
            continue
        if len(nilai) > 1:
            # Satu berkas = satu kapal + satu tahun. Sebelum palang ini, berkas berisi
            # tiga kapal tetap diproses: SELURUH barisnya tercatat atas nama kapal yang
            # kebetulan muncul paling atas, tanpa peringatan apa pun. Salahnya permanen
            # -- kapal dan tahun ikut membentuk prefix ID baris -- dan baru ketahuan
            # berbulan-bulan kemudian waktu ada yang membandingkan harga antar kapal.
            if field in _HEADER_WAJIB_TUNGGAL:
                contoh = ", ".join(nilai[:5]) + (", ..." if len(nilai) > 5 else "")
                return None, [
                    f"Berkas ini memuat {len(nilai)} {_HEADER_SEBUTAN[field]} ({contoh}). "
                    f"Satu berkas cuma boleh satu kapal dan satu tahun -- isi kolom "
                    f"'{col}' harus sama di setiap baris. Pisahkan berkasnya dulu."
                ]
            # Perusahaan dan tipe tidak menolak berkasnya: keduanya tidak ikut ke prefix
            # ID, jadi salahnya masih bisa diperbaiki lewat layar edit. Tapi tetap
            # dikatakan terang-terangan, bukan dipilih diam-diam seperti dulu.
            errors.append(
                f"Kolom '{col}' punya {len(nilai)} nilai berbeda ({', '.join(nilai[:5])}); "
                f"seluruh berkas disimpan memakai '{nilai[0]}'."
            )
        header[field] = nilai[0]

    items: list[CatalogItemBase] = []
    for idx, row in df.iterrows():
        raw = {}
        for field, col in mapped.items():
            val = row[col]
            if pd.isna(val):
                val = "-" if field != "harga_satuan" else 0
            raw[field] = val
        if str(raw.get("uraian_pekerjaan", "")).strip() in ("", "-", "nan"):
            continue
        try:
            items.append(CatalogItemBase(**raw))
        except ValidationError as e:
            errors.append(f"Baris {int(idx) + 2}: {e.errors()[0]['msg']}")

    if not items:
        return None, errors or ["Tidak ada baris valid di file"]

    if "nama_kapal" not in header or "tahun" not in header:
        return None, [
            "Tambahkan kolom 'Nama Kapal' dan 'Tahun' di Excel (isi sama di setiap baris), "
            "atau gunakan form JSON bulk di API."
        ]

    tipe = header.get("tipe_perjanjian", "Induk")
    try:
        tipe_enum = TipePerjanjian(tipe) if tipe in ("Induk", "Addendum") else TipePerjanjian.induk
    except ValueError:
        tipe_enum = TipePerjanjian.induk

    try:
        bulk = BulkCatalogCreate(
            nama_perusahaan=header.get("nama_perusahaan", ""),
            nama_kapal=header["nama_kapal"],
            tahun=header["tahun"],
            tipe_perjanjian=tipe_enum,
            items=items,
        )
    except ValidationError as e:
        return None, [f"Header invalid: {e.errors()[0]['msg']}"]

    return bulk, errors
