# shipyard-pricing — konteks untuk Claude Code

Aplikasi internal PT Dukuh Raya (galangan kapal, Lombok). Katalog harga jasa, katalog
material, dan analisa harga satuan (AHSP). Pengguna aktif: satu orang. Dikerjakan solo.

Terakhir diperbarui: Agustus 2026.

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
backend/tests/      -- 80 tes, harus tetap lulus setelah perubahan apa pun
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
| `tabel_katalog_harga` | Harga realisasi docking, ±4.900 baris. Diisi `services/docking_parser.py` dari Excel "REALISASI BIAYA DOCKING". |
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
AHSP (Langkah 3 — **sudah selesai dan teruji**, tapi belum satu koefisien pun diisi dan
belum pernah dibuka di peramban), dan kategori pekerjaan kanonik (K0–K3 selesai dan
sudah di produksi; 4.914 baris terpetakan, nol sisa).

Diketahui terbatas: aplikasi belum menghasilkan keluaran apa pun (penawaran masih dibuat
manual di Excel). `uq_sd_identitas` cuma menolak nama yang persis sama.

Yang masih menggantung di katalog material — `berlaku_dari` jatuh ke `date.today()` kalau
tempelan tidak menyertakan tanggal, padahal SEMUA keputusan "harga mana yang terkini"
(`v_harga_terkini`, `_harga_berubah`, tren material) mengurut lewat kolom itu. Akibatnya
(a) faktur yang sama ditempel di dua hari berbeda jadi dua titik harga, dan (b) pembelian
lama yang baru diinput bisa mengalahkan pembelian yang lebih baru. `tahun_pembelian` sudah
ada tapi cuma dipakai sebagai filter, tidak pernah untuk mengurutkan.

## Dokumen

`docs/roadmap-fitur.md`, `docs/desain-katalog-material.md` (ERD + DDL + query analitik),
`docs/rencana-langkah-3-struktur-biaya.md`, `docs/catatan-tabel-katalog-harga.md`,
`docs/CHANGELOG.md`.

## Kebiasaan kerja

- Baca dulu file yang relevan sebelum edit. Jangan asumsi struktur.
- Tunjukkan rencana/diff sebelum eksekusi perubahan besar (skema DB, banyak file).
- Jangan bikin fitur di luar scope yang diminta dalam satu sesi.
- Kalau ragu soal keputusan yang mengubah kode — **tanya dulu**, jangan langsung eksekusi.
- Setelah ubah frontend: jalankan `npx tsc -b` dan `npm run build` sampai bersih.
- Setelah ubah backend: jalankan tes, semuanya harus lulus.
- Jangan mengaku sudah menguji sesuatu yang belum diuji.
