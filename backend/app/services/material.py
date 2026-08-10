from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.database import KOLOM_CARI_MATERIAL, engine, sd_identitas_sql, urutan_harga_sql
from app.schemas.material import (
    JENIS_SUMBER_DAYA,
    BulkMaterialCreate,
    BulkPatchMaterialRequest,
    MaterialItemCreate,
    MaterialRowOut,
    MaterialStats,
    PriceHistoryRow,
    PriceCreate,
)
from app.services import audit, pencarian

# Nama kolom dengan alias tabelnya, sesuai bentuk yang dipakai query di file ini.
_KOLOM_CARI = tuple(f"sd.{k}" for k in KOLOM_CARI_MATERIAL)

# Kapal, supplier, dan tahun itu sifat PEMBELIAN, bukan sifat materialnya -- satu material
# bisa dibeli untuk beberapa kapal dari beberapa supplier di beberapa tahun. Dulu ketiganya
# disaring lewat v_harga_terkini (harga TERAKHIR saja), jadi material yang pernah dibeli
# untuk kapal A tapi harga terakhirnya dari kapal B hilang begitu difilter kapal A --
# angkanya salah tanpa memberi tanda apa pun.
#
# Sekarang: penyaringan melihat SELURUH riwayat harga, dan baris harga yang ditampilkan
# adalah yang terbaru DI ANTARA yang lolos filter. Jadi memfilter kapal A menampilkan harga
# kapal A, bukan harga kapal B.
#
# CAST eksplisit dipakai karena pg8000 tidak bisa menyimpulkan tipe parameter yang hanya
# muncul di dalam "IS NULL".
_LATERAL_HARGA = f"""
    LEFT JOIN LATERAL (
        SELECT h.id, h.harga_satuan, h.mata_uang, h.nama_kapal, h.tahun_pembelian,
               h.berlaku_dari, sup.nama AS supplier_nama
        FROM   sumber_daya_harga h
        LEFT   JOIN supplier sup ON sup.id = h.supplier_id
        WHERE  h.sumber_daya_id = sd.id
          AND  (CAST(:kapal    AS TEXT) IS NULL OR h.nama_kapal      = :kapal)
          AND  (CAST(:supplier AS TEXT) IS NULL OR sup.nama          = :supplier)
          AND  (CAST(:tahun    AS INT)  IS NULL OR h.tahun_pembelian = :tahun)
        ORDER  BY {urutan_harga_sql("h")}
        LIMIT  1
    ) h ON TRUE
"""

_LIST_QUERY = f"""
    SELECT sd.id, sd.nama, sd.spesifikasi, sd.satuan,
           h.harga_satuan, h.mata_uang, h.nama_kapal, h.tahun_pembelian, h.berlaku_dari,
           h.supplier_nama
    FROM   sumber_daya sd
    {_LATERAL_HARGA}
    WHERE  sd.jenis = :jenis AND sd.aktif
"""


def _cek_jenis(jenis: str) -> str:
    """Jaga-jaga kalau ada pemanggil selain router (tes, skrip) yang salah ketik.

    Nilainya selalu masuk query sebagai bindparam, jadi ini bukan soal injeksi -- yang
    dicegah adalah jenis yang salah eja diam-diam mengembalikan nol baris dan terlihat
    seperti "datanya memang belum ada".
    """
    if jenis not in JENIS_SUMBER_DAYA:
        raise ValueError(f"jenis tidak dikenal: {jenis!r}. Pilihan: {', '.join(JENIS_SUMBER_DAYA)}")
    return jenis


def _norm_filter(v: str | None) -> str | None:
    return None if not v or v == "Semua" else v


def _build_where(
    *,
    jenis: str = "BAHAN",
    supplier: str | None = None,
    satuan: str | None = None,
    kapal: str | None = None,
    tahun: str | None = None,
    search: str | None = None,
) -> tuple[str, dict[str, Any], pencarian.Pencarian | None]:
    """Klausa tambahan + parameter + rakitan pencarian. Parameter kapal/supplier/tahun SELALU
    ada (None kalau tidak aktif) karena dipakai di dalam LATERAL, bukan cuma di WHERE.

    Rakitan pencarian ikut dikembalikan supaya pemanggil yang menampilkan baris bisa
    mengurutkan pakai skor relevansinya; yang cuma menghitung (stats) boleh mengabaikannya.
    """
    kapal_n, supplier_n = _norm_filter(kapal), _norm_filter(supplier)
    tahun_n = _norm_filter(tahun)
    params: dict[str, Any] = {
        "jenis": _cek_jenis(jenis),
        "kapal": kapal_n,
        "supplier": supplier_n,
        "tahun": int(tahun_n) if tahun_n else None,
    }

    clauses = []
    # Filter pembelian aktif -> material yang tidak punya baris harga yang cocok harus
    # gugur. Tanpa ini LEFT JOIN LATERAL akan tetap meloloskannya dengan kolom harga kosong.
    if kapal_n or supplier_n or tahun_n:
        clauses.append("h.id IS NOT NULL")
    if satuan and satuan != "Semua":
        clauses.append("sd.satuan = :satuan")
        params["satuan"] = satuan
    cari = pencarian.bangun(search, _KOLOM_CARI)
    if cari:
        clauses.append(cari.kondisi)
        params.update(cari.params)
    where = (" AND " + " AND ".join(clauses)) if clauses else ""
    return where, params, cari


def list_material(
    *,
    jenis: str = "BAHAN",
    supplier: str | None = None,
    satuan: str | None = None,
    kapal: str | None = None,
    tahun: str | None = None,
    search: str | None = None,
) -> list[MaterialRowOut]:
    where, params, cari = _build_where(
        jenis=jenis, supplier=supplier, satuan=satuan, kapal=kapal, tahun=tahun, search=search
    )
    # Tanpa kata kunci urutannya tetap alfabetis seperti dulu -- peringkat relevansi cuma
    # punya arti kalau ada yang dicari. Nama & id tetap jadi pemecah seri supaya urutannya
    # stabil antar pemanggilan, bukan berubah-ubah untuk skor yang sama.
    urut = f"{cari.skor} DESC, sd.nama, sd.id" if cari else "sd.nama, sd.id"
    query = text(f"{_LIST_QUERY} {where} ORDER BY {urut}")
    with engine.connect() as conn:
        rows = conn.execute(query, params).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("spesifikasi") is None:
            d["spesifikasi"] = ""
        out.append(MaterialRowOut(**d))
    return out


def material_stats(
    *,
    jenis: str = "BAHAN",
    supplier: str | None = None,
    satuan: str | None = None,
    kapal: str | None = None,
    tahun: str | None = None,
    search: str | None = None,
) -> MaterialStats:
    where, params, _ = _build_where(
        jenis=jenis, supplier=supplier, satuan=satuan, kapal=kapal, tahun=tahun, search=search
    )
    # Supplier & kapal dihitung dari SELURUH riwayat material yang lolos filter, bukan dari
    # harga terakhirnya saja -- kalau tidak, KPI "Total Kapal" ikut salah seperti filternya.
    query = text(
        f"""
        WITH lolos AS (
            SELECT sd.id
            FROM   sumber_daya sd
            {_LATERAL_HARGA}
            WHERE  sd.jenis = :jenis AND sd.aktif {where}
        )
        SELECT (SELECT COUNT(*) FROM lolos) AS total_material,
               COUNT(DISTINCT hh.supplier_id) AS total_supplier,
               COUNT(DISTINCT hh.nama_kapal)  AS total_kapal,
               MAX(hh.berlaku_dari)           AS update_terakhir
        FROM   lolos
        LEFT   JOIN sumber_daya_harga hh ON hh.sumber_daya_id = lolos.id
        """
    )
    with engine.connect() as conn:
        row = conn.execute(query, params).mappings().first()
    if not row:
        return MaterialStats(total_material=0, total_supplier=0, total_kapal=0, update_terakhir=None)
    return MaterialStats(**dict(row))


def filter_options(
    *,
    jenis: str = "BAHAN",
    supplier: str | None = None,
    satuan: str | None = None,
    kapal: str | None = None,
    tahun: str | None = None,
    search: str | None = None,
) -> dict[str, list[str]]:
    """Opsi tiap filter, dihitung dari filter lain yang sedang aktif (cascading).

    Aturannya: sebuah nilai hanya jadi opsi kalau memilihnya benar-benar menghasilkan baris.
    Karena kapal/supplier/tahun itu sifat baris harga, penyaringannya dilakukan di tingkat
    baris harga -- bukan di tingkat material. Kalau di tingkat material, memilih kapal
    ANTAREJA akan memunculkan opsi tahun 2025 (dari riwayat kapal lain milik material yang
    sama) padahal kombinasi ANTAREJA+2025 tidak punya satu baris pun.
    """
    beli = {
        "kapal": ("hh.nama_kapal", _norm_filter(kapal)),
        "supplier": ("sup.nama", _norm_filter(supplier)),
        "tahun": ("hh.tahun_pembelian", _norm_filter(tahun)),
    }
    satuan_n = _norm_filter(satuan)
    jenis_n = _cek_jenis(jenis)
    result: dict[str, list[str]] = {}

    with engine.connect() as conn:
        for key in ("supplier", "satuan", "kapal", "tahun"):
            col_expr = "sd.satuan" if key == "satuan" else beli[key][0]
            clauses, params = [], {"jenis": jenis_n}

            # Filter pembelian lain (selain yang sedang dihitung) diterapkan per baris harga.
            for other, (col, val) in beli.items():
                if other == key or val is None:
                    continue
                clauses.append(f"{col} = :{other}")
                params[other] = int(val) if other == "tahun" else val

            if key != "satuan" and satuan_n:
                clauses.append("sd.satuan = :satuan")
                params["satuan"] = satuan_n
            cari = pencarian.bangun(search, _KOLOM_CARI)
            if cari:
                clauses.append(cari.kondisi)
                params.update(cari.params)

            where = (" AND " + " AND ".join(clauses)) if clauses else ""
            rows = conn.execute(
                text(
                    f"""
                    SELECT DISTINCT {col_expr}
                    FROM   sumber_daya sd
                    JOIN   sumber_daya_harga hh ON hh.sumber_daya_id = sd.id
                    LEFT   JOIN supplier sup ON sup.id = hh.supplier_id
                    WHERE  sd.jenis = :jenis AND sd.aktif {where}
                    ORDER  BY {col_expr}
                    """
                ),
                params,
            ).all()
            result[key] = ["Semua"] + [str(r[0]) for r in rows if r[0] is not None]
    return result


def _multi_values(columns: list[str], rows: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    """Bangun klausa VALUES (:c0_0, :c1_0), (:c0_1, :c1_1), ... buat insert banyak baris dalam
    SATU round-trip ke DB -- penting karena DB-nya remote (Railway), jadi tiap round-trip kena
    latency jaringan. Insert satu-satu (loop per baris) kerasa lambat pas paste banyak baris."""
    placeholders = []
    params: dict[str, Any] = {}
    for i, row in enumerate(rows):
        keys = [f"{col}{i}" for col in columns]
        placeholders.append("(" + ", ".join(f":{k}" for k in keys) + ")")
        for col, key in zip(columns, keys):
            params[key] = row[col]
    return ", ".join(placeholders), params


def _resolve_suppliers(conn: Connection, raw_names: list[str]) -> dict[str, int]:
    """Cari-atau-buat semua supplier yang dibutuhkan dalam SATU query (bukan satu query per baris).
    ON CONFLICT DO UPDATE (bukan DO NOTHING) dipakai supaya RETURNING tetap ngasih balik id
    supplier yang sudah ada juga, nggak cuma yang baru dibuat."""
    names = sorted({n.strip() for n in raw_names if n and n.strip()})
    if not names:
        return {}
    values_sql, params = _multi_values(["nama"], [{"nama": n} for n in names])
    rows = conn.execute(
        text(
            f"INSERT INTO supplier (nama) VALUES {values_sql} "
            "ON CONFLICT (nama) DO UPDATE SET nama = EXCLUDED.nama "
            "RETURNING id, nama"
        ),
        params,
    ).all()
    return {nama: id_ for id_, nama in rows}


def _insert_harga(conn: Connection, sumber_daya_id: int, item: PriceCreate, supplier_id: int | None) -> None:
    conn.execute(
        text(
            """
            INSERT INTO sumber_daya_harga
            (sumber_daya_id, supplier_id, harga_satuan, mata_uang, nama_kapal, tahun_pembelian,
             berlaku_dari, sumber, no_dokumen, catatan)
            VALUES (:sd_id, :sup_id, :harga, :mata_uang, :kapal, :tahun, :tgl, :sumber, :no_dok, :catatan)
            """
        ),
        {
            "sd_id": sumber_daya_id,
            "sup_id": supplier_id,
            "harga": item.harga_satuan,
            "mata_uang": item.mata_uang,
            "kapal": item.nama_kapal or None,
            "tahun": item.tahun_pembelian,
            "tgl": item.berlaku_dari or date.today(),
            "sumber": item.sumber or None,
            "no_dok": item.no_dokumen or None,
            "catatan": item.catatan or None,
        },
    )


def _norm_teks(s: str | None) -> str:
    return " ".join((s or "").split()).lower()


def _identitas_key(nama: str, spesifikasi: str | None, satuan: str) -> tuple:
    """Kunci identitas material.

    Part number (disimpan di `spesifikasi`) adalah identitas sebenarnya; nama cuma label
    yang bisa ditulis berbeda-beda oleh orang berbeda. Jadi kalau part number ada, ITU yang
    menentukan -- "AIR FILTER ELEMENT" dan "Air Filter Elem." dengan part number sama adalah
    satu barang, dan harga keduanya menempel di riwayat yang sama.

    Kalau part number tidak ada (cat per liter, plat per ukuran, konsumabel), identitas jatuh
    ke nama + satuan. Karena itu part number tidak dijadikan wajib: mewajibkannya akan
    memblokir barang-barang yang memang tidak punya nomor.

    Harus sejalan dengan unique index di DB: `uq_sd_partno` untuk cabang pertama,
    `uq_sd_identitas` untuk cabang kedua.
    """
    spek = _norm_teks(spesifikasi)
    if spek:
        return ("partno", spek)
    return ("nama", _norm_teks(nama), _norm_teks(satuan))


def _peta_identitas(conn: Connection, jenis: str = "BAHAN") -> dict[tuple, int]:
    """Kunci identitas -> id material, untuk seluruh sumber daya berjenis `jenis`.

    Disaring per jenis dengan sengaja. `_identitas_key()` tidak menyertakan jenis, jadi
    peta yang dicampur akan menyamakan "Pengecatan" sebagai BAHAN dengan "Pengecatan"
    sebagai ALAT -- padahal `uq_sd_identitas` di DB memisahkan keduanya.
    """
    rows = conn.execute(
        text("SELECT id, nama, spesifikasi, satuan FROM sumber_daya WHERE jenis = :jenis"),
        {"jenis": _cek_jenis(jenis)},
    ).all()
    return {_identitas_key(nama, spek, satuan): id_ for id_, nama, spek, satuan in rows}


def _resolve_sumber_daya(
    conn: Connection, items: list[MaterialItemCreate], jenis: str = "BAHAN"
) -> list[int]:
    """Cari-atau-buat master material, kembalikan id sejajar dengan `items`.

    Dulu fungsi ini selalu INSERT, jadi paste batch yang sama dua kali bikin material
    kembar dan riwayat harganya terbelah. Sekarang material yang sudah ada dipakai ulang,
    sehingga harga baru menempel jadi TITIK RIWAYAT di material yang sama -- inilah yang
    bikin tren harga bisa terbentuk sama sekali.
    """
    keys = [_identitas_key(i.nama, i.spesifikasi, i.satuan) for i in items]
    existing = _peta_identitas(conn, jenis)

    # Batch yang sama bisa memuat material yang sama dua kali; yang kedua harus memakai
    # id hasil insert yang pertama, bukan bikin baris baru lagi.
    baru = []
    for key, item in zip(keys, items, strict=True):
        if key not in existing:
            existing[key] = -1
            baru.append(item)

    if baru:
        # `jenis` WAJIB disebut di sini. Tanpa kolom itu, INSERT jatuh ke DEFAULT 'BAHAN'
        # (lihat DDL sumber_daya di database.py) sehingga baris upah/alat yang baru dipaste
        # tersimpan sebagai bahan dan muncul di tab Katalog Material -- rusaknya diam, tidak
        # ada error yang kelihatan.
        values_sql, params = _multi_values(
            ["nama", "spesifikasi", "satuan", "jenis"],
            [
                {
                    "nama": i.nama,
                    "spesifikasi": i.spesifikasi or None,
                    "satuan": i.satuan,
                    "jenis": _cek_jenis(jenis),
                }
                for i in baru
            ],
        )
        inserted = conn.execute(
            text(
                f"INSERT INTO sumber_daya (nama, spesifikasi, satuan, jenis) VALUES {values_sql} "
                "RETURNING id, nama, spesifikasi, satuan"
            ),
            params,
        ).all()
        for id_, nama, spek, satuan in inserted:
            existing[_identitas_key(nama, spek, satuan)] = id_

    return [existing[k] for k in keys]


def _tanda_harga(row: dict[str, Any]) -> tuple:
    """Sidik jari satu titik harga. Dua baris dengan sidik jari sama = kejadian harga
    yang sama ke-input dua kali, bukan perubahan harga.

    `berlaku_dari` sengaja TIDAK ikut. Dia boleh dikosongkan di tempelan dan kalau kosong
    jatuh ke `date.today()`, jadi memasukkannya bikin sidik jari ini berubah tiap ganti
    hari: faktur yang sama ditempel besoknya lolos sebagai "harga baru", padahal harganya
    tidak bergerak sesenpun. Penangkal duplikatnya cuma bekerja dalam satu hari.

    Yang tersisa sudah cukup menjawab "pembelian yang sama atau bukan": material, harga,
    mata uang, supplier, tahun pembelian, dan kapalnya. Dua pembelian berbeda di tahun yang
    sama dengan enam hal itu identik memang tidak dapat dibedakan -- dan memang tidak perlu,
    karena titik harganya persis sama.
    """
    return (
        row["sumber_daya_id"],
        float(row["harga_satuan"]),
        row["mata_uang"],
        row["supplier_id"],
        row["tahun_pembelian"],
        row["nama_kapal"] or "",
    )


def bulk_create(payload: BulkMaterialCreate, *, aktor: str, jenis: str = "BAHAN") -> dict[str, int]:
    with engine.begin() as conn:
        supplier_map = _resolve_suppliers(conn, [item.supplier_nama for item in payload.items])
        sd_ids = _resolve_sumber_daya(conn, payload.items, jenis)

        semua_rows = [
            {
                "sumber_daya_id": sd_id,
                "supplier_id": supplier_map.get(item.supplier_nama.strip()) if item.supplier_nama.strip() else None,
                "harga_satuan": item.harga_satuan,
                "mata_uang": item.mata_uang,
                "nama_kapal": item.nama_kapal or None,
                "tahun_pembelian": item.tahun_pembelian,
                "berlaku_dari": item.berlaku_dari or date.today(),
                "sumber": item.sumber or None,
                "no_dokumen": item.no_dokumen or None,
                "catatan": item.catatan or None,
            }
            for sd_id, item in zip(sd_ids, payload.items, strict=True)
        ]

        # Paste file yang sama dua kali itu kejadian biasa. Sejak material dipakai ulang
        # (bukan bikin master baru), tanpa saringan ini titik harga identik akan menumpuk
        # dan muncul sebagai titik palsu di grafik tren. Jalur edit sudah dijaga oleh
        # `_harga_berubah`; ini padanannya untuk jalur tambah.
        sudah_ada = set()
        if sd_ids:
            existing = conn.execute(
                text(
                    """
                    SELECT sumber_daya_id, harga_satuan, mata_uang, supplier_id,
                           berlaku_dari, tahun_pembelian, nama_kapal
                    FROM   sumber_daya_harga
                    WHERE  sumber_daya_id = ANY(:ids)
                    """
                ),
                {"ids": list(set(sd_ids))},
            ).mappings().all()
            sudah_ada = {_tanda_harga(dict(r)) for r in existing}

        harga_rows = []
        for row in semua_rows:
            tanda = _tanda_harga(row)
            if tanda in sudah_ada:
                continue
            sudah_ada.add(tanda)  # cegah duplikat di dalam satu batch juga
            harga_rows.append(row)

        dilewati = len(semua_rows) - len(harga_rows)
        if not harga_rows:
            audit.catat(
                conn,
                aktor=aktor,
                aksi="create",
                entitas="material",
                jumlah=0,
                detail={"jenis": jenis, "dilewati_duplikat": dilewati},
            )
            return {"saved": 0, "titik_harga_baru": 0, "dilewati": dilewati}

        harga_values_sql, harga_params = _multi_values(
            [
                "sumber_daya_id",
                "supplier_id",
                "harga_satuan",
                "mata_uang",
                "nama_kapal",
                "tahun_pembelian",
                "berlaku_dari",
                "sumber",
                "no_dokumen",
                "catatan",
            ],
            harga_rows,
        )
        conn.execute(
            text(
                "INSERT INTO sumber_daya_harga "
                "(sumber_daya_id, supplier_id, harga_satuan, mata_uang, nama_kapal, tahun_pembelian, "
                "berlaku_dari, sumber, no_dokumen, catatan) "
                f"VALUES {harga_values_sql}"
            ),
            harga_params,
        )
        audit.catat(
            conn,
            aktor=aktor,
            aksi="create",
            entitas="material",
            jumlah=len(harga_rows),
            detail={
                "jenis": jenis,
                "nama": [i.nama for i in payload.items[:20]],
                "dilewati_duplikat": dilewati,
            },
        )
    return {"saved": len(harga_rows), "titik_harga_baru": len(harga_rows), "dilewati": dilewati}


def _harga_berubah(conn: Connection, sumber_daya_id: int, item: PriceCreate, supplier_id: int | None) -> bool:
    """True kalau harga yang dikirim beda dari titik harga terakhir material ini.

    Tanpa cek ini, `bulk_patch` menyisipkan baris harga baru SETIAP kali material di-edit
    -- benerin typo di kolom nama pun bikin satu "titik harga" palsu. Untuk katalog biasa
    itu tak kelihatan, tapi buat grafik tren itu racun: riwayatnya jadi campuran antara
    perubahan harga asli dan jejak penyuntingan.
    """
    row = conn.execute(
        text(
            f"""
            SELECT harga_satuan, mata_uang, supplier_id, berlaku_dari, tahun_pembelian, nama_kapal
            FROM   sumber_daya_harga
            WHERE  sumber_daya_id = :id
            ORDER  BY {urutan_harga_sql()}
            LIMIT  1
            """
        ),
        {"id": sumber_daya_id},
    ).mappings().first()
    if row is None:
        return True
    return (
        float(row["harga_satuan"]) != float(item.harga_satuan)
        or row["mata_uang"] != item.mata_uang
        or row["supplier_id"] != supplier_id
        or row["berlaku_dari"] != (item.berlaku_dari or date.today())
        or row["tahun_pembelian"] != item.tahun_pembelian
        or (row["nama_kapal"] or "") != (item.nama_kapal or "")
    )


def bulk_patch(body: BulkPatchMaterialRequest, *, aktor: str) -> dict[str, int]:
    deleted = 0
    updated = 0
    harga_baru = 0
    with engine.begin() as conn:
        if body.delete_ids:
            # ahsp_komponen menunjuk ke sumber_daya tanpa ON DELETE, jadi Postgres menolak
            # penghapusan ini sebagai pelanggaran foreign key. Tanpa pemeriksaan di sini,
            # yang sampai ke pengguna cuma "Gagal menyimpan ke database" -- benar bahwa
            # datanya aman, tapi tidak memberi tahu apa pun tentang sebabnya atau jalan
            # keluarnya.
            terpakai = conn.execute(
                text(
                    """
                    SELECT sd.nama, a.uraian
                    FROM   ahsp_komponen k
                    JOIN   sumber_daya sd ON sd.id = k.sumber_daya_id
                    JOIN   ahsp a         ON a.id  = k.ahsp_id
                    WHERE  k.sumber_daya_id = ANY(:ids)
                    ORDER  BY sd.nama, a.uraian
                    """
                ),
                {"ids": body.delete_ids},
            ).all()
            if terpakai:
                nama = sorted({t[0] for t in terpakai})
                analisa = sorted({t[1] for t in terpakai})
                raise ValueError(
                    f"{', '.join(nama)} masih dipakai di analisa harga satuan: "
                    f"{', '.join(analisa[:5])}"
                    + (f", dan {len(analisa) - 5} lainnya" if len(analisa) > 5 else "")
                    + ". Hapus dulu komponennya dari analisa itu di tab Struktur Biaya."
                )

            nama_dihapus = conn.execute(
                text("SELECT nama FROM sumber_daya WHERE id = ANY(:ids)"), {"ids": body.delete_ids}
            ).scalars().all()
            conn.execute(
                text("DELETE FROM sumber_daya WHERE id = ANY(:ids)"), {"ids": body.delete_ids}
            )
            deleted = len(body.delete_ids)
            audit.catat(
                conn,
                aktor=aktor,
                aksi="delete",
                entitas="material",
                jumlah=deleted,
                detail={"ids": body.delete_ids, "nama": list(nama_dihapus)[:20]},
            )

        if body.updates:
            supplier_map = _resolve_suppliers(conn, [u.data.supplier_nama for u in body.updates])
            upd_q = text(
                """
                UPDATE sumber_daya
                SET nama = :nama, spesifikasi = :spesifikasi, satuan = :satuan
                WHERE id = :id
                """
            )
            for u in body.updates:
                d = u.data
                conn.execute(
                    upd_q,
                    {
                        "nama": d.nama,
                        "spesifikasi": d.spesifikasi or None,
                        "satuan": d.satuan,
                        "id": u.id,
                    },
                )
                supplier_id = supplier_map.get(d.supplier_nama.strip()) if d.supplier_nama.strip() else None
                if _harga_berubah(conn, u.id, d, supplier_id):
                    _insert_harga(conn, u.id, d, supplier_id)
                    harga_baru += 1
            updated = len(body.updates)
            audit.catat(
                conn,
                aktor=aktor,
                aksi="update",
                entitas="material",
                jumlah=updated,
                detail={
                    "ids": [u.id for u in body.updates][:20],
                    "titik_harga_baru": harga_baru,
                },
            )
    return {"deleted": deleted, "updated": updated, "titik_harga_baru": harga_baru}


# ---------- Pratinjau paste ----------


def preview_bulk(payload: BulkMaterialCreate, *, jenis: str = "BAHAN") -> dict[str, Any]:
    """Jalankan seluruh logika keputusan tanpa menulis apa pun.

    Tanpa ini antarmuka diam soal apa yang akan terjadi, sehingga orang yang hati-hati
    menyangka aplikasinya akan bikin duplikat lalu memilih memasukkan data secara manual --
    padahal titik harga baru untuk material yang sudah ada sudah ditangani otomatis.
    Endpoint ini memakai fungsi keputusan yang sama dengan jalur simpan, jadi hasilnya tidak
    bisa berbeda dari yang benar-benar terjadi nanti.
    """
    with engine.connect() as conn:
        peta = _peta_identitas(conn, jenis)
        nama_master = dict(
            conn.execute(
                text("SELECT id, nama FROM sumber_daya WHERE jenis = :jenis"),
                {"jenis": _cek_jenis(jenis)},
            ).all()
        )

        ids = [peta.get(_identitas_key(i.nama, i.spesifikasi, i.satuan)) for i in payload.items]
        ada_ids = [i for i in ids if i is not None]

        harga_lama: dict[int, tuple[float, str]] = {}
        tanda_ada: set[tuple] = set()
        if ada_ids:
            for r in conn.execute(
                text(
                    f"""
                    SELECT sumber_daya_id, harga_satuan, mata_uang, supplier_id,
                           berlaku_dari, tahun_pembelian, nama_kapal
                    FROM   sumber_daya_harga
                    WHERE  sumber_daya_id = ANY(:ids)
                    ORDER  BY sumber_daya_id, {urutan_harga_sql()}
                    """
                ),
                {"ids": ada_ids},
            ).mappings():
                d = dict(r)
                tanda_ada.add(_tanda_harga(d))
                harga_lama.setdefault(d["sumber_daya_id"], (float(d["harga_satuan"]), d["mata_uang"]))

        sup_map = dict(
            conn.execute(
                text("SELECT btrim(nama), id FROM supplier WHERE btrim(nama) = ANY(:n)"),
                {"n": [i.supplier_nama.strip() for i in payload.items if i.supplier_nama.strip()] or [""]},
            ).all()
        )

    baris = []
    tanda_batch: set[tuple] = set()
    baru_di_batch: set[tuple] = set()
    for item, sd_id in zip(payload.items, ids, strict=True):
        row = {
            "nama": item.nama,
            "spesifikasi": item.spesifikasi or "",
            "satuan": item.satuan,
            "harga_satuan": item.harga_satuan,
            "mata_uang": item.mata_uang,
            "status": "material_baru",
            "harga_lama": None,
            "perubahan_persen": None,
            "peringatan": None,
        }

        if sd_id is not None:
            tanda = _tanda_harga(
                {
                    "sumber_daya_id": sd_id,
                    "harga_satuan": item.harga_satuan,
                    "mata_uang": item.mata_uang,
                    "supplier_id": sup_map.get(item.supplier_nama.strip())
                    if item.supplier_nama.strip()
                    else None,
                    "tahun_pembelian": item.tahun_pembelian,
                    "nama_kapal": item.nama_kapal or None,
                }
            )
            if tanda in tanda_ada or tanda in tanda_batch:
                row["status"] = "dilewati"
            else:
                tanda_batch.add(tanda)
                row["status"] = "harga_baru"
                lama = harga_lama.get(sd_id)
                if lama and lama[1] == item.mata_uang and lama[0] > 0:
                    row["harga_lama"] = lama[0]
                    row["perubahan_persen"] = round(
                        (item.harga_satuan - lama[0]) / lama[0] * 100, 2
                    )

            # Part number cocok tapi namanya beda: material lama yang dipakai, dan nama di
            # paste diabaikan. Itu biasanya benar (nama cuma label) tapi bisa juga tanda
            # part number salah ketik, jadi harus kelihatan sebelum disimpan.
            tersimpan = nama_master.get(sd_id, "")
            if item.spesifikasi.strip() and _norm_teks(tersimpan) != _norm_teks(item.nama):
                row["peringatan"] = (
                    f"Part number ini sudah tercatat dengan nama \"{tersimpan}\". "
                    f"Nama itu yang dipakai, bukan \"{item.nama}\"."
                )
        else:
            # Material baru yang muncul dua kali dalam satu paste: kemunculan pertama
            # membuat masternya, sisanya menempel ke master yang sama -- jadi harus
            # dinilai seperti material yang sudah ada, bukan "material baru" dua kali.
            key = _identitas_key(item.nama, item.spesifikasi, item.satuan)
            # Bentuknya harus sejalan dengan _tanda_harga(): tanpa berlaku_dari, karena
            # tanggal yang dikosongkan jatuh ke hari ini dan bikin duplikat lolos besoknya.
            tanda = ("baru", key, item.harga_satuan, item.mata_uang,
                     item.tahun_pembelian, item.nama_kapal or "")
            if key in baru_di_batch:
                row["status"] = "dilewati" if tanda in tanda_batch else "harga_baru"
            else:
                baru_di_batch.add(key)
            tanda_batch.add(tanda)

            if not item.spesifikasi.strip():
                row["peringatan"] = (
                    "Tanpa part number, identitas material bertumpu pada nama + satuan — "
                    "penulisan nama yang berbeda akan terhitung sebagai material lain."
                )

        baris.append(row)

    ringkas = {
        "material_baru": sum(1 for b in baris if b["status"] == "material_baru"),
        "harga_baru": sum(1 for b in baris if b["status"] == "harga_baru"),
        "dilewati": sum(1 for b in baris if b["status"] == "dilewati"),
        "peringatan": sum(1 for b in baris if b["peringatan"]),
    }
    return {"ringkas": ringkas, "baris": baris}


# ---------- Riwayat harga per material ----------


def price_history(sumber_daya_id: int) -> list[PriceHistoryRow]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT h.id, h.harga_satuan, h.mata_uang, h.berlaku_dari, h.tahun_pembelian,
                       h.nama_kapal, h.sumber, h.no_dokumen, h.catatan, h.dibuat_pada,
                       sup.nama AS supplier_nama
                FROM   sumber_daya_harga h
                LEFT   JOIN supplier sup ON sup.id = h.supplier_id
                WHERE  h.sumber_daya_id = :id
                ORDER  BY {urutan_harga_sql("h", terbaru_dulu=False)}
                """
            ),
            {"id": sumber_daya_id},
        ).mappings().all()
    return [PriceHistoryRow(**dict(r)) for r in rows]


def add_price(sumber_daya_id: int, item: PriceCreate, *, aktor: str) -> int:
    with engine.begin() as conn:
        ada = conn.execute(
            text("SELECT nama FROM sumber_daya WHERE id = :id"), {"id": sumber_daya_id}
        ).scalar()
        if ada is None:
            raise ValueError("Material tidak ditemukan")
        supplier_map = _resolve_suppliers(conn, [item.supplier_nama])
        supplier_id = supplier_map.get(item.supplier_nama.strip()) if item.supplier_nama.strip() else None
        _insert_harga(conn, sumber_daya_id, item, supplier_id)
        new_id = conn.execute(
            text("SELECT id FROM sumber_daya_harga WHERE sumber_daya_id = :id ORDER BY id DESC LIMIT 1"),
            {"id": sumber_daya_id},
        ).scalar()
        audit.catat(
            conn,
            aktor=aktor,
            aksi="create",
            entitas="material_harga",
            detail={
                "sumber_daya_id": sumber_daya_id,
                "nama": ada,
                "harga_satuan": float(item.harga_satuan),
                "mata_uang": item.mata_uang,
                "berlaku_dari": item.berlaku_dari or date.today(),
            },
        )
    return int(new_id)


def delete_price(harga_id: int, *, aktor: str) -> None:
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT sumber_daya_id, harga_satuan, berlaku_dari FROM sumber_daya_harga WHERE id = :id"),
            {"id": harga_id},
        ).mappings().first()
        if row is None:
            raise ValueError("Titik harga tidak ditemukan")
        sisa = conn.execute(
            text("SELECT COUNT(*) FROM sumber_daya_harga WHERE sumber_daya_id = :id"),
            {"id": row["sumber_daya_id"]},
        ).scalar()
        # Material tanpa harga sama sekali bakal hilang dari daftar katalog (view
        # v_harga_terkini kosong -> kolom harga null), jadi tolak di sini biar tidak
        # ada material "hantu" yang cuma bisa dibetulkan lewat SQL manual.
        if sisa is not None and int(sisa) <= 1:
            raise ValueError(
                "Ini satu-satunya titik harga material tersebut. "
                "Tambahkan harga baru dulu, atau hapus materialnya dari tabel katalog."
            )
        conn.execute(text("DELETE FROM sumber_daya_harga WHERE id = :id"), {"id": harga_id})
        audit.catat(
            conn,
            aktor=aktor,
            aksi="delete",
            entitas="material_harga",
            detail={
                "harga_id": harga_id,
                "sumber_daya_id": row["sumber_daya_id"],
                "harga_satuan": float(row["harga_satuan"]),
                "berlaku_dari": row["berlaku_dari"],
            },
        )
