# shipyard-pricing — konteks untuk Claude Code

## Stack
- **Backend**: FastAPI (folder `backend/`), SQLAlchemy pakai raw SQL lewat `text()`,
  driver `pg8000`. SELALU parameterized query, jangan f-string ke SQL.
- **Frontend**: React + TypeScript + Vite + Tailwind v4 (folder `frontend/`).
  Design system: warna navy `--ink`/`--marine` + aksen brass, font "Space Grotesk"
  untuk heading. Komponen tombol pakai class `.btn .btn-primary/secondary/danger/accent`
  (lihat `frontend/src/index.css`). Ikon pakai `lucide-react`.
- **Database**: Postgres di Railway (BUKAN Supabase lagi — sudah migrasi penuh).
  Env var: `DATABASE_URL` (nama variable historis, isinya connection string Railway).
- **Auth**: JWT custom (`backend/app/auth.py`), password hashing pakai `werkzeug`.
- **Deploy**: 2 service Railway (backend root `/backend`, frontend root `/frontend`),
  branch **`main`** (bukan `revamp-ui-modern` lagi — sudah dipindah).
- **DB schema changes**: belum ada Alembic. Pola yang dipakai sekarang: fungsi
  `ensure_xxx_table()` di `backend/app/database.py` yang jalanin DDL mentah pas app start
  (lihat `ensure_users_table()` sebagai contoh pola yang harus diikuti).

## Tabel existing (JANGAN diubah struktur intinya)
- `tabel_katalog_harga` — katalog harga JASA yang dijual (docking/maintenance kapal).
  Diisi lewat parser khusus (`backend/app/services/docking_parser.py`) yang extract dari
  laporan Excel "REALISASI BIAYA DOCKING".
- `users` — shared auth, dipakai juga rencana superapp/portal ke depan.

## Rencana fitur baru
Baca `docs/roadmap-fitur.md` (ringkas, dari slide yang disetujui klien) dan
`docs/desain-katalog-material.md` (detail teknis: ERD, DDL, query analitik).
**Fokus sekarang: Langkah 1 di roadmap saja** (tab Katalog Material). Langkah 2 & 3
belum dikerjakan sampai ada instruksi lanjut.

## Kebiasaan kerja
- Baca dulu file yang relevan sebelum edit, jangan asumsi struktur.
- Tunjukkan rencana/diff sebelum eksekusi perubahan besar (schema DB, banyak file).
- Jangan bikin fitur di luar scope yang diminta di 1 sesi kerja.
- Setelah ubah frontend: jalanin `npx tsc -b` dan `npm run build` buat mastiin nggak
  ada error sebelum dianggap selesai.
