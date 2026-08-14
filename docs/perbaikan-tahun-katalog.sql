-- =============================================================================
-- Perbaikan `tahun` dan `id` di tabel_katalog_harga
--
-- Tiga kelas kerusakan, satu transaksi, tanpa menghapus satu baris pun:
--
--   A. tahun "2026.0"  -> "2026"   -- 764 baris, masuk 12 & 14 Agustus 2026 lewat impor
--                                     Laporan Docking. Sel tahun tersimpan sebagai angka,
--                                     terbaca float, str(2026.0) -> "2026.0". Sumbernya
--                                     sudah ditambal di commit a9d1848 (find_label_value).
--   B. tahun "Nopember" -> "2025"  -- 36 baris MV. BALI HAI II, masuk 31 Juli 2026.
--                                     Sel aslinya berbunyi
--                                     PERIODE DOCKING | : | Nopember | 2025
--                                     -- bulan dan tahun di DUA sel terpisah, dan parser
--                                     mengambil sel pertama di sebelah kanan.
--                                     Dasarnya berkas "Realisasi MV. Bali Hai II 2025 -
--                                     370.xlsx". Cocokkan sekali lagi sebelum COMMIT.
--   C. id tidak sepakat dengan kolom tahun -- 226 baris KMP. GILIMANUK: kolom tahunnya
--                                     "2025" tapi id-nya "GILIMANUK-2026-001..226", dan
--                                     slug-nya tanpa awalan "KMP._". Sudah begitu sejak
--                                     sebelum cadangan 9 Agustus. Diputuskan pemilik
--                                     proyek 14 Agustus: KOLOM TAHUN yang benar, jadi
--                                     id-nya yang ditulis ulang mengikuti tahun 2025.
--
-- Kenapa id ikut ditulis ulang, bukan cuma kolom tahunnya: `id` adalah primary key
-- berbentuk SLUG-TAHUN-NNN. Kalau kolom tahun diperbaiki tapi id dibiarkan, `_next_ids()`
-- -- yang menghitung nomor urut dari id, bukan dari kolom tahun -- akan mulai lagi dari
-- 001 pada impor berikutnya untuk kapal itu.
--
-- Penomoran ulang MELANJUTKAN nomor terakhir yang sudah terpakai di tahun tujuan, jadi
-- tidak ada baris yang saling menimpa. Tidak ada tabel lain yang punya foreign key ke
-- tabel_katalog_harga.id (diperiksa di backend/app/database.py); satu-satunya jejak id
-- lama ada di `audit_log.detail`, dan itu catatan sejarah append-only yang sengaja
-- dibiarkan apa adanya.
--
-- Baris beruraian sama TIDAK dianggap masalah di sini -- sudah ditinjau 14 Agustus, itu
-- data realisasi asli. Skrip ini tidak menghapus apa pun.
--
-- Cara pakai: satu sesi psql, jalankan per bagian, baca hasil tiap bagian sebelum lanjut.
-- `COMMIT` di Bagian 4 sengaja masih dikomentari.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Bagian 0 -- periksa dulu (baca saja)
-- -----------------------------------------------------------------------------

-- 0a. Tahun apa saja yang ada sekarang?
SELECT tahun, COUNT(*) AS baris
FROM tabel_katalog_harga
GROUP BY tahun
ORDER BY tahun;

-- 0b. Kelas A dan B -- kapal mana, kapan masuk?
SELECT tahun, nama_kapal, nama_perusahaan, tipe_perjanjian,
       COUNT(*) AS baris, MIN(id) AS id_awal, MAX(id) AS id_akhir,
       MIN(created_at)::date AS diinput
FROM tabel_katalog_harga
WHERE tahun !~ '^[0-9]{4}$'
GROUP BY tahun, nama_kapal, nama_perusahaan, tipe_perjanjian
ORDER BY tahun, nama_kapal;

-- 0c. Kelas C -- id yang tidak memuat "-<tahun>-".
SELECT nama_kapal, tahun,
       substring(id FROM '^(.*)-[0-9]+$') AS awalan_id,
       COUNT(*) AS baris, MIN(id) AS id_awal, MAX(id) AS id_akhir
FROM tabel_katalog_harga
WHERE position('-' || tahun || '-' IN id) = 0
GROUP BY nama_kapal, tahun, substring(id FROM '^(.*)-[0-9]+$')
ORDER BY baris DESC;

-- 0d. Apakah tahun tujuan sudah berisi baris lain? Penomoran ulang melanjutkan dari sini.
SELECT nama_kapal, tahun, COUNT(*) AS baris,
       MAX(CAST(substring(id FROM '[0-9]+$') AS INT)) AS nomor_terbesar
FROM tabel_katalog_harga
WHERE nama_kapal IN (
    SELECT nama_kapal FROM tabel_katalog_harga
    WHERE tahun !~ '^[0-9]{4}$' OR position('-' || tahun || '-' IN id) = 0
)
GROUP BY nama_kapal, tahun
ORDER BY nama_kapal, tahun;


-- -----------------------------------------------------------------------------
-- Bagian 1 -- cadangkan
-- -----------------------------------------------------------------------------

BEGIN;

-- Bertahan di luar transaksi ini. Hapus sendiri kalau sudah yakin:
--   DROP TABLE cadangan_tahun_rusak;
CREATE TABLE IF NOT EXISTS cadangan_tahun_rusak AS
SELECT *, now() AS dicadangkan_pada
FROM tabel_katalog_harga
WHERE tahun !~ '^[0-9]{4}$'
   OR position('-' || tahun || '-' IN id) = 0;


-- -----------------------------------------------------------------------------
-- Bagian 2 -- susun rencananya di tabel sementara, jangan tulis apa pun dulu
-- -----------------------------------------------------------------------------

CREATE TEMP TABLE peta_id AS
WITH peta(tahun_lama, tahun_baru) AS (
    -- kelas A, otomatis: "2026.0" -> "2026"
    SELECT DISTINCT tahun, left(tahun, length(tahun) - 2)
    FROM tabel_katalog_harga
    WHERE tahun ~ '^[0-9]+\.0$'
    UNION ALL
    -- kelas B, manual: tahun yang bukan angka sama sekali
    SELECT * FROM (VALUES ('Nopember', '2025')) AS m(tahun_lama, tahun_baru)
),
terurai AS (
    SELECT id, tahun, nama_kapal,
           substring(id FROM '[0-9]+$') AS nomor
    FROM tabel_katalog_harga
),
kandidat AS (
    -- A + B: kolom tahun yang rusak; id-nya sendiri konsisten dengan kolom tahun itu.
    -- `awalan` = bagian id sebelum tahun, sudah termasuk tanda hubungnya, mis.
    -- "MV._BALI_HAI_II-". Dipotong lewat panjang, bukan split_part, karena nama kapal
    -- boleh memuat tanda hubung sendiri (mis. KMP. RO-RO 2000).
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

    UNION ALL

    -- C: kolom tahunnya yang benar, id-nya yang salah. Slug disusun ulang dari
    -- nama_kapal dengan aturan yang sama dengan `_bulk_create`, supaya penomoran impor
    -- berikutnya untuk kapal ini menyambung, bukan mulai lagi dari 001.
    SELECT t.id,
           t.tahun,
           t.tahun,
           t.nomor,
           upper(replace(btrim(t.nama_kapal), ' ', '_')) || '-',
           'id tidak sepakat'
    FROM terurai t
    WHERE t.nomor IS NOT NULL
      AND position('-' || t.tahun || '-' IN t.id) = 0
),
mulai AS (
    -- Nomor tertinggi yang SUDAH terpakai di awalan tujuan. `left(...) =` dipakai, bukan
    -- LIKE: slug nama kapal penuh "_", dan di LIKE "_" berarti "satu karakter apa saja".
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
SELECT k.id                                        AS id_lama,
       k.awalan || k.tahun_baru || '-' || lpad(
           (m.nomor_terakhir + ROW_NUMBER() OVER (
                PARTITION BY k.awalan, k.tahun_baru
                ORDER BY CAST(k.nomor AS INT), k.id
           ))::text, 3, '0')                       AS id_baru,
       k.tahun_lama,
       k.tahun_baru,
       k.sebab
FROM kandidat k
JOIN mulai m ON m.awalan = k.awalan AND m.tahun_baru = k.tahun_baru;

-- 2a. Ringkasan rencananya.
SELECT sebab, tahun_lama, tahun_baru, COUNT(*) AS baris,
       MIN(id_lama) AS contoh_lama, MIN(id_baru) AS contoh_baru
FROM peta_id
GROUP BY sebab, tahun_lama, tahun_baru
ORDER BY sebab, tahun_lama;

-- 2b. Rinciannya, kalau mau dilihat satu per satu.
-- SELECT * FROM peta_id ORDER BY id_baru;

-- 2c. Empat palang pengaman. KEEMPATNYA harus 0.
SELECT
    -- tahun tujuan harus empat digit
    (SELECT COUNT(*) FROM peta_id WHERE tahun_baru !~ '^[0-9]{4}$')                  AS tahun_tujuan_janggal,
    -- id baru tidak boleh menabrak id yang tidak ikut berubah
    (SELECT COUNT(*) FROM peta_id p
      JOIN tabel_katalog_harga k ON k.id = p.id_baru
     WHERE k.id NOT IN (SELECT id_lama FROM peta_id))                                AS id_baru_sudah_dipakai,
    -- id baru tidak boleh kembar sesama isi peta
    (SELECT COUNT(*) - COUNT(DISTINCT id_baru) FROM peta_id)                         AS id_baru_kembar,
    -- semua baris rusak harus ikut terpetakan, tidak ada yang tertinggal diam-diam
    (SELECT COUNT(*) FROM tabel_katalog_harga
      WHERE (tahun !~ '^[0-9]{4}$' OR position('-' || tahun || '-' IN id) = 0)
        AND id NOT IN (SELECT id_lama FROM peta_id))                                 AS baris_rusak_tak_terpetakan;

-- 2d. Palang kelima: kalau ada id baru yang kebetulan sama dengan id lama milik baris
--     LAIN yang juga sedang diubah, UPDATE satu perintah bisa tabrakan di tengah jalan.
--     Harus 0. Kalau tidak 0, perlu dua tahap lewat id sementara -- jangan dipaksakan.
SELECT COUNT(*) AS id_baru_menabrak_id_lama
FROM peta_id WHERE id_baru IN (SELECT id_lama FROM peta_id);


-- -----------------------------------------------------------------------------
-- Bagian 3 -- eksekusi
--
-- Kalau 2c belum berempat-nol atau 2d belum nol: ROLLBACK; lalu berhenti.
-- -----------------------------------------------------------------------------

UPDATE tabel_katalog_harga k
SET id    = p.id_baru,
    tahun = p.tahun_baru
FROM peta_id p
WHERE k.id = p.id_lama;


-- -----------------------------------------------------------------------------
-- Bagian 4 -- verifikasi, MASIH di transaksi yang sama, SEBELUM commit
-- -----------------------------------------------------------------------------

-- 4a. Tinggal tahun empat digit, dan jumlah barisnya utuh.
SELECT tahun, COUNT(*) AS baris FROM tabel_katalog_harga GROUP BY tahun ORDER BY tahun;

-- 4b. Id dan kolom tahun sepakat di seluruh tabel. HARUS KOSONG.
SELECT id, tahun, nama_kapal FROM tabel_katalog_harga
WHERE position('-' || tahun || '-' IN id) = 0;

-- 4c. Hasil akhir baris yang tadi diperbaiki.
SELECT nama_kapal, tahun, COUNT(*) AS baris, MIN(id) AS id_awal, MAX(id) AS id_akhir
FROM tabel_katalog_harga
WHERE id IN (SELECT id_baru FROM peta_id)
GROUP BY nama_kapal, tahun
ORDER BY nama_kapal, tahun;

-- 4d. CATATAN, bukan kegagalan: kapal+tahun yang id-nya terbelah jadi lebih dari satu
--     keluarga awalan. KMP. MISHIMA 2026 akan muncul di sini -- 197 baris lamanya
--     ber-id "MISHIMA-2026-*" (slug gaya lama, tanpa "KMP._") sementara 394 baris yang
--     baru diperbaiki ber-id "KMP._MISHIMA-2026-*". Keduanya sah dan tidak bentrok;
--     `_next_ids()` cuma melihat keluarga yang cocok dengan slug sekarang. Dibiarkan
--     karena di luar tiga kelas yang diminta -- catat saja kalau mau dirapikan nanti.
SELECT nama_kapal, tahun,
       COUNT(DISTINCT left(id, length(id) - length(substring(id FROM '[0-9]+$')))) AS keluarga_id,
       COUNT(*) AS baris
FROM tabel_katalog_harga
GROUP BY nama_kapal, tahun
HAVING COUNT(DISTINCT left(id, length(id) - length(substring(id FROM '[0-9]+$')))) > 1
ORDER BY baris DESC;

-- COMMIT;    -- <<< buka ini kalau 4a-4c sudah benar
-- ROLLBACK;  -- <<< atau ini kalau ada yang janggal
