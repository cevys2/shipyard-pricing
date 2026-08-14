-- =============================================================================
-- Perbaikan nilai `tahun` yang rusak di tabel_katalog_harga
--   (a) "2026.0" dan sejenisnya -- 764 baris, masuk 12 & 14 Agustus 2026
--   (b) "Nopember"              -- 36 baris MV. BALI HAI II, masuk 31 Juli 2026
--
-- Dua catatan dari hasil Bagian 0 di produksi, 14 Agustus 2026:
--
-- 1. BARIS BERULANG ITU DISENGAJA. KMP. MISHIMA punya ~591 baris untuk laporan docking
--    198 baris, KMP. GILIMANUK ~453 untuk 227. Sudah ditinjau pemilik proyek 14 Agustus:
--    banyak pekerjaan docking memang beruraian sama, dan semuanya data realisasi asli --
--    bukan kecelakaan impor. Jadi skrip ini menggabungkannya ke satu tahun tanpa
--    menghapus apa pun. Kueri 0e-0g di bawah dipertahankan sebagai alat lihat saja.
--
-- 2. ID DAN KOLOM TAHUN TIDAK SEPAKAT di 226 baris KMP. GILIMANUK: kolom tahunnya "2025"
--    tapi id-nya "GILIMANUK-2026-001..226", dan slug-nya "GILIMANUK", bukan
--    "KMP._GILIMANUK" seperti yang dihasilkan `_bulk_create` sekarang. Sudah begitu sejak
--    sebelum cadangan 9 Agustus. Baris-baris itu TIDAK ikut tersentuh Bagian 3 (kolom
--    tahunnya sudah empat digit) -- perbaikannya terpisah di Bagian 5, dan masih menunggu
--    satu jawaban: docking itu 2025 atau 2026.
--
-- JANGAN dijalankan sekaligus. Baca per bagian, jalankan Bagian 0 dulu, lihat hasilnya.
-- Skrip ini MENGUBAH primary key: `id` berbentuk SLUG-TAHUN-NNN, jadi memperbaiki tahun
-- tanpa memperbaiki id akan meninggalkan baris yang id-nya bilang "2026.0" sementara
-- kolom tahunnya bilang "2026" -- dan `_next_ids()` menghitung nomor urut dari id, bukan
-- dari kolom tahun, jadi ketidakcocokan itu akan memecah penomoran kapal tersebut.
--
-- Tidak ada tabel lain yang punya foreign key ke tabel_katalog_harga.id (sudah diperiksa
-- di backend/app/database.py). Satu-satunya jejak id lama ada di `audit_log.detail` --
-- itu catatan sejarah append-only, sengaja TIDAK ikut diubah.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Bagian 0 -- periksa dulu (baca saja, tidak mengubah apa pun)
-- -----------------------------------------------------------------------------

-- 0a. Tahun apa saja yang ada, dan berapa barisnya?
SELECT tahun, COUNT(*) AS baris
FROM tabel_katalog_harga
GROUP BY tahun
ORDER BY tahun;

-- 0b. Kapal mana yang kena, dan kapan barisnya masuk?
SELECT tahun, nama_kapal, nama_perusahaan, tipe_perjanjian,
       COUNT(*) AS baris, MIN(id) AS id_awal, MAX(id) AS id_akhir,
       MIN(created_at)::date AS diinput
FROM tabel_katalog_harga
WHERE tahun ~ '^[0-9]+\.0$' OR tahun !~ '^[0-9]{4}$'
GROUP BY tahun, nama_kapal, nama_perusahaan, tipe_perjanjian
ORDER BY tahun, nama_kapal;

-- 0c. Apakah kapal yang kena SUDAH punya baris di tahun yang benar?
--     Kalau ya, penomoran ulang di Bagian 3 melanjutkan dari nomor terakhir di sana,
--     bukan menabraknya.
SELECT nama_kapal, tahun, COUNT(*) AS baris, MAX(substring(id from '[0-9]+$')) AS nomor_terbesar
FROM tabel_katalog_harga
WHERE nama_kapal IN (
    SELECT nama_kapal FROM tabel_katalog_harga
    WHERE tahun ~ '^[0-9]+\.0$' OR tahun !~ '^[0-9]{4}$'
)
GROUP BY nama_kapal, tahun
ORDER BY nama_kapal, tahun;

-- 0d. Palang pengaman: baris yang id-nya TIDAK memuat "-<tahun>-".
--     Di produksi 14 Agustus ini mengembalikan 226 baris KMP. GILIMANUK -- lihat catatan
--     nomor 2 di kepala berkas dan Bagian 5. Baris-baris itu tidak ikut diubah Bagian 3.
SELECT nama_kapal, tahun,
       substring(id FROM '^(.*)-[0-9]+$') AS awalan_id,
       COUNT(*) AS baris, MIN(id) AS id_awal, MAX(id) AS id_akhir
FROM tabel_katalog_harga
WHERE position('-' || tahun || '-' IN id) = 0
GROUP BY nama_kapal, tahun, substring(id FROM '^(.*)-[0-9]+$')
ORDER BY baris DESC;

-- 0e. Sekadar potret: berapa lipat baris terhadap uraian uniknya per kapal.
--     Angka besar di sini sudah ditinjau dan diterima (lihat catatan 1 di kepala berkas).
SELECT nama_kapal, tahun,
       COUNT(*)                             AS baris,
       COUNT(DISTINCT uraian_pekerjaan)     AS uraian_unik,
       ROUND(COUNT(*)::numeric
             / NULLIF(COUNT(DISTINCT uraian_pekerjaan), 0), 2) AS lipat
FROM tabel_katalog_harga
WHERE nama_kapal IN ('KMP. MISHIMA', 'KMP. GILIMANUK', 'KMP. NARAYA', 'MV. BALI HAI II')
GROUP BY nama_kapal, tahun
ORDER BY nama_kapal, tahun;

-- 0f. Uraian yang persis sama DAN harga yang persis sama, di kapal + tahun yang sama.
--     Baris lanjutan/berulang di laporan docking memang ada (parser sendiri
--     memperingatkannya), jadi angka kecil itu wajar. Yang dicari: pengulangan masif.
SELECT nama_kapal, tahun, uraian_pekerjaan, harga_satuan, COUNT(*) AS kali,
       string_agg(id, ', ' ORDER BY id) AS id_terkait
FROM tabel_katalog_harga
WHERE nama_kapal IN ('KMP. MISHIMA', 'KMP. GILIMANUK', 'KMP. NARAYA')
GROUP BY nama_kapal, tahun, uraian_pekerjaan, harga_satuan
HAVING COUNT(*) > 1
ORDER BY kali DESC, nama_kapal
LIMIT 25;

-- 0g. Apakah isi "2026.0" itu salinan dari yang sudah ada di "2026"?
--     Kalau banyak barisnya berpasangan, penggabungan di Bagian 3 akan melipatgandakannya.
SELECT lama.nama_kapal,
       COUNT(*) AS pasangan_uraian_dan_harga_yang_sama
FROM (SELECT DISTINCT nama_kapal, uraian_pekerjaan, harga_satuan
      FROM tabel_katalog_harga WHERE tahun ~ '^[0-9]{4}$') lama
JOIN (SELECT DISTINCT nama_kapal, uraian_pekerjaan, harga_satuan
      FROM tabel_katalog_harga WHERE tahun ~ '^[0-9]+\.0$') baru
  ON  baru.nama_kapal       = lama.nama_kapal
  AND baru.uraian_pekerjaan = lama.uraian_pekerjaan
  AND baru.harga_satuan     = lama.harga_satuan
GROUP BY lama.nama_kapal;


-- -----------------------------------------------------------------------------
-- Bagian 1 -- peta tahun yang benar
--
-- Yang berbentuk "2026.0" ditangani otomatis (buang ".0"). Yang bukan angka harus
-- disebut satu per satu -- tidak ada cara menebaknya dari data. Sudah diisi di Bagian 2:
--
--   'Nopember' -> '2025'
--
-- Kalau mau menjalankan "Nopember" saja tanpa yang ".0": di Bagian 2, komentari cabang
-- otomatis ".0" berikut `UNION ALL`-nya, sisakan baris VALUES.
--
-- Dasarnya berkas sumbernya sendiri, "Realisasi MV. Bali Hai II 2025 - 370.xlsx":
-- selnya berbunyi  PERIODE DOCKING | : | Nopember | 2025  -- bulan dan tahun di DUA sel
-- terpisah, dan `find_label_value()` mengambil sel non-kosong PERTAMA di sebelah kanan,
-- jadi yang tersimpan cuma "Nopember". Cocokkan sekali lagi dengan berkas aslinya
-- sebelum menjalankan Bagian 3 -- setelah COMMIT, id-nya permanen.
-- -----------------------------------------------------------------------------


-- -----------------------------------------------------------------------------
-- Bagian 2 -- rencana perubahan, disimpan ke tabel sementara
--
-- Jalankan seluruh blok BEGIN ... COMMIT ini dalam SATU sesi psql. Tabel sementaranya
-- hilang saat sesi ditutup.
-- -----------------------------------------------------------------------------

BEGIN;

-- 2a. Salinan cadangan baris yang akan disentuh -- di luar transaksi ini pun tetap ada.
--     Hapus sendiri kalau sudah yakin: DROP TABLE cadangan_tahun_rusak;
CREATE TABLE IF NOT EXISTS cadangan_tahun_rusak AS
SELECT *, now() AS dicadangkan_pada
FROM tabel_katalog_harga
WHERE tahun ~ '^[0-9]+\.0$' OR tahun !~ '^[0-9]{4}$';

CREATE TEMP TABLE peta_id AS
WITH peta(tahun_lama, tahun_baru) AS (
    -- otomatis: "2026.0" -> "2026"
    SELECT DISTINCT tahun, left(tahun, length(tahun) - 2)
    FROM tabel_katalog_harga
    WHERE tahun ~ '^[0-9]+\.0$'
    UNION ALL
    -- manual: tahun yang bukan angka (lihat Bagian 1 untuk dasarnya)
    SELECT * FROM (VALUES ('Nopember', '2025')) AS m(tahun_lama, tahun_baru)
),
rusak AS (
    SELECT k.id,
           k.tahun                        AS tahun_lama,
           p.tahun_baru,
           substring(k.id FROM '[0-9]+$') AS nomor
    FROM tabel_katalog_harga k
    JOIN peta p ON p.tahun_lama = k.tahun
),
-- `awalan` = bagian id sebelum tahun, sudah termasuk tanda hubungnya, mis.
-- "MV._BALI_HAI_II-". Dipotong lewat panjang, bukan split_part, karena nama kapal
-- boleh memuat tanda hubung sendiri.
terurai AS (
    SELECT r.*,
           left(r.id, length(r.id) - length(r.tahun_lama) - length(r.nomor) - 1) AS awalan
    FROM rusak r
    WHERE r.nomor IS NOT NULL
      AND right(r.id, length(r.tahun_lama) + length(r.nomor) + 2)
          = '-' || r.tahun_lama || '-' || r.nomor
),
-- Nomor tertinggi yang SUDAH terpakai di tahun tujuan, supaya penomoran ulang
-- melanjutkan, bukan menabrak. `left(...) =` dipakai, bukan LIKE: slug nama kapal
-- penuh "_", dan di LIKE "_" berarti "satu karakter apa saja".
mulai AS (
    SELECT t.awalan, t.tahun_baru,
           COALESCE(MAX(CAST(substring(k.id FROM '[0-9]+$') AS INT)), 0) AS nomor_terakhir
    FROM (SELECT DISTINCT awalan, tahun_baru FROM terurai) t
    LEFT JOIN tabel_katalog_harga k
           ON left(k.id, length(t.awalan) + length(t.tahun_baru) + 1)
              = t.awalan || t.tahun_baru || '-'
          AND substring(k.id FROM '[0-9]+$') IS NOT NULL
    GROUP BY t.awalan, t.tahun_baru
)
SELECT t.id                                        AS id_lama,
       t.awalan || t.tahun_baru || '-' || lpad(
           (m.nomor_terakhir + ROW_NUMBER() OVER (
                PARTITION BY t.awalan, t.tahun_baru
                ORDER BY CAST(t.nomor AS INT)
           ))::text, 3, '0')                       AS id_baru,
       t.tahun_lama,
       t.tahun_baru
FROM terurai t
JOIN mulai m ON m.awalan = t.awalan AND m.tahun_baru = t.tahun_baru;

-- 2b. Lihat rencananya sebelum apa pun ditulis.
SELECT * FROM peta_id ORDER BY id_lama;

-- 2c. Tiga palang pengaman. KETIGANYA harus 0.
SELECT
    (SELECT COUNT(*) FROM peta_id WHERE tahun_baru !~ '^[0-9]{4}$')              AS tahun_baru_tidak_wajar,
    (SELECT COUNT(*) FROM peta_id p JOIN tabel_katalog_harga k ON k.id = p.id_baru
                                    WHERE k.id NOT IN (SELECT id_lama FROM peta_id)) AS id_baru_sudah_dipakai,
    (SELECT COUNT(*) FROM tabel_katalog_harga
      WHERE (tahun ~ '^[0-9]+\.0$' OR tahun !~ '^[0-9]{4}$')
        AND id NOT IN (SELECT id_lama FROM peta_id))                            AS baris_rusak_tidak_terpetakan;


-- -----------------------------------------------------------------------------
-- Bagian 3 -- eksekusi
--
-- Kalau Bagian 2c belum bertiga-nol, jalankan ROLLBACK; dan berhenti.
-- -----------------------------------------------------------------------------

UPDATE tabel_katalog_harga k
SET id    = p.id_baru,
    tahun = p.tahun_baru
FROM peta_id p
WHERE k.id = p.id_lama;

-- COMMIT;   -- <<< buka baris ini setelah Bagian 4 di bawah terlihat benar
-- ROLLBACK; -- <<< atau ini kalau ada yang janggal


-- -----------------------------------------------------------------------------
-- Bagian 4 -- verifikasi (jalankan SEBELUM COMMIT, masih di transaksi yang sama)
-- -----------------------------------------------------------------------------

-- 4a. Tinggal tahun empat digit, dan jumlah barisnya utuh.
SELECT tahun, COUNT(*) AS baris FROM tabel_katalog_harga GROUP BY tahun ORDER BY tahun;

-- 4b. Id dan kolom tahun kembali sepakat. Harus kosong.
SELECT id, tahun FROM tabel_katalog_harga WHERE position('-' || tahun || '-' IN id) = 0;

-- 4c. Tidak ada nomor kembar dalam satu kapal + tahun. Harus kosong.
SELECT nama_kapal, tahun, substring(id FROM '[0-9]+$') AS nomor, COUNT(*)
FROM tabel_katalog_harga
GROUP BY nama_kapal, tahun, substring(id FROM '[0-9]+$')
HAVING COUNT(*) > 1;

-- 4d. Yang tadinya rusak sekarang duduk di tahun yang benar.
SELECT nama_kapal, tahun, COUNT(*) AS baris, MIN(id) AS id_awal, MAX(id) AS id_akhir
FROM tabel_katalog_harga
WHERE id IN (SELECT id_baru FROM peta_id)
GROUP BY nama_kapal, tahun;


-- -----------------------------------------------------------------------------
-- Bagian 5 -- 226 baris KMP. GILIMANUK yang id dan kolom tahunnya tidak sepakat
--
-- MASALAH TERPISAH, bukan bagian dari bug ".0". Jangan dijalankan bersama Bagian 3.
--
-- Keadaannya: nama_kapal "KMP. GILIMANUK", kolom tahun "2025", tapi id-nya
-- "GILIMANUK-2026-001..226" -- tahunnya beda, dan slug-nya tanpa "KMP._".
-- Sudah begitu sejak sebelum cadangan 9 Agustus, jadi bukan oleh-oleh impor minggu ini.
--
-- Satu pertanyaan yang harus dijawab lebih dulu, dan jawabannya tidak ada di dalam data:
-- docking itu 2025 atau 2026? Kolom tahun dan id bilang hal yang berbeda, dan filter
-- "Tahun" di dashboard mengikuti kolom tahun, bukan id.
--
-- Setelah dijawab, baru template di bawah dipakai. Diberikan sebagai komentar dengan
-- sengaja -- angka tahunnya harus diketik sadar, bukan ikut jalan.
--
-- BEGIN;
--
-- CREATE TABLE cadangan_gilimanuk AS
-- SELECT *, now() AS dicadangkan_pada FROM tabel_katalog_harga
-- WHERE position('-' || tahun || '-' IN id) = 0;
--
-- WITH sasaran AS (
--     SELECT id,
--            substring(id FROM '[0-9]+$')                       AS nomor,
--            upper(replace(btrim(nama_kapal), ' ', '_'))        AS slug,
--            '2025'                                            AS tahun_benar  -- <<< ISI
--     FROM tabel_katalog_harga
--     WHERE position('-' || tahun || '-' IN id) = 0
-- ),
-- mulai AS (
--     SELECT s.slug, s.tahun_benar,
--            COALESCE(MAX(CAST(substring(k.id FROM '[0-9]+$') AS INT)), 0) AS nomor_terakhir
--     FROM (SELECT DISTINCT slug, tahun_benar FROM sasaran) s
--     LEFT JOIN tabel_katalog_harga k
--            ON left(k.id, length(s.slug) + length(s.tahun_benar) + 2)
--               = s.slug || '-' || s.tahun_benar || '-'
--     GROUP BY s.slug, s.tahun_benar
-- )
-- UPDATE tabel_katalog_harga k
-- SET id    = s.slug || '-' || s.tahun_benar || '-' || lpad(
--                 (m.nomor_terakhir + ROW_NUMBER() OVER (PARTITION BY s.slug
--                                                        ORDER BY CAST(s.nomor AS INT)))::text, 3, '0'),
--     tahun = s.tahun_benar
-- FROM sasaran s JOIN mulai m ON m.slug = s.slug AND m.tahun_benar = s.tahun_benar
-- WHERE k.id = s.id;
--
-- SELECT id, tahun FROM tabel_katalog_harga WHERE position('-' || tahun || '-' IN id) = 0;
-- -- COMMIT;
