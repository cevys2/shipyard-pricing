-- Seed kategori pekerjaan + alias. Disepakati VP marketing, 2026.
-- Idempoten: aman dijalankan berulang.
--
-- CATATAN: berkas ini ARSIP, bukan yang dijalankan aplikasi. Root service backend di
-- Railway adalah /backend, jadi docs/ tidak ikut ke dalam container dan berkas ini tidak
-- akan ada di sana saat start. Yang benar-benar dijalankan adalah `backend/app/seed_kategori.py`
-- lewat `ensure_kategori_table()`, dengan isi peta yang identik (dijaga oleh
-- tests/test_kategori.py yang membandingkannya dengan docs/final_peta.json).
--
-- Satu perbedaan yang disengaja di kode: alias memakai
--   ON CONFLICT (alias) DO UPDATE SET kategori_id = EXCLUDED.kategori_id
-- bukan DO NOTHING. Dengan DO NOTHING, mengubah kategori sebuah alias di seed tidak akan
-- pernah berlaku di database yang sudah terisi -- diam, tanpa error. Asumsi K-A1
-- ("ubah 1 baris alias") mensyaratkan perubahan itu benar-benar berlaku.

INSERT INTO kategori (nama, urutan) VALUES ('PIPA - PIPA', 10)
  ON CONFLICT (nama) DO UPDATE SET urutan = EXCLUDED.urutan;
INSERT INTO kategori (nama, urutan) VALUES ('REPLATING', 20)
  ON CONFLICT (nama) DO UPDATE SET urutan = EXCLUDED.urutan;
INSERT INTO kategori (nama, urutan) VALUES ('PELAYANAN UMUM', 30)
  ON CONFLICT (nama) DO UPDATE SET urutan = EXCLUDED.urutan;
INSERT INTO kategori (nama, urutan) VALUES ('PERAWATAN LAMBUNG', 40)
  ON CONFLICT (nama) DO UPDATE SET urutan = EXCLUDED.urutan;
INSERT INTO kategori (nama, urutan) VALUES ('KEMUDI, PROPELLER & POROS', 50)
  ON CONFLICT (nama) DO UPDATE SET urutan = EXCLUDED.urutan;
INSERT INTO kategori (nama, urutan) VALUES ('SEA CHEST & VALVE', 60)
  ON CONFLICT (nama) DO UPDATE SET urutan = EXCLUDED.urutan;
INSERT INTO kategori (nama, urutan) VALUES ('DOCKING & UNDOCKING', 70)
  ON CONFLICT (nama) DO UPDATE SET urutan = EXCLUDED.urutan;
INSERT INTO kategori (nama, urutan) VALUES ('KONSTRUKSI', 80)
  ON CONFLICT (nama) DO UPDATE SET urutan = EXCLUDED.urutan;
INSERT INTO kategori (nama, urutan) VALUES ('JANGKAR & RANTAI JANGKAR', 90)
  ON CONFLICT (nama) DO UPDATE SET urutan = EXCLUDED.urutan;
INSERT INTO kategori (nama, urutan) VALUES ('TANGKI', 100)
  ON CONFLICT (nama) DO UPDATE SET urutan = EXCLUDED.urutan;
INSERT INTO kategori (nama, urutan) VALUES ('LAIN-LAIN', 110)
  ON CONFLICT (nama) DO UPDATE SET urutan = EXCLUDED.urutan;

-- PIPA - PIPA  (10 alias)
INSERT INTO kategori_alias (kategori_id, alias)
SELECT id, x FROM kategori, unnest(ARRAY[
    'PEKERJAAN PIPA',
    'PEKERJAAN PIPA-PIPA',
    'PEKERJAAN TAMBAHAN PIPA- PIPA',
    'PIPA',
    'PIPA - PIPA',
    'PIPA - PIPA (PIPA YARD SUPPLY)',
    'PIPA- PIPA',
    'PIPA-PIPA',
    'PIPA-PIPA DIKAMAR MESIN DAN DECK (BERDASARKAN RL YANG DIKIRIM)',
    'PIPING'
]) AS x WHERE nama = 'PIPA - PIPA'
ON CONFLICT (alias) DO NOTHING;

-- REPLATING  (3 alias)
INSERT INTO kategori_alias (kategori_id, alias)
SELECT id, x FROM kategori, unnest(ARRAY[
    'PEKERJAAN REPLATING',
    'PEKERJAAN REPLATING PLAT',
    'REPLATING'
]) AS x WHERE nama = 'REPLATING'
ON CONFLICT (alias) DO NOTHING;

-- PELAYANAN UMUM  (7 alias)
INSERT INTO kategori_alias (kategori_id, alias)
SELECT id, x FROM kategori, unnest(ARRAY[
    'GENERAL SERVICE',
    'GENERAL SERVICES',
    'PELAYANAN UMUM',
    'PELAYANAN UMUM ( GENERAL SERVICES )',
    'PELAYANAN UMUM (GENERAL SERVICES)',
    'PELAYANAN UMUM KAPAL ( GENERAL SERVICES )',
    'UMUM'
]) AS x WHERE nama = 'PELAYANAN UMUM'
ON CONFLICT (alias) DO NOTHING;

-- PERAWATAN LAMBUNG  (10 alias)
INSERT INTO kategori_alias (kategori_id, alias)
SELECT id, x FROM kategori, unnest(ARRAY[
    'ATAS GARIS AIR',
    'BAGIAN LAMBUNG',
    'HULL CLEANING & PAINTING',
    'HULL MAINTENANCE',
    'PERAWATAN LAMBUNG',
    'PERAWATAN LAMBUNG ( BGA )',
    'PERAWATAN LAMBUNG ( BGA ) DAN SUPERSTRUKTUR',
    'PERAWATAN LAMBUNG (BGA)',
    'PERAWATAN LAMBUNG (HULL)',
    'PERAWATAN LAMBUNG KAPAL'
]) AS x WHERE nama = 'PERAWATAN LAMBUNG'
ON CONFLICT (alias) DO NOTHING;

-- KEMUDI, PROPELLER & POROS  (12 alias)
INSERT INTO kategori_alias (kategori_id, alias)
SELECT id, x FROM kategori, unnest(ARRAY[
    'KEMUDI, PROPELLER & POROS',
    'KEMUDI, PROPELLER, TAIL SHAFT',
    'KEMUDI, PROPELLER, TAIL SHAFT DAN STERN TUBE',
    'KEMUDI, PROPELLER, TAIL SHAFT, STERN TUBE',
    'PROPELLER & SHAFTING',
    'PROPELLER SHAFTING, RUDDER & RAMPDOOR',
    'PROPULSION SYSTEM',
    'RUDDER & RUDDER STOCK',
    'SISTEM PROPULSI',
    'TAIL SAHFT, PROPELLER, RUDDER DAN STERN BUSH',
    'TAIL SHAFT, PROPELLER, RUDDER & STERN BUSH',
    'VOID KEMUDI'
]) AS x WHERE nama = 'KEMUDI, PROPELLER & POROS'
ON CONFLICT (alias) DO NOTHING;

-- SEA CHEST & VALVE  (7 alias)
INSERT INTO kategori_alias (kategori_id, alias)
SELECT id, x FROM kategori, unnest(ARRAY[
    'KRAN-KRAN',
    'SEA CHEST',
    'SEA CHEST & SEA VALVE',
    'SEA CHEST & VALVE',
    'SEA CHEST DAN SEA VALVE',
    'SEA CHEST, SEA VALVE & OVER BOARD',
    'VALVE-VALVE'
]) AS x WHERE nama = 'SEA CHEST & VALVE'
ON CONFLICT (alias) DO NOTHING;

-- DOCKING & UNDOCKING  (3 alias)
INSERT INTO kategori_alias (kategori_id, alias)
SELECT id, x FROM kategori, unnest(ARRAY[
    'DOCKING & UNDOCKING',
    'DOCKING AND UNDOCKING',
    'DOCKING DAN UNDOCKING'
]) AS x WHERE nama = 'DOCKING & UNDOCKING'
ON CONFLICT (alias) DO NOTHING;

-- KONSTRUKSI  (2 alias)
INSERT INTO kategori_alias (kategori_id, alias)
SELECT id, x FROM kategori, unnest(ARRAY[
    'KONSTRUKSI',
    'PEKERJAAN KONSTRUKSI'
]) AS x WHERE nama = 'KONSTRUKSI'
ON CONFLICT (alias) DO NOTHING;

-- JANGKAR & RANTAI JANGKAR  (5 alias)
INSERT INTO kategori_alias (kategori_id, alias)
SELECT id, x FROM kategori, unnest(ARRAY[
    'JANGKAR & RANTAI JANGKAR',
    'JANGKAR, RANTAI JANGKAR & CERUK JANGKAR',
    'JANGKAR, RANTAI JANGKAR DAN CERUK JANGKAR',
    'JANGKAR, RANTAI JANGKAR DAN CERUK JANGKAR ( RANTAI = 40 MM , KANAN = 8 SEGEL, KIRI = 7 SEGEL )',
    'RANTAI JANGKAR DAN CERUK'
]) AS x WHERE nama = 'JANGKAR & RANTAI JANGKAR'
ON CONFLICT (alias) DO NOTHING;

-- TANGKI  (6 alias)
INSERT INTO kategori_alias (kategori_id, alias)
SELECT id, x FROM kategori, unnest(ARRAY[
    'CLEANING',
    'PERAWATAN TANGKI-TANGKI',
    'TANGKI',
    'TANGKI - TANGKI',
    'TANGKI-TANGKI',
    'TANK CLEANING'
]) AS x WHERE nama = 'TANGKI'
ON CONFLICT (alias) DO NOTHING;

-- LAIN-LAIN  (18 alias)
INSERT INTO kategori_alias (kategori_id, alias)
SELECT id, x FROM kategori, unnest(ARRAY[
    'ADDITIONAL WORK',
    'KAMAR MESIN',
    'LAIN - LAIN',
    'LAIN- LAIN',
    'LAIN-LAIN',
    'MEKANIK',
    'MEKANIKAL',
    'OTHERS',
    'PEKERJAAN ACCOMODATION PASSANGER DECK (NON REPLATING)',
    'PEKERJAAN BENGKEL',
    'PEKERJAAN DI CARDECK DAN WINCH DECK (NON REPLATING)',
    'PEKERJAAN DI KAMAR MESIN (NON REPLATING)',
    'PEKERJAAN DI RAMPDOOR',
    'PEKERJAAN LISTRIK',
    'PEKERJAAN NAVIGATION DECK (NON REPLATING)',
    'PEKERJAAN TAMBAHAN',
    'PEKERJAAN TOP DECK (NON REPLATING)',
    'ULTRASONIC TEST DAN NDT'
]) AS x WHERE nama = 'LAIN-LAIN'
ON CONFLICT (alias) DO NOTHING;
