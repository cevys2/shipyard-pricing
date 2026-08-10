# shipyard-pricing

Aplikasi internal PT Dukuh Raya (galangan kapal, Lombok) untuk **menyimpan dan menganalisis
harga** — bukan untuk mengelola pekerjaan docking.

Tiga jenis data:

| Bagian | Isi |
|---|---|
| **Katalog Harga Jasa** | Harga jual pekerjaan docking/repair per kapal per tahun, hasil ekstraksi laporan "Realisasi Biaya Docking" (±4.900 baris) |
| **Katalog Sumber Daya** | Harga beli material, tarif upah, tarif alat, konsumabel — lengkap dengan riwayat harganya |
| **Struktur Biaya (AHSP)** | Rincian satu pekerjaan jadi komponen bahan/upah/alat, untuk menghitung harga pokok dari bawah |

Ditambah analitik tren harga dan audit log.

## Yang aplikasi ini TIDAK lakukan

Ditulis terang-terangan supaya tidak ada yang mewarisi harapan yang keliru:

- **Tidak menghasilkan dokumen penawaran.** Penawaran masih dibuat manual di Excel. Aplikasi
  ini sumber angkanya, bukan penerbitnya.
- **Tidak punya halaman login.** Login ada di Portal (repo terpisah, `dukuh-raya-portal`)
  dengan JWT secret yang sama. Repo ini hanya memverifikasi token.
- **Tidak mengelola jadwal, pekerjaan, atau inventaris.**
- **Tidak punya tempat sampah.** Penghapusan permanen; pemulihan hanya dari cadangan harian.

## Stack

FastAPI + SQLAlchemy (raw SQL lewat `text()`, driver pg8000) · React + TypeScript + Vite +
Tailwind v4 · Postgres · deploy di Railway, cadangan harian ke Backblaze B2.

## Menjalankan di komputer sendiri

```bash
# Backend
cd backend
pip install -r requirements-dev.txt
export DATABASE_URL="postgresql://..."     # Postgres lokal
export JWT_SECRET="apa-saja-untuk-lokal"
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev                                 # http://localhost:5173
```

Ada juga dev container (`.devcontainer/devcontainer.json`) yang memasang semuanya otomatis.

**Peringatan.** `backend/.env` yang ada di mesin pengembang menunjuk ke database
**produksi**. Menjalankan uvicorn tanpa menimpa `DATABASE_URL` berarti menulis ke data klien
yang sebenarnya. Berkas itu tidak ikut ke repo (`backend/.gitignore`), dan jangan sampai ikut.

### Tes

```bash
createdb shipyard_test
cd backend
TEST_DATABASE_URL="postgresql://postgres:PASSWORD@127.0.0.1:5432/shipyard_test" pytest
```

`TEST_DATABASE_URL` bawaannya tanpa kata sandi, jadi hampir selalu perlu disebut sendiri.
Tes **menolak jalan** kalau URL-nya menunjuk ke host jauh (Railway, Supabase, AWS) — palang
supaya tes tidak pernah menyentuh produksi.

Setelah mengubah frontend, wajib bersih sebelum push:

```bash
cd frontend && npx tsc -b && npm run build
```

## Perubahan skema — tidak ada Alembic

Fungsi `ensure_*()` di `backend/app/database.py` menjalankan DDL mentah dan idempoten setiap
kali aplikasi start, dipanggil berurutan dari `main.py`. **Urutannya mengikat** — ada foreign
key antar tabelnya. Semua DDL harus idempoten; kalau tidak, aplikasi gagal start di boot
kedua, dan kalau DDL gagal seluruh aplikasi gagal start.

`tabel_katalog_harga` tidak pernah diubah strukturnya selain menambah kolom nullable, dan isi
`kategori_pekerjaan` tidak pernah ditulis ulang — itu catatan apa yang benar-benar tertulis di
laporan asli.

## Dokumen

| Berkas | Isi |
|---|---|
| `CLAUDE.md` | Konteks untuk AI coding assistant; paling padat soal aturan yang tidak boleh dilanggar |
| `docs/CHANGELOG.md` | Riwayat perubahan beserta alasannya |
| `docs/errata-serah-terima.md` | Koreksi atas Dokumen Serah Terima (PDF, di luar repo) |
| `docs/roadmap-fitur.md` | Rencana fitur yang disetujui klien |
| `docs/desain-katalog-material.md` | ERD, DDL, query analitik katalog material |
| `docs/rencana-langkah-3-struktur-biaya.md` | Rencana lengkap tab Struktur Biaya |
| `docs/catatan-tabel-katalog-harga.md` | Temuan kualitas data katalog harga |
| `docs/bundel-kategori-claude-code.md` | Keputusan kategori pekerjaan kanonik |

Dokumen Serah Terima yang lengkap — peta layanan, akses, runbook, prosedur pemulihan —
**tidak disimpan di repo** karena memuat pengenal infrastruktur dan catatan risiko
operasional. Minta ke pemegang akses. Baca bersama `docs/errata-serah-terima.md`.

## Catatan bagi siapa pun yang mengambil alih

Saat README ini ditulis, akses produksi (Railway, GitHub, Backblaze) dipegang **satu orang**
lewat akun pribadi. Selama itu belum berubah, sistem ini bergantung pada satu orang, dan tidak
ada perbaikan teknis untuk itu. Langkahnya ada di Dokumen Serah Terima bagian 3.2.
