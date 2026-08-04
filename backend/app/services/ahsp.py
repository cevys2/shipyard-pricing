"""Perhitungan dan penyimpanan AHSP (tab Struktur Biaya).

Tiga aturan dari bagian 3 docs/rencana-langkah-3-struktur-biaya.md dijaga di sini:
komponen tanpa harga tidak pernah dianggap nol, mata uang berbeda tidak pernah
dijumlahkan, dan rumus harga jual cuma ada di satu fungsi.
"""

import json
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.database import engine
from app.schemas.ahsp import (
    KELOMPOK,
    AhspCreate,
    AhspUpdate,
    KomponenInput,
)
from app.services import audit


def hitung_harga_jual(subtotal: dict[str, Decimal], parameter: dict) -> Decimal | None:
    """SATU-SATUNYA tempat rumus harga jual boleh ditulis.

    subtotal  -- {'BAHAN': ..., 'UPAH': ..., 'ALAT': ..., 'KONSUMABEL': ...}
    parameter -- isi kolom ahsp.parameter (JSONB)

    Sudah diverifikasi dari file Excel asli (bagian 1B.2 rencana): 54 dari 54 blok AHSP
    punya nilai akhir = jumlah seluruh subtotal, persis. Tidak ada overhead, keuntungan,
    atau markup apa pun di tingkat AHSP -- marginnya sudah tertanam di dalam tarif tiap
    komponen. PPN ditambahkan di tingkat dokumen penawaran, bukan di sini.

    Jadi rumusnya memang penjumlahan biasa. JANGAN menambahkan persentase apa pun
    "karena biasanya ada" -- di perusahaan ini memang tidak ada.

    A9 diputuskan 4 Agustus 2026: **jumlahkan jujur**. Di file asli, 37% kelompok biaya punya
    Sub Total yang tidak sama dengan jumlah barisnya -- angka akhirnya dibulatkan lebih dulu
    lalu komponennya dicocokkan ke belakang. Aplikasi ini sengaja TIDAK meniru itu: tidak ada
    kolom harga_ditetapkan, tidak ada baris penyesuaian, tidak ada subtotal yang bisa diketik
    manual. Angka yang berbeda dari Excel adalah perbaikan, bukan selisih yang perlu ditutup.
    """
    return sum(subtotal.values(), Decimal(0))


# Query komponen + harga terkini. LEFT JOIN, bukan JOIN: komponen yang belum punya baris
# harga harus tetap muncul supaya bisa dilaporkan sebagai bolong, bukan hilang diam-diam.
_KOMPONEN_SQL = """
    SELECT k.id, k.sumber_daya_id, k.kelompok, k.qty, k.shift, k.jml_hari, k.urutan,
           COALESCE(k.catatan, '') AS catatan,
           sd.nama, COALESCE(sd.spesifikasi, '') AS spesifikasi, sd.satuan,
           h.harga_satuan, h.mata_uang
    FROM   ahsp_komponen k
    JOIN   sumber_daya sd ON sd.id = k.sumber_daya_id
    LEFT   JOIN v_harga_terkini h ON h.sumber_daya_id = k.sumber_daya_id
    WHERE  k.ahsp_id = :id
    ORDER  BY k.urutan, k.id
"""

# Ringkasan per AHSP untuk daftar dan kartu KPI. Baris non-IDR ikut dihitung sebagai
# "tanpa harga" karena perlakuannya sama: tidak boleh masuk penjumlahan (aturan 3.2).
_RINGKAS_KOMPONEN_SQL = """
    SELECT ak.ahsp_id,
           COUNT(*) AS n_komponen,
           COUNT(*) FILTER (WHERE h.harga_satuan IS NULL OR h.mata_uang <> 'IDR')
               AS n_tanpa_harga,
           SUM(ak.qty * ak.shift * ak.jml_hari * h.harga_satuan)
               FILTER (WHERE h.mata_uang = 'IDR') AS subtotal_total
    FROM   ahsp_komponen ak
    LEFT   JOIN v_harga_terkini h ON h.sumber_daya_id = ak.sumber_daya_id
    GROUP  BY ak.ahsp_id
"""


def _baris_ahsp(r: dict[str, Any]) -> dict[str, Any]:
    d = dict(r)
    n = int(d.pop("n_komponen", 0) or 0)
    bolong = int(d.pop("n_tanpa_harga", 0) or 0)
    d["n_komponen"] = n
    d["n_tanpa_harga"] = bolong
    d["lengkap"] = n > 0 and bolong == 0
    return d


def list_ahsp(*, hanya_aktif: bool = True) -> list[dict[str, Any]]:
    klausa = "WHERE a.aktif" if hanya_aktif else ""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT a.*, k.n_komponen, k.n_tanpa_harga, k.subtotal_total
                FROM   ahsp a
                LEFT   JOIN ({_RINGKAS_KOMPONEN_SQL}) k ON k.ahsp_id = a.id
                {klausa}
                ORDER  BY a.uraian, a.id
                """
            )
        ).mappings().all()
    return [_baris_ahsp(r) for r in rows]


def ringkas() -> dict[str, int]:
    """Angka kartu KPI: berapa AHSP sudah punya rincian lengkap dari total."""
    with engine.connect() as conn:
        row = conn.execute(
            text(
                f"""
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (
                           WHERE COALESCE(k.n_komponen, 0) > 0
                             AND COALESCE(k.n_tanpa_harga, 0) = 0
                       ) AS lengkap,
                       COALESCE(SUM(k.n_tanpa_harga), 0) AS komponen_tanpa_harga
                FROM   ahsp a
                LEFT   JOIN ({_RINGKAS_KOMPONEN_SQL}) k ON k.ahsp_id = a.id
                WHERE  a.aktif
                """
            )
        ).mappings().first()
    return dict(row) if row else {"total": 0, "lengkap": 0, "komponen_tanpa_harga": 0}


def ambil_ahsp(ahsp_id: int) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                f"""
                SELECT a.*, k.n_komponen, k.n_tanpa_harga, k.subtotal_total
                FROM   ahsp a
                LEFT   JOIN ({_RINGKAS_KOMPONEN_SQL}) k ON k.ahsp_id = a.id
                WHERE  a.id = :id
                """
            ),
            {"id": ahsp_id},
        ).mappings().first()
    return _baris_ahsp(row) if row else None


def create_ahsp(data: AhspCreate, *, aktor: str) -> int:
    with engine.begin() as conn:
        new_id = conn.execute(
            text(
                """
                INSERT INTO ahsp (uraian, satuan, jenis_jual, kategori, catatan, parameter)
                VALUES (:uraian, :satuan, :jenis_jual, :kategori, :catatan,
                        CAST(:parameter AS JSONB))
                RETURNING id
                """
            ),
            {
                "uraian": data.uraian,
                "satuan": data.satuan,
                "jenis_jual": data.jenis_jual,
                "kategori": data.kategori or None,
                "catatan": data.catatan or None,
                # pg8000 tidak mengadaptasi dict ke JSONB sendiri -- pola yang sama
                # dipakai services/audit.py.
                "parameter": json.dumps(data.parameter or {}),
            },
        ).scalar()
        audit.catat(
            conn,
            aktor=aktor,
            aksi="create",
            entitas="ahsp",
            detail={"id": new_id, "uraian": data.uraian, "satuan": data.satuan},
        )
    return int(new_id)


def update_ahsp(ahsp_id: int, data: AhspUpdate, *, aktor: str) -> bool:
    isi = data.model_dump(exclude_unset=True)
    if not isi:
        return True

    set_parts, params = [], {"id": ahsp_id}
    for kolom, nilai in isi.items():
        if kolom == "parameter":
            set_parts.append("parameter = CAST(:parameter AS JSONB)")
            params["parameter"] = json.dumps(nilai or {})
        else:
            set_parts.append(f"{kolom} = :{kolom}")
            params[kolom] = nilai
    set_parts.append("diubah_pada = now()")

    with engine.begin() as conn:
        hasil = conn.execute(
            text(f"UPDATE ahsp SET {', '.join(set_parts)} WHERE id = :id"), params
        )
        if hasil.rowcount == 0:
            return False
        audit.catat(
            conn,
            aktor=aktor,
            aksi="update",
            entitas="ahsp",
            detail={"id": ahsp_id, "ubah": list(isi.keys())},
        )
    return True


def delete_ahsp(ahsp_id: int, *, aktor: str) -> bool:
    with engine.begin() as conn:
        uraian = conn.execute(
            text("SELECT uraian FROM ahsp WHERE id = :id"), {"id": ahsp_id}
        ).scalar()
        if uraian is None:
            return False
        # ahsp_komponen ikut terhapus lewat ON DELETE CASCADE.
        conn.execute(text("DELETE FROM ahsp WHERE id = :id"), {"id": ahsp_id})
        audit.catat(
            conn,
            aktor=aktor,
            aksi="delete",
            entitas="ahsp",
            detail={"id": ahsp_id, "uraian": uraian},
        )
    return True


def _ambil_komponen(conn: Connection, ahsp_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(text(_KOMPONEN_SQL), {"id": ahsp_id}).mappings().all()
    hasil = []
    for r in rows:
        d = dict(r)
        harga, mata_uang = d["harga_satuan"], d["mata_uang"]
        # `jumlah` hanya diisi kalau harganya benar-benar bisa dipakai. Mengisinya untuk
        # baris EUR akan bikin angka yang tidak boleh dijumlahkan terlihat siap dijumlahkan.
        d["jumlah"] = (
            d["qty"] * d["shift"] * d["jml_hari"] * harga
            if harga is not None and mata_uang == "IDR"
            else None
        )
        hasil.append(d)
    return hasil


def komponen(ahsp_id: int) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        return _ambil_komponen(conn, ahsp_id)


def ganti_komponen(ahsp_id: int, items: list[KomponenInput], *, aktor: str) -> int:
    """Ganti SELURUH rincian dalam satu transaksi.

    Bukan tambah/hapus per baris: kalau separuh tersimpan dan separuh gagal, pengguna
    tidak punya cara tahu bagian mana yang mana -- pelajaran yang sama dengan perbaikan
    impor docking 31 Juli 2026.
    """
    # Dicek di sini, bukan dibiarkan ditangkap UNIQUE (ahsp_id, sumber_daya_id, kelompok):
    # IntegrityError sampai ke pengguna sebagai "sepertinya sudah tersimpan", yang tidak
    # menjelaskan apa pun tentang baris kembar.
    pasangan = [(i.sumber_daya_id, i.kelompok) for i in items]
    if len(set(pasangan)) != len(pasangan):
        raise ValueError(
            "Ada komponen yang sama dipakai dua kali di kelompok yang sama. "
            "Gabungkan jadi satu baris, atau pindahkan salah satunya ke kelompok lain."
        )

    with engine.begin() as conn:
        ada = conn.execute(text("SELECT 1 FROM ahsp WHERE id = :id"), {"id": ahsp_id}).scalar()
        if ada is None:
            raise ValueError("AHSP tidak ditemukan")

        conn.execute(text("DELETE FROM ahsp_komponen WHERE ahsp_id = :id"), {"id": ahsp_id})

        if items:
            placeholders, params = [], {"ahsp_id": ahsp_id}
            for n, i in enumerate(items):
                placeholders.append(
                    f"(:ahsp_id, :sd{n}, :kel{n}, :qty{n}, :shift{n}, :hari{n}, :urut{n}, :cat{n})"
                )
                params |= {
                    f"sd{n}": i.sumber_daya_id,
                    f"kel{n}": i.kelompok,
                    f"qty{n}": i.qty,
                    f"shift{n}": i.shift,
                    f"hari{n}": i.jml_hari,
                    f"urut{n}": i.urutan if i.urutan else n,
                    f"cat{n}": i.catatan or None,
                }
            conn.execute(
                text(
                    "INSERT INTO ahsp_komponen "
                    "(ahsp_id, sumber_daya_id, kelompok, qty, shift, jml_hari, urutan, catatan) "
                    f"VALUES {', '.join(placeholders)}"
                ),
                params,
            )

        conn.execute(text("UPDATE ahsp SET diubah_pada = now() WHERE id = :id"), {"id": ahsp_id})
        audit.catat(
            conn,
            aktor=aktor,
            aksi="update",
            entitas="ahsp",
            jumlah=len(items),
            detail={"id": ahsp_id, "komponen": len(items)},
        )
    return len(items)


def hitung(ahsp_id: int) -> dict[str, Any] | None:
    with engine.connect() as conn:
        parameter = conn.execute(
            text("SELECT parameter FROM ahsp WHERE id = :id"), {"id": ahsp_id}
        ).scalar()
        if parameter is None:
            ada = conn.execute(
                text("SELECT 1 FROM ahsp WHERE id = :id"), {"id": ahsp_id}
            ).scalar()
            if ada is None:
                return None
            parameter = {}
        baris = _ambil_komponen(conn, ahsp_id)

    subtotal = {k: Decimal(0) for k in KELOMPOK}
    alasan: list[str] = []
    lengkap = bool(baris)
    if not baris:
        alasan.append("Belum ada satu pun komponen di AHSP ini")

    for b in baris:
        label = b["nama"] if not b["spesifikasi"] else f"{b['nama']} ({b['spesifikasi']})"
        if b["harga_satuan"] is None:
            lengkap = False
            alasan.append(f"{label} belum punya harga")
            continue
        if b["mata_uang"] != "IDR":
            # Konversi butuh kurs, dan kurs butuh tanggal + sumber yang disepakati.
            # Menebaknya sama saja mengubah harga diam-diam (aturan 3.2).
            lengkap = False
            alasan.append(
                f"{label} harganya dalam {b['mata_uang']}, tidak dijumlahkan -- "
                "catat harga rupiah yang benar-benar dibayar"
            )
            continue
        subtotal[b["kelompok"]] += b["jumlah"]

    total = sum(subtotal.values(), Decimal(0))
    harga_jual = hitung_harga_jual(subtotal, parameter or {}) if lengkap else None
    return {
        "subtotal": subtotal,
        "subtotal_total": total,
        "harga_jual": harga_jual,
        # Dipertahankan meski selalu true: kalau suatu saat klien mulai memakai markup,
        # penanda ini sudah ada dan frontend tidak perlu diubah.
        "rumus_terpasang": True,
        "lengkap": lengkap,
        "alasan": alasan,
    }
