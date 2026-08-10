# Bundel Claude Code — Kategori Pekerjaan Kanonik

Versi 2. Empat sesi terpisah, berurutan. **Jangan digabung jadi satu sesi.**

Berkas pendamping:
- `seed_kategori.sql` — 11 kategori + 83 alias. Sudah diuji di Postgres 16 dengan 78 kategori
  asli dari database produksi: semua terpetakan, nol sisa, aman dijalankan berulang.
- `CLAUDE.md` — pengganti yang sudah diperbarui (dipakai di Sesi K0).

---

## Keputusan yang mengikat — jangan ditawar ulang oleh agent

| # | Keputusan | Oleh |
|---|---|---|
| K-1 | 11 kategori kanonik: 10 jenis pekerjaan + `LAIN-LAIN` | VP marketing |
| K-2 | MEKANIK/BENGKEL, NDT & PENGUJIAN, LISTRIK dihapus dari daftar; aliasnya jatuh ke `LAIN-LAIN` | VP marketing |
| K-3 | `LAIN-LAIN` tetap dipakai sebagai kategori sah | VP marketing |
| K-4 | Pengecatan tidak berdiri sendiri, tetap di dalam `PERAWATAN LAMBUNG` | VP marketing |
| K-5 | `PEKERJAAN TAMBAHAN` / `ADDITIONAL WORK` (442 baris) → `LAIN-LAIN` | VP marketing |
| K-6 | Kategori hasil disimpan di kolom `kategori_id`; **isi `kategori_pekerjaan` tidak pernah ditimpa** | Lutfi |
| K-7 | Nama kanonik memakai kata yang sudah dipakai di laporan, bukan istilah baru | Lutfi |

Angka yang harus keluar setelah K1 selesai — sudah diverifikasi dua kali dengan metode
berbeda (pandas dan SQL):

| Kategori | Baris | % |
|---|---:|---:|
| PIPA - PIPA | 1.350 | 27,5% |
| REPLATING | 761 | 15,5% |
| PELAYANAN UMUM | 605 | 12,3% |
| PERAWATAN LAMBUNG | 512 | 10,4% |
| KEMUDI, PROPELLER & POROS | 416 | 8,5% |
| SEA CHEST & VALVE | 276 | 5,6% |
| DOCKING & UNDOCKING | 150 | 3,1% |
| KONSTRUKSI | 88 | 1,8% |
| JANGKAR & RANTAI JANGKAR | 52 | 1,1% |
| TANGKI | 24 | 0,5% |
| LAIN-LAIN | 678 | 13,8% |
| **Total** | **4.912** | **100%** |

`LAIN-LAIN` lahir di 13,8% karena konsekuensi K-5. **Disengaja, bukan bug.** Jangan biarkan
agent "memperbaikinya".

---

## Rancangan inti

Dua lapis, sengaja dipisah:

- **`kategori_alias`** — mesin otomatis. Memetakan teks kategori lama ke kategori kanonik.
- **`tabel_katalog_harga.kategori_id`** — tempat hasilnya disimpan, boleh ditimpa manusia.

Aturannya satu kalimat: **alias mengisi otomatis, manusia boleh menimpa, dan resolver tidak
pernah menyentuh baris yang bertanda `manual`.**

Kenapa dua lapis: tanpa `kategori_id`, satu-satunya cara mengoreksi baris adalah menimpa teks
kategori aslinya — merusak catatan sejarah. Dengan `kategori_id`, 442 baris `PEKERJAAN TAMBAHAN`
yang jenis pekerjaannya masih terbaca dari `uraian_pekerjaan` bisa dipulihkan belakangan.
Tanpa itu, LAIN-LAIN permanen di 13,8% tanpa jalan turun.

Perilaku ini sudah diuji di Postgres 16 lokal — termasuk kasus dua baris berteks kategori
identik di mana yang satu dikoreksi manual dan yang lain tidak. Setelah resolver dijalankan
dua kali, koreksi manualnya tetap utuh.

---

## Sesi K0 — perbarui CLAUDE.md

Kecil tapi dikerjakan **pertama**, karena berkas ini dibaca agent sebagai instruksi.
Yang sekarang menyatakan "Langkah 2 & 3 belum dikerjakan" padahal Langkah 3 sudah selesai,
dan menyuruh meniru pola `ensure_users_table()` — **fungsi itu tidak ada di repo.**

> **Prompt untuk Claude Code:**
>
> Ganti isi `CLAUDE.md` di root repo dengan berkas `CLAUDE.md` baru yang saya sertakan.
> Jangan menambah atau mengurangi isinya.
>
> Setelah itu, verifikasi setiap klaim di berkas baru terhadap repo yang sebenarnya dan
> laporkan kalau ada yang tidak cocok — khususnya: daftar fungsi `ensure_*()` di
> `database.py`, daftar router dan service, jumlah tes di `backend/tests/`, dan apakah
> `backend/app/auth.py` benar hanya memverifikasi token tanpa menyentuh tabel `users`.
> Jangan perbaiki sendiri — laporkan saja, biar saya yang putuskan.

## Sesi K1 — master kategori + alias + resolver

> **Prompt untuk Claude Code:**
>
> Baca dulu, jangan menulis kode sebelum selesai:
> - `backend/app/database.py`, terutama `ensure_audit_table()` (pola paling bersih untuk
>   ditiru) dan bagian `tahun_pembelian` di `ensure_material_tables()` (pola menambah kolom
>   ke tabel yang sudah berisi data).
> - `backend/app/services/analitik.py` baris 20–30.
> - `docs/desain-katalog-material.md` bagian 2.3.
>
> Tugas:
>
> 1. Buat `ensure_kategori_table()` di `backend/app/database.py`, panggil dari `main.py`
>    **sebelum** `ensure_ahsp_tables()`. DDL `kategori` dan `kategori_alias` persis seperti
>    di `docs/desain-katalog-material.md` bagian 2.3 — jangan diubah bentuknya.
>
> 2. Pindahkan ekspresi normalisasi kategori yang sekarang ada di `analitik.py`
>    (`_KATEGORI_NORM`) ke satu tempat yang bisa dipakai bersama, lalu pakai dari situ di
>    kedua tempat. **Ekspresinya harus tetap identik**, karena alias di database disimpan
>    dalam bentuk hasil normalisasi itu. Beda sedikit saja, pemetaan gagal tanpa error —
>    hasilnya cuma salah.
>
> 3. Jalankan `seed_kategori.sql`. Seed sudah idempoten. Tentukan sendiri apakah dipanggil
>    dari `ensure_kategori_table()` atau lewat perintah terpisah — tunjukkan pilihanmu dan
>    alasannya sebelum eksekusi.
>
> 4. Tambahkan dua kolom ke `tabel_katalog_harga`:
>    ```sql
>    ALTER TABLE tabel_katalog_harga
>      ADD COLUMN IF NOT EXISTS kategori_id     INT REFERENCES kategori(id),
>      ADD COLUMN IF NOT EXISTS kategori_sumber TEXT NOT NULL DEFAULT 'alias'
>                               CHECK (kategori_sumber IN ('alias','manual'));
>    ```
>    Bentuk ini **sudah diuji idempoten**: dijalankan tiga kali hanya menghasilkan NOTICE
>    "already exists, skipping" dan tetap satu constraint. Jadi di sini **tidak perlu** guard
>    `DO $$ ... pg_constraint ... $$` seperti pada `chk_sdh_mata_uang` — guard itu diperlukan
>    ketika constraint dipasang lewat `ADD CONSTRAINT` terpisah, bukan menempel di
>    `ADD COLUMN IF NOT EXISTS`. Jangan menambahkannya.
>    Ini penambahan kolom nullable — kolom yang sudah ada tidak boleh disentuh.
>
> 5. Buat fungsi resolver yang mengisi `kategori_id` dari `kategori_alias`, dengan syarat
>    **hanya menyentuh baris yang `kategori_sumber = 'alias'`**:
>    ```sql
>    UPDATE tabel_katalog_harga t
>    SET    kategori_id = a.kategori_id
>    FROM   kategori_alias a
>    WHERE  t.kategori_sumber = 'alias'
>      AND  <ekspresi normalisasi dari langkah 2 atas t.kategori_pekerjaan> = a.alias
>      AND  t.kategori_id IS DISTINCT FROM a.kategori_id;
>    ```
>    Resolver dipanggil setelah seed, dan juga setelah impor Excel berikutnya.
>
> 6. Buat indeks `idx_tkh_kategori ON tabel_katalog_harga(kategori_id)`.
>
> **Jangan sentuh:** kolom existing `tabel_katalog_harga`, isi `kategori_pekerjaan`,
> frontend, `ahsp`, `sumber_daya`.
>
> **Cara verifikasi — tunjukkan hasil query-nya, bukan cuma bilang sudah:**
> - Jumlah baris per kategori. Harus sama persis dengan tabel di dokumen bundel ini,
>   11 baris, total 4.912.
> - `SELECT count(*) FROM tabel_katalog_harga WHERE kategori_id IS NULL` — harus **nol**.
>   Kalau bukan nol, berhenti dan laporkan, jangan diperbaiki sendiri.
> - Jalankan seed dan resolver dua kali. Tidak boleh ada baris ganda, tidak boleh ada error,
>   dan jumlah per kategori harus tidak berubah.
> - Uji penjaga manual: ambil satu baris, set `kategori_id` ke kategori lain dan
>   `kategori_sumber='manual'`, jalankan resolver dua kali, pastikan baris itu tidak berubah
>   sementara baris lain berteks kategori sama tetap ikut resolver.
> - 43 tes yang sudah ada harus tetap lulus.

## Sesi K2 — analitik memakai `kategori_id`

> **Prompt untuk Claude Code:**
>
> Baca `backend/app/services/analitik.py` seluruhnya.
>
> Ganti `tren_harga_jasa()` dan `kategori_options()` supaya mengelompokkan lewat
> `kategori_id` / tabel `kategori`, bukan lewat normalisasi teks. `kategori_options()`
> sekarang mengembalikan daftar dari master (aktif saja, urut `urutan`), bukan hasil
> pemindaian teks bebas.
>
> Jangan ubah bentuk respons API-nya kalau tidak perlu — kalau terpaksa berubah, tunjukkan
> dulu sebelum eksekusi karena frontend ikut terpengaruh.
>
> **Cara verifikasi:** bandingkan keluaran `tren_harga_jasa()` sebelum dan sesudah untuk satu
> kategori yang aliasnya banyak, misalnya PIPA - PIPA. Setelah perubahan, jumlah sampelnya
> harus **naik** karena 10 sebutan sekarang menyatu. Tunjukkan angka sebelum dan sesudah.

## Sesi K3 — ikat `ahsp.kategori` + frontend

Dua bagian, boleh dipisah lagi kalau terasa besar.

> **Prompt untuk Claude Code:**
>
> **Bagian A — backend.** `ahsp.kategori` masih teks bebas, jadi akan melenceng persis
> seperti `kategori_pekerjaan` dulu. Tambahkan `kategori_id INT REFERENCES kategori(id)` ke
> `ahsp` lewat `ADD COLUMN IF NOT EXISTS`, backfill dari kolom `kategori` lama lewat
> `kategori_alias`. Kolom `kategori` lama **jangan di-drop**. Tunjukkan berapa baris yang
> berhasil dan gagal di-backfill; kalau ada yang gagal, tampilkan daftarnya, jangan
> diperbaiki diam-diam.
>
> **Bagian B — frontend.** Setiap tempat pengguna mengetik kategori jadi dropdown yang
> mengambil daftar dari `kategori` (aktif saja, urut `urutan`). Filter kategori di tab
> Analitik ikut memakai daftar yang sama. Pakai komponen dan kelas yang sudah ada di
> `frontend/src/index.css` — jangan bikin gaya baru.
>
> **Wajib sebelum dianggap selesai:** `npx tsc -b` dan `npm run build` bersih, dan 43 tes lulus.

---

## Assumption log

| No | Asumsi | Risiko kalau salah | Status |
|----|--------|--------------------|--------|
| K-A1 | `CLEANING` (5 baris) masuk `TANGKI`, bukan `PERAWATAN LAMBUNG` | rendah — ubah 1 baris alias | default |
| K-A2 | `KONSTRUKSI` tetap terpisah dari `REPLATING` | rendah — gabungkan kapan saja tanpa sentuh data | default |
| K-A3 | Pengguna boleh memilih `LAIN-LAIN` saat input baru | sedang — lihat catatan | **belum diputuskan** |
| K-A4 | Ambang wajar `LAIN-LAIN` 5%; di atas itu berarti ada nama yang kurang | rendah | usulan |
| K-A5 | Resolver dipanggil manual, belum otomatis tiap impor | rendah — tambahkan di K1 langkah 5 kalau parser sudah siap | default |

**Catatan K-A3.** K-5 menyelesaikan **data lama** — untuk 442 baris itu memang tidak diketahui
jenis pekerjaannya, dan `LAIN-LAIN` label paling jujur. Yang belum diputuskan adalah **aturan
input ke depan**: waktu orang memasukkan pekerjaan addendum baru, boleh pilih `LAIN-LAIN`,
atau wajib pilih jenis pekerjaan sungguhan karena status Induk/Addendum sudah punya kolom
sendiri? Hanya memengaruhi Sesi K3 Bagian B. Aman ditunda.

## Risiko terbesar bundel ini

Seluruh mekanisme bergantung pada satu ekspresi normalisasi yang harus **identik** antara
`analitik.py` dan alias yang tersimpan di database. Kalau meleset, tidak ada error — cuma
hasil yang salah. Karena itu verifikasi K1 dibuat spesifik: baris tanpa `kategori_id` harus
**nol**, bukan "sedikit". Kalau agent melaporkan angka selain nol, berhenti.
