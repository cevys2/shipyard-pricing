# shipyard-pricing — konteks untuk Claude Code

Aplikasi internal PT Dukuh Raya (galangan kapal, Lombok). Katalog harga jasa, katalog
material, dan analisa harga satuan (AHSP). Pengguna aktif: satu orang. Dikerjakan solo.

Terakhir diperbarui: 18 Agustus 2026.

## Stack

- **Backend**: FastAPI (`backend/`), SQLAlchemy pakai raw SQL lewat `text()`, driver `pg8000`.
  SELALU parameterized query — jangan pernah f-string ke SQL.
- **Frontend**: React + TypeScript + Vite + Tailwind v4 (`frontend/`). Satu halaman utama
  `src/pages/DashboardPage.tsx` dengan beberapa tab. Design system: navy `--ink`/`--marine`
  + aksen brass, heading "Space Grotesk". Tombol pakai `.btn .btn-primary/secondary/danger/accent`
  (lihat `frontend/src/index.css`). Ikon `lucide-react`.
- **Database**: Postgres di Railway (bukan Supabase). Env var `DATABASE_URL`.
- **Auth**: `backend/app/auth.py` **hanya memverifikasi** JWT — `get_current_user()` dan
  `require_admin()`. Login dan tabel `users` ada di Portal, repo terpisah, dengan shared JWT
  secret. Repo ini tidak punya sistem login sendiri dan tidak membuat tabel `users`.
- **Deploy**: 2 service Railway (backend root `/backend`, frontend root `/frontend`),
  branch `main`. Cadangan harian ke Backblaze B2 lewat `backup-service/`.
  Build command frontend **harus** `npm install && npm run build` — `npm ci` selalu gagal
  EBUSY karena Railpack me-mount cache di dalam `node_modules`. Setelan build/start cuma
  terbaca oleh deployment BARU; tombol redeploy memutar ulang snapshot yang lama.

## Struktur backend

```
backend/app/
  main.py           -- startup memanggil semua ensure_*(), lalu include 5 router
  database.py       -- SEMUA DDL ada di sini (lihat "Perubahan skema" di bawah)
  auth.py           -- verifikasi JWT saja
  config.py         -- settings, termasuk catalog_table = "tabel_katalog_harga"
  seed_kategori.py  -- 11 kategori + 83 alias, dipakai ensure_kategori_table()
  routers/          -- ahsp, analitik, catalog, kategori, material
  services/         -- ahsp, analitik, audit, catalog, docking_parser, material, pencarian
  schemas/          -- pydantic
backend/tests/      -- 88 tes, harus tetap lulus setelah perubahan apa pun
```

## Perubahan skema — TIDAK ada Alembic

Pola yang dipakai: fungsi `ensure_xxx_table()` di `backend/app/database.py` yang menjalankan
DDL mentah dan idempoten saat app start, lalu dipanggil dari `main.py`.

Contoh pola yang paling bersih untuk ditiru: **`ensure_audit_table()`**.
Contoh penambahan kolom ke tabel yang sudah berisi data: lihat `tahun_pembelian` di
`ensure_material_tables()` — tambah nullable, backfill, baru `SET NOT NULL`.

Fungsi yang ada sekarang, dalam urutan pemanggilan di `main.py`:
`ensure_material_tables()`, `ensure_partno_unique()`, `ensure_kategori_table()`,
`ensure_ahsp_tables()`, `ensure_audit_table()`, `ensure_pencarian_index()`.

Urutannya bukan selera: `ahsp_komponen` punya FK ke `sumber_daya`, `ahsp.kategori_id` ke
`kategori`, dan index pencarian menempel ke tabel yang harus sudah ada. Dipanggil di luar
urutan itu, DDL-nya gagal.

Postgres tidak punya `ADD CONSTRAINT IF NOT EXISTS` — pakai guard `DO $$ ... pg_constraint ... $$`
seperti `chk_sdh_mata_uang`.

## Tabel

| Tabel | Isi |
|---|---|
| `tabel_katalog_harga` | Harga realisasi docking, 6.673 baris (cadangan 17 Agustus 2026). Diisi `services/docking_parser.py` dari Excel "REALISASI BIAYA DOCKING". |
| `kategori`, `kategori_alias` | Master kategori pekerjaan kanonik (11) + pemetaan sebutan lama (83 alias). Teks kategori dicocokkan lewat `database.kategori_norm_sql()` — **jangan ubah ekspresinya**, alias di DB tersimpan sebagai hasil normalisasi itu. |
| `supplier`, `sumber_daya`, `sumber_daya_harga` | Katalog material + riwayat harga. View `v_harga_terkini`. |
| `ahsp`, `ahsp_komponen` | Analisa harga satuan. |
| `audit_log` | Append-only, siapa mengubah apa. |

### Aturan `tabel_katalog_harga`

**Boleh:** menambah kolom baru yang nullable.
**Tidak boleh:** mengubah atau menghapus kolom yang sudah ada, dan **tidak boleh menimpa isi
`kategori_pekerjaan`** — itu catatan apa yang benar-benar tertulis di laporan asli. Koreksi
kategori ditulis ke `kategori_id`, bukan dengan mengedit teks aslinya.

## Keputusan yang sudah final — jangan ditawar ulang

- Harga jual AHSP = jumlah subtotal, **tanpa markup**. Diverifikasi dari 54/54 blok Excel asli.
- PPN di luar AHSP, ditambahkan di tingkat dokumen penawaran.
- Subtotal dijumlahkan jujur. Di ±37% kelompok, angka aplikasi akan **lebih tinggi** daripada
  Excel lama. Disengaja, bukan bug.
- Harga komponen AHSP hidup mengikuti Katalog Material, tidak dibekukan saat disimpan.
- Tidak ada impor Excel untuk AHSP — diisi manual lewat form.
- Tidak ada halaman changelog di dalam aplikasi.

## Keadaan sekarang

Sudah jalan: katalog harga jasa, katalog material + riwayat harga, analitik tren material,
AHSP/Struktur Biaya (Langkah 3 sampai Sesi 3.2, sudah di produksi — termasuk membuat material
baru langsung dari layar AHSP), dan kategori pekerjaan kanonik (11 kategori, 83 alias).

Diketahui terbatas:

- Aplikasi belum menghasilkan keluaran apa pun — penawaran masih disusun manual di Excel.
  Ini jurang terbesar yang tersisa antara "katalog" dan "alat yang menyelesaikan pekerjaan".
- Tab Struktur Biaya baru berisi satu analisa (13 komponen). `shift` dan `jml_hari` isinya 1
  di seluruh baris; cuma `qty` yang dipakai.
- `uq_sd_identitas` cuma menolak nama yang persis sama, jadi penjaga duplikat di layar
  sengaja dibuat lebih longgar daripada index-nya.
- **Cakupan kategori bukan lagi 100%.** Per cadangan 17 Agustus 2026: 6.017 dari 6.673 baris
  punya `kategori_id` (90,2%), 656 kosong. Sebabnya `selaraskan_kategori()` cuma jalan saat
  app start (di ujung `ensure_kategori_table()`), **belum di jalur impor Excel** — jadi baris
  hasil impor menunggu deploy berikutnya. Angkanya kelihatan di tab Analitik
  (`cakupan.tanpa_kategori`).
  Dari 656 itu, 107 teksnya cocok alias dan pulih sendiri begitu di-deploy. Sisanya 549
  **tidak akan pulih**: tujuh sebutan yang belum punya alias sama sekali — PERPIPAAN (368),
  PEKERJAAN PIPA DAN VALVE (126), PEKERJAAN PROPULSI (27), PEKERJAAN KONTRUKSI (14),
  PELAYANAN UMUM/GENERAL SERVICES (9), SEA CHEST & SEA VALVES (4), PEKERJAAN MEKANIK (1).
  Menambahkannya = menambah baris di `seed_kategori.py`; upsert-nya sudah idempoten.
- Baris kembar identik di `tabel_katalog_harga` sengaja tidak didedup — tabelnya tidak punya
  kolom kuantitas, jadi tidak ada cara memastikan itu salah input atau dua pekerjaan sungguhan.

### Waktu harga material — `tahun_pembelian`, bukan `berlaku_dari`

`berlaku_dari` boleh dikosongkan waktu menempel, dan kalau kosong jatuh ke `date.today()` —
jadi sering dia fakta soal kapan orang sempat menginput, bukan soal pembeliannya. Di cadangan
9 Agustus, 9 dari 68 baris harga punya `berlaku_dari` di tahun yang berbeda dari
`tahun_pembelian`.

Karena itu **`tahun_pembelian` yang berwenang**, dan sekarang sudah dipakai konsisten:

- Urutan "harga mana yang terkini": satu definisi di `database.urutan_harga_sql()`
  (`tahun_pembelian DESC, berlaku_dari DESC, id DESC`), dipakai di delapan tempat.
- Sidik jari penangkal duplikat titik harga (`services/material.py`) tidak memuat tanggal —
  kalau memuat, faktur yang sama ditempel besoknya lolos sebagai "harga baru".
- Sumbu-X grafik tren material dan kolom "Rentang Beli" memakai tahun pembelian.

`berlaku_dari` tetap ikut sebagai pemecah seri untuk membedakan dua pembelian di tahun yang
sama — selama memang diisi.

Konsekuensi yang disengaja: grafik tren punya satu titik per tahun. Kalau ada beberapa
pembelian di tahun yang sama, yang tergambar adalah yang paling baru di tahun itu.

## Dokumen

`docs/roadmap-fitur.md`, `docs/desain-katalog-material.md` (ERD + DDL + query analitik),
`docs/rencana-langkah-3-struktur-biaya.md`, `docs/catatan-tabel-katalog-harga.md`,
`docs/CHANGELOG.md`.

**`docs/errata-serah-terima.md`** — Dokumen Serah Terima (PDF, di luar repo) disusun 10
Agustus 2026 dan repo sudah bergerak sejak itu. Kalau errata dan PDF bertentangan, errata
yang benar. Baca ini sebelum memercayai PDF-nya.

Arsip keputusan kategori: `docs/bundel-kategori-claude-code.md`, `docs/final_peta.json`,
`docs/seed_kategori.sql` (yang benar-benar dijalankan `backend/app/seed_kategori.py`).
Migrasi tahun yang sudah dijalankan: `docs/perbaikan-tahun-katalog.sql` +
`backend/perbaiki_tahun.py`.

## Kebiasaan kerja

- Baca dulu file yang relevan sebelum edit. Jangan asumsi struktur.
- Tunjukkan rencana/diff sebelum eksekusi perubahan besar (skema DB, banyak file).
- Jangan bikin fitur di luar scope yang diminta dalam satu sesi.
- Kalau ragu soal keputusan yang mengubah kode — **tanya dulu**, jangan langsung eksekusi.
- Setelah ubah frontend: jalankan `npx tsc -b` dan `npm run build` sampai bersih.
- Setelah ubah backend: jalankan tes, semuanya harus lulus.
- Jangan mengaku sudah menguji sesuatu yang belum diuji.
