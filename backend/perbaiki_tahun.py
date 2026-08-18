"""Perbaiki kolom `tahun` dan `id` di tabel_katalog_harga.

Isinya sama persis dengan berkas SQL dari Claude Code, tapi dibungkus supaya seluruhnya
berjalan di SATU koneksi = SATU transaksi. Itu yang tidak bisa dilakukan kotak query
Railway: di sana tiap tombol Run membuka sambungan baru, sehingga BEGIN, tabel sementara,
dan COMMIT tidak pernah bertemu.

CARA PAKAI
----------
Taruh berkas ini di folder `backend/` repo katalog-harga, lalu dari folder itu:

    venv\\Scripts\\python perbaiki_tahun.py              <- uji coba, TIDAK menyimpan apa pun
    venv\\Scripts\\python perbaiki_tahun.py --commit     <- sungguhan, menyimpan

Tanpa --commit, apa pun yang terjadi akan dibatalkan di akhir. Uji coba dulu, baca
hasilnya, baru jalankan yang kedua.

Pilihan tambahan:

    --tanpa-gilimanuk    hanya perbaiki "2026.0" dan "Nopember"; id KMP. GILIMANUK
                         dibiarkan apa adanya

Skrip ini tidak menghapus satu baris pun. Kalau ada palang pengaman yang tidak nol,
dia berhenti sendiri dan membatalkan semuanya.
"""

import sys
from pathlib import Path

from sqlalchemy import create_engine

COMMIT = "--commit" in sys.argv
TANPA_C = "--tanpa-gilimanuk" in sys.argv


# --------------------------------------------------------------------------------------
# Sambungan
# --------------------------------------------------------------------------------------
def baca_database_url() -> str:
    env = Path(__file__).resolve().parent / ".env"
    if not env.exists():
        sys.exit(f"Tidak menemukan {env}. Taruh berkas ini di folder backend/ repo.")
    for baris in env.read_text(encoding="utf-8").splitlines():
        if baris.strip().startswith("DATABASE_URL="):
            url = baris.split("=", 1)[1].strip().strip('"').strip("'")
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql+pg8000://", 1)
            elif url.startswith("postgresql://") and "pg8000" not in url:
                url = url.replace("postgresql://", "postgresql+pg8000://", 1)
            return url
    sys.exit("DATABASE_URL tidak ada di .env")


def tabel(conn, sql, judul):
    """Jalankan SELECT lalu cetak hasilnya sebagai tabel sederhana."""
    print(f"\n--- {judul} " + "-" * max(0, 74 - len(judul)))
    hasil = conn.exec_driver_sql(sql)
    kolom = list(hasil.keys())
    baris = [[("" if v is None else str(v)) for v in r] for r in hasil.fetchall()]
    if not baris:
        print("   (kosong)")
        return []
    lebar = [max(len(kolom[i]), *(len(b[i]) for b in baris)) for i in range(len(kolom))]
    print("   " + " | ".join(k.ljust(lebar[i]) for i, k in enumerate(kolom)))
    print("   " + "-+-".join("-" * w for w in lebar))
    for b in baris:
        print("   " + " | ".join(b[i].ljust(lebar[i]) for i in range(len(kolom))))
    return baris


# --------------------------------------------------------------------------------------
# SQL — disalin dari berkas Claude Code, tidak diubah isinya
# --------------------------------------------------------------------------------------
Q_0A = """
SELECT tahun, COUNT(*) AS baris
FROM tabel_katalog_harga GROUP BY tahun ORDER BY tahun
"""

Q_0B = r"""
SELECT tahun, nama_kapal, nama_perusahaan, tipe_perjanjian,
       COUNT(*) AS baris, MIN(id) AS id_awal, MAX(id) AS id_akhir
FROM tabel_katalog_harga
WHERE tahun !~ '^[0-9]{4}$'
GROUP BY tahun, nama_kapal, nama_perusahaan, tipe_perjanjian
ORDER BY tahun, nama_kapal
"""

Q_0C = r"""
SELECT nama_kapal, tahun,
       substring(id FROM '^(.*)-[0-9]+$') AS awalan_id,
       COUNT(*) AS baris, MIN(id) AS id_awal, MAX(id) AS id_akhir
FROM tabel_katalog_harga
WHERE position('-' || tahun || '-' IN id) = 0
GROUP BY nama_kapal, tahun, substring(id FROM '^(.*)-[0-9]+$')
ORDER BY baris DESC
"""

CADANGAN = r"""
CREATE TABLE IF NOT EXISTS cadangan_tahun_rusak AS
SELECT *, now() AS dicadangkan_pada
FROM tabel_katalog_harga
WHERE tahun !~ '^[0-9]{4}$'
   OR position('-' || tahun || '-' IN id) = 0
"""

# Bagian C ikut atau tidak, ditentukan di sini. Sisanya identik.
BAGIAN_C = r"""
    UNION ALL

    SELECT t.id,
           t.tahun,
           t.tahun,
           t.nomor,
           upper(replace(btrim(t.nama_kapal), ' ', '_')) || '-',
           'id tidak sepakat'
    FROM terurai t
    WHERE t.nomor IS NOT NULL
      AND position('-' || t.tahun || '-' IN t.id) = 0
"""

PETA_ID = r"""
CREATE TEMP TABLE peta_id AS
WITH peta(tahun_lama, tahun_baru) AS (
    SELECT DISTINCT tahun, left(tahun, length(tahun) - 2)
    FROM tabel_katalog_harga
    WHERE tahun ~ '^[0-9]+\.0$'
    UNION ALL
    SELECT * FROM (VALUES ('Nopember', '2025')) AS m(tahun_lama, tahun_baru)
),
terurai AS (
    SELECT id, tahun, nama_kapal, substring(id FROM '[0-9]+$') AS nomor
    FROM tabel_katalog_harga
),
kandidat AS (
    SELECT t.id,
           t.tahun                                                     AS tahun_lama,
           p.tahun_baru,
           t.nomor,
           left(t.id, length(t.id) - length(t.tahun) - length(t.nomor) - 1) AS awalan,
           'tahun rusak'                                               AS sebab
    FROM terurai t
    JOIN peta p ON p.tahun_lama = t.tahun
    WHERE t.nomor IS NOT NULL
      AND right(t.id, length(t.tahun) + length(t.nomor) + 2)
          = '-' || t.tahun || '-' || t.nomor
__BAGIAN_C__
),
mulai AS (
    SELECT k.awalan, k.tahun_baru,
           COALESCE(MAX(CAST(substring(t.id FROM '[0-9]+$') AS INT)), 0) AS nomor_terakhir
    FROM (SELECT DISTINCT awalan, tahun_baru FROM kandidat) k
    LEFT JOIN tabel_katalog_harga t
           ON left(t.id, length(k.awalan) + length(k.tahun_baru) + 1)
              = k.awalan || k.tahun_baru || '-'
          AND substring(t.id FROM '[0-9]+$') IS NOT NULL
          AND t.id NOT IN (SELECT id FROM kandidat)
    GROUP BY k.awalan, k.tahun_baru
)
SELECT k.id AS id_lama,
       k.awalan || k.tahun_baru || '-' || lpad(
           (m.nomor_terakhir + ROW_NUMBER() OVER (
                PARTITION BY k.awalan, k.tahun_baru
                ORDER BY CAST(k.nomor AS INT), k.id
           ))::text, 3, '0') AS id_baru,
       k.tahun_lama, k.tahun_baru, k.sebab
FROM kandidat k
JOIN mulai m ON m.awalan = k.awalan AND m.tahun_baru = k.tahun_baru
"""

Q_RENCANA = """
SELECT sebab, tahun_lama, tahun_baru, COUNT(*) AS baris,
       MIN(id_lama) AS contoh_lama, MIN(id_baru) AS contoh_baru
FROM peta_id GROUP BY sebab, tahun_lama, tahun_baru ORDER BY sebab, tahun_lama
"""

Q_PALANG = r"""
SELECT
    (SELECT COUNT(*) FROM peta_id WHERE tahun_baru !~ '^[0-9]{4}$')                 AS tahun_tujuan_janggal,
    (SELECT COUNT(*) FROM peta_id p JOIN tabel_katalog_harga k ON k.id = p.id_baru
      WHERE k.id NOT IN (SELECT id_lama FROM peta_id))                              AS id_baru_sudah_dipakai,
    (SELECT COUNT(*) - COUNT(DISTINCT id_baru) FROM peta_id)                        AS id_baru_kembar,
    (SELECT COUNT(*) FROM tabel_katalog_harga
      WHERE (tahun !~ '^[0-9]{4}$' OR position('-' || tahun || '-' IN id) = 0)
        AND id NOT IN (SELECT id_lama FROM peta_id))                                AS baris_rusak_tak_terpetakan,
    (SELECT COUNT(*) FROM peta_id WHERE id_baru IN (SELECT id_lama FROM peta_id))   AS id_baru_menabrak_id_lama
"""

UPDATE = """
UPDATE tabel_katalog_harga k
SET id = p.id_baru, tahun = p.tahun_baru
FROM peta_id p WHERE k.id = p.id_lama
"""

Q_4B = """
SELECT id, tahun, nama_kapal FROM tabel_katalog_harga
WHERE position('-' || tahun || '-' IN id) = 0
"""

Q_4C = """
SELECT nama_kapal, tahun, COUNT(*) AS baris, MIN(id) AS id_awal, MAX(id) AS id_akhir
FROM tabel_katalog_harga WHERE id IN (SELECT id_baru FROM peta_id)
GROUP BY nama_kapal, tahun ORDER BY nama_kapal, tahun
"""

Q_TOTAL = "SELECT COUNT(*) AS total_baris FROM tabel_katalog_harga"


# --------------------------------------------------------------------------------------
def main():
    mode = "SUNGGUHAN (akan COMMIT)" if COMMIT else "UJI COBA (akan ROLLBACK)"
    print("=" * 80)
    print(f"  Perbaikan tahun & id  —  mode: {mode}")
    if TANPA_C:
        print("  Kelas C (id KMP. GILIMANUK) DILEWATI atas permintaan.")
    print("=" * 80)

    engine = create_engine(baca_database_url())
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            # --- Bagian 0: keadaan sekarang -------------------------------------------
            total_awal = conn.exec_driver_sql(Q_TOTAL).scalar()
            print(f"\nTotal baris sebelum: {total_awal}")
            tabel(conn, Q_0A, "0a. Tahun yang ada sekarang")
            tabel(conn, Q_0B, "0b. Tahun yang bukan 4 digit")
            tabel(conn, Q_0C, "0c. Id yang tidak sepakat dengan kolom tahun")

            # --- Bagian 1: cadangkan --------------------------------------------------
            conn.exec_driver_sql(CADANGAN)
            n_cad = conn.exec_driver_sql(
                "SELECT COUNT(*) FROM cadangan_tahun_rusak"
            ).scalar()
            print(f"\nTabel cadangan_tahun_rusak berisi {n_cad} baris.")
            print("(Catatan: tabel ini ikut hilang kalau transaksinya dibatalkan —")
            print(" cadangan sungguhanmu tetap yang harian dari backup-service.)")

            # --- Bagian 2: susun rencana ----------------------------------------------
            conn.exec_driver_sql(
                PETA_ID.replace("__BAGIAN_C__", "" if TANPA_C else BAGIAN_C)
            )
            tabel(conn, Q_RENCANA, "2a. Rencana perubahan")

            palang = conn.exec_driver_sql(Q_PALANG).mappings().one()
            print("\n--- 2c. Palang pengaman (semuanya HARUS 0) " + "-" * 37)
            gagal = []
            for nama, nilai in palang.items():
                tanda = "OK " if nilai == 0 else "!! "
                print(f"   {tanda}{nama:32s} = {nilai}")
                if nilai != 0:
                    gagal.append(nama)
            if TANPA_C and palang["baris_rusak_tak_terpetakan"] != 0:
                print("\n   (Angka 'baris_rusak_tak_terpetakan' memang tidak nol karena")
                print("    kelas C sengaja dilewati. Itu diharapkan, bukan kegagalan.)")
                gagal = [g for g in gagal if g != "baris_rusak_tak_terpetakan"]
            if gagal:
                trans.rollback()
                sys.exit(
                    "\nBERHENTI. Palang pengaman tidak nol: "
                    + ", ".join(gagal)
                    + "\nTidak ada yang diubah. Tunjukkan keluaran ini sebelum melanjutkan."
                )

            # --- Bagian 3: eksekusi ---------------------------------------------------
            n = conn.exec_driver_sql(UPDATE).rowcount
            print(f"\nUPDATE mengubah {n} baris.")

            # --- Bagian 4: verifikasi, masih di dalam transaksi ------------------------
            tabel(conn, Q_0A, "4a. Tahun setelah perbaikan")
            sisa = tabel(conn, Q_4B, "4b. Id yang masih tidak sepakat (harus kosong)")
            tabel(conn, Q_4C, "4c. Baris yang baru diperbaiki")
            total_akhir = conn.exec_driver_sql(Q_TOTAL).scalar()
            print(f"\nTotal baris sesudah: {total_akhir}  (sebelum: {total_awal})")

            aman = total_akhir == total_awal and (TANPA_C or not sisa)
            if not aman:
                trans.rollback()
                sys.exit(
                    "\nBERHENTI. Verifikasi Bagian 4 tidak bersih. Tidak ada yang diubah."
                )

            # --- Akhir ----------------------------------------------------------------
            if COMMIT:
                trans.commit()
                print("\n" + "=" * 80)
                print("  COMMIT. Perubahan tersimpan permanen.")
                print("=" * 80)
            else:
                trans.rollback()
                print("\n" + "=" * 80)
                print("  ROLLBACK. Tidak ada yang tersimpan — ini cuma uji coba.")
                print("  Kalau semua di atas sudah benar, jalankan lagi dengan --commit")
                print("=" * 80)
        except Exception:
            trans.rollback()
            print("\nGagal — semuanya dibatalkan, tidak ada yang berubah.\n")
            raise


if __name__ == "__main__":
    main()
