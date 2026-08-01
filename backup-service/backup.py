"""Cadangkan seluruh isi database ke Backblaze B2.

Kenapa menyalin tabel sendiri, bukan memanggil `pg_dump`: image Railway tidak memuat
postgresql-client, dan menambahkannya berarti mengurus konfigurasi nixpacks. Seluruh data
di sini kecil (sekitar 2 MB) dan strukturnya sederhana, jadi menyalin per tabel jadi CSV
sudah cukup untuk memulihkan, tanpa dependensi sistem apa pun.

Yang dihasilkan satu berkas `.tar.gz` berisi:
  - `<nama_tabel>.csv` untuk tiap tabel, header di baris pertama
  - `manifest.json` berisi jumlah baris per tabel, waktu, dan versi Postgres

Skrip ini SELALU memverifikasi hasil unggahannya dengan membaca ulang objek di B2.
Kegagalan paling berbahaya pada backup adalah yang diam -- service hijau, tapi tidak ada
berkas yang benar-benar mendarat. Persis itu yang terjadi selama ini: berkas ini kosong,
jadi service-nya sukses tiap kali tanpa melakukan apa pun. Karena itu skrip ini keluar
dengan status bukan-nol kalau verifikasinya gagal, supaya kegagalannya terlihat.

Variabel lingkungan yang dibutuhkan:
  DATABASE_URL          connection string Postgres (sama dengan backend)
  B2_KEY_ID             applicationKeyId dari Backblaze
  B2_APPLICATION_KEY    applicationKey dari Backblaze
  B2_BUCKET             nama bucket
  B2_ENDPOINT           mis. https://s3.us-west-004.backblazeb2.com
  B2_PREFIX             opsional, folder di dalam bucket (default "shipyard-pricing")
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import tarfile
from datetime import datetime, timezone

import boto3
from botocore.config import Config
from sqlalchemy import create_engine, text


def normalize_db_url(db_url: str) -> str:
    """Sama dengan backend -- pg8000 dipakai supaya tidak butuh libpq."""
    if db_url.startswith("postgres://"):
        return db_url.replace("postgres://", "postgresql+pg8000://", 1)
    if db_url.startswith("postgresql://") and "pg8000" not in db_url:
        return db_url.replace("postgresql://", "postgresql+pg8000://", 1)
    return db_url


def wajib(nama: str) -> str:
    nilai = os.environ.get(nama, "").strip()
    if not nilai:
        sys.exit(f"[gagal] variabel lingkungan {nama} belum diisi")
    return nilai


def ambil_tabel(conn) -> list[str]:
    """Hanya tabel biasa. View di-skip karena isinya turunan, bukan data asli."""
    return [
        r[0]
        for r in conn.execute(
            text(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """
            )
        )
    ]


def tabel_ke_csv(conn, tabel: str) -> tuple[bytes, int]:
    # Nama tabel dikutip, bukan dijadikan parameter: Postgres tidak menerima nama objek
    # sebagai parameter terikat. Sumbernya information_schema, bukan masukan pengguna.
    res = conn.execute(text(f'SELECT * FROM "{tabel}"'))
    kolom = list(res.keys())
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(kolom)
    n = 0
    for baris in res:
        w.writerow(["" if v is None else v for v in baris])
        n += 1
    return buf.getvalue().encode("utf-8"), n


def main() -> None:
    db_url = wajib("DATABASE_URL")
    key_id = wajib("B2_KEY_ID")
    app_key = wajib("B2_APPLICATION_KEY")
    bucket = wajib("B2_BUCKET")
    endpoint = wajib("B2_ENDPOINT")
    prefix = os.environ.get("B2_PREFIX", "shipyard-pricing").strip("/")

    saat = datetime.now(timezone.utc)
    stempel = saat.strftime("%Y-%m-%dT%H-%M-%SZ")

    engine = create_engine(normalize_db_url(db_url), pool_pre_ping=True)
    manifest: dict = {"dibuat_pada": saat.isoformat(), "tabel": {}}

    tar_buf = io.BytesIO()
    with engine.connect() as conn:
        manifest["postgres"] = conn.execute(text("SELECT version()")).scalar()
        tabel = ambil_tabel(conn)
        if not tabel:
            sys.exit("[gagal] tidak ada tabel ditemukan -- menolak mengunggah cadangan kosong")

        with tarfile.open(fileobj=tar_buf, mode="w:gz") as tar:
            for t in tabel:
                isi, n = tabel_ke_csv(conn, t)
                manifest["tabel"][t] = n
                info = tarfile.TarInfo(name=f"{t}.csv")
                info.size = len(isi)
                info.mtime = int(saat.timestamp())
                tar.addfile(info, io.BytesIO(isi))
                print(f"  {t}: {n} baris, {len(isi)} byte")

            m = json.dumps(manifest, indent=2, default=str).encode("utf-8")
            info = tarfile.TarInfo(name="manifest.json")
            info.size = len(m)
            info.mtime = int(saat.timestamp())
            tar.addfile(info, io.BytesIO(m))

    data = tar_buf.getvalue()
    total_baris = sum(manifest["tabel"].values())
    print(f"arsip siap: {len(data)} byte, {len(tabel)} tabel, {total_baris} baris")

    # Cadangan tanpa satu baris pun hampir pasti tanda ada yang salah, bukan database yang
    # memang kosong. Lebih baik berhenti dan terlihat gagal daripada menambah riwayat
    # cadangan dengan berkas hampa yang menipu.
    if total_baris == 0:
        sys.exit("[gagal] semua tabel kosong -- menolak mengunggah")

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=key_id,
        aws_secret_access_key=app_key,
        config=Config(signature_version="s3v4"),
    )
    kunci = f"{prefix}/{saat:%Y}/{saat:%m}/shipyard-{stempel}.tar.gz"
    s3.put_object(Bucket=bucket, Key=kunci, Body=data, ContentType="application/gzip")

    # Baca ulang: satu-satunya bukti bahwa berkasnya benar-benar mendarat.
    head = s3.head_object(Bucket=bucket, Key=kunci)
    if head["ContentLength"] != len(data):
        sys.exit(
            f"[gagal] ukuran di B2 ({head['ContentLength']}) beda dari yang dikirim ({len(data)})"
        )

    print(f"[sukses] {kunci} terverifikasi di B2, {head['ContentLength']} byte")


if __name__ == "__main__":
    main()
