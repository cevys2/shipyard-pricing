# shipyard-pricing — konteks untuk Claude Code

Aplikasi internal PT Dukuh Raya (galangan kapal, Lombok). Katalog harga jasa, katalog
material, dan analisa harga satuan (AHSP). Pengguna aktif: satu orang. Dikerjakan solo.

Terakhir diperbarui: 24 Agustus 2026.

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
  seed_kategori.py  -- 11 kategori + 100 alias, dipakai ensure_kategori_table()
  routers/          -- ahsp, analitik, catalog, kategori, material
  services/         -- ahsp, analitik, audit, catalog, docking_parser, material, pencarian,
                       repair_list_parser
  schemas/          -- pydantic
backend/tests/      -- 201 tes, harus tetap lulus setelah perubahan apa pun
```

## Perubahan skema — TIDAK ada Alembic

Pola yang dipakai: fungsi `ensure_xxx_table()` di `backend/app/database.py` yang menjalankan
DDL mentah dan idempoten saat app start, lalu dipanggil dari `main.py`.

Contoh pola yang paling bersih untuk ditiru: **`ensure_audit_table()`**.
Contoh penambahan kolom ke tabel yang sudah berisi data: lihat `tahun_pembelian` di
`ensure_material_tables()` — tambah nullable, backfill, baru `SET NOT NULL`.

Fungsi yang ada sekarang, dalam urutan pemanggilan di `main.py`:
`ensure_material_tables()`, `ensure_partno_unique()`, `ensure_katalog_kolom_rincian()`,
`ensure_kategori_table()`, `ensure_ahsp_tables()`, `ensure_audit_table()`,
`ensure_pencarian_index()`.

Urutannya bukan selera: `ahsp_komponen` punya FK ke `sumber_daya`, `ahsp.kategori_id` ke
`kategori`, dan index pencarian menempel ke tabel yang harus sudah ada. Dipanggil di luar
urutan itu, DDL-nya gagal.

Postgres tidak punya `ADD CONSTRAINT IF NOT EXISTS` — pakai guard `DO $$ ... pg_constraint ... $$`
seperti `chk_sdh_mata_uang`.

## Tabel

| Tabel | Isi |
|---|---|
| `tabel_katalog_harga` | Harga realisasi docking, 6.673 baris (cadangan 17 Agustus 2026). Diisi `services/docking_parser.py` dari Excel "REALISASI BIAYA DOCKING" dan `services/repair_list_parser.py` dari Excel "REPAIR LIST"/"RINCIAN". |
| `kategori`, `kategori_alias` | Master kategori pekerjaan kanonik (11) + pemetaan sebutan lama (83 alias). Teks kategori dicocokkan lewat `database.kategori_norm_sql()` — **jangan ubah ekspresinya**, alias di DB tersimpan sebagai hasil normalisasi itu. |
| `supplier`, `sumber_daya`, `sumber_daya_harga` | Katalog material + riwayat harga. View `v_harga_terkini`. |
| `ahsp`, `ahsp_komponen` | Analisa harga satuan. |
| `audit_log` | Append-only, siapa mengubah apa. |

### Aturan `tabel_katalog_harga`

**Boleh:** menambah kolom baru yang nullable.
**Tidak boleh:** mengubah atau menghapus kolom yang sudah ada, dan **tidak boleh menimpa isi
`kategori_pekerjaan`** — itu catatan apa yang benar-benar tertulis di laporan asli. Koreksi
kategori ditulis ke `kategori_id`, bukan dengan mengedit teks aslinya.

Kolom nullable yang sudah ditambahkan (`ensure_katalog_kolom_rincian()`, 24 Agustus 2026):
`volume` NUMERIC, `satuan` TEXT, `induk_uraian` TEXT, `keterangan` TEXT. Tidak ada backfill —
untuk 6.673 baris lama nilainya memang tidak diketahui, dan NULL mengatakan itu dengan jujur.
`volume_satuan` yang lama tidak disentuh dan tetap berlaku.

**Keempatnya sengaja TIDAK ikut di-UPDATE oleh `bulk_patch()`.** Layar edit katalog cuma
mengirim delapan kolom lama; kalau keempatnya ikut, menyunting satu sel apa pun akan
menimpanya jadi NULL tanpa error apa pun. Kalau suatu saat perlu bisa disunting, kirim
nilainya dari layar dulu — jangan cukup menambahkannya di SQL.

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
baru langsung dari layar AHSP), kategori pekerjaan kanonik (11 kategori, 100 alias), dan
impor Repair List (mode ketiga di tab Import Excel).

Diketahui terbatas:

- Aplikasi belum menghasilkan keluaran apa pun — penawaran masih disusun manual di Excel.
  Ini jurang terbesar yang tersisa antara "katalog" dan "alat yang menyelesaikan pekerjaan".
- Tab Struktur Biaya baru berisi satu analisa (13 komponen). `shift` dan `jml_hari` isinya 1
  di seluruh baris; cuma `qty` yang dipakai.
- `uq_sd_identitas` cuma menolak nama yang persis sama, jadi penjaga duplikat di layar
  sengaja dibuat lebih longgar daripada index-nya.
- **Cakupan kategori: 90,2% di produksi saat ini, 100% begitu di-deploy.** Per cadangan
  17 Agustus 2026, 6.017 dari 6.673 baris punya `kategori_id`; 656 kosong. Sebabnya
  `selaraskan_kategori()` cuma jalan saat app start (di ujung `ensure_kategori_table()`),
  **belum di jalur impor Excel** — jadi baris hasil impor menunggu deploy berikutnya. Angkanya
  kelihatan di tab Analitik (`cakupan.tanpa_kategori`).
  Dari 656 itu, 107 sudah cocok alias lama. Sisanya 549 memakai tujuh sebutan yang belum punya
  alias; ketujuhnya ditambahkan 18 Agustus 2026, jadi alias 83 → 90. Dihitung ulang terhadap
  cadangan yang sama: 6.673/6.673 = **100,00%**, nol sisa.
  Catatan jujur: selama jalur impor belum memanggil resolver, angka ini akan turun lagi tiap
  impor baru dan pulih lagi tiap deploy.
  Tujuh alias lagi ditambahkan 24 Agustus 2026 (90 → 97) untuk sebutan seksi di berkas
  REPAIR LIST, yang bentuknya memang beda dari laporan realisasi. Tanpa ketujuhnya, 374 dari
  385 baris tiga repair list Basarnas masuk tanpa kategori sama sekali; dengan ketujuhnya,
  385/385 terpetakan. Satu di antaranya keputusan, bukan kepastian: `DOCKING/ GENERAL SERVICE`
  dipetakan ke PELAYANAN UMUM, padahal sebutannya menggabung dua kategori yang di repo ini
  terpisah. Kalau yang dimaksud biaya naik-turun dok, pindahkan satu baris alias itu ke
  DOCKING & UNDOCKING.
- **Pencarian belum mencakup `induk_uraian`.** `KOLOM_CARI_KATALOG` masih dua kolom, jadi
  mengetik "Main Engine Tengah" tidak menemukan baris part yang konteksnya ada di kolom itu;
  mencari nama partnya sendiri tetap jalan. Menambahkannya bukan sekadar mengubah satu tuple:
  ekspresi index harus persis sama dengan ekspresi query, dan `CREATE INDEX IF NOT EXISTS`
  tidak akan membangun ulang index yang namanya sudah ada — index lamanya tetap terpasang
  tapi tidak pernah tersentuh lagi. Perlu nama index baru + DROP yang lama.
- Baris kembar identik di `tabel_katalog_harga` sengaja tidak didedup — tabelnya tidak punya
  kolom kuantitas, jadi tidak ada cara memastikan itu salah input atau dua pekerjaan sungguhan.

### Kuantitas: `volume`, dan kenapa dia tidak pernah ada sebelumnya

Dugaan yang lazim adalah `volume_satuan` menyimpan `"269 m²"`. Tidak — isinya **satuan saja**
("Ls", "Hari", "Kali"). Kuantitasnya tidak pernah tersimpan dari jalur mana pun. Di
`docking_parser` angkanya bahkan sudah dibaca sejak awal (`qty_numeric`), tapi cuma dipakai
membagi kolom Jumlah jadi harga satuan, lalu dibuang.

Sekarang ketiga jalur impor mengisi `volume` + `satuan`: Repair List, Laporan Docking, dan
Format Rapi (lewat kolom opsional `Vol`/`Sat`). Diverifikasi: di dua berkas docking di root
repo, 414 baris punya Qty DAN kolom Jumlah, dan `volume × harga_satuan = Jumlah` di
keempat-ratus-empat-belasnya.

**Jalur docking sengaja TIDAK diberi palang rekonsiliasi** seperti Repair List. Sebabnya
nyata, bukan kehati-hatian kosong: ada baris "tarif" (Keel block, Bottom share, Side Block,
"Repair Propeller Blade jika terjadi kerusakan") yang punya harga satuan tapi kolom Jumlah-nya
kosong, dan memang tidak ikut TOTAL BIAYA di berkasnya. Menjumlahkan `volume × harga` seluruh
baris melebihi TOTAL BIAYA sekitar 0,4% (Rp 5,5 juta di MISHIMA, Rp 7,0 juta di GILIMANUK II).
Itu bukan baris yang jatuh — itu tarif bersyarat. Palang yang berbunyi merah padahal impornya
benar akan cepat diabaikan, dan begitu diabaikan dia tidak menjaga apa pun.

Baris repair list tidak punya masalah itu: di ketiga berkas Basarnas semua baris berharga
punya VOL, dan selisihnya nol.

### Blok tanda tangan pernah jadi baris harga (diperbaiki 24 Agustus 2026)

Di baris `Diketahui dan Disetujui oleh :` ada sel tanggal di kolom harga satuan, dan xlrd
mengembalikannya sebagai **nomor seri Excel**. Jadi tiap berkas docking menyumbang satu baris
katalog palsu seharga 46.197 (MISHIMA) atau 45.903 (GILIMANUK II) — angka yang cukup masuk
akal sebagai harga sehingga tidak pernah ada yang curiga. `NOISE_EXACT` sekarang memuat
`diketahui`, `disetujui`, `mengetahui`, `dibuat oleh`.

Kemungkinan ada baris seperti ini di produksi, satu per berkas docking yang pernah diimpor.
Belum dihitung — butuh cadangan produksi. Cara mencarinya:
`WHERE uraian_pekerjaan ILIKE '%disetujui%' OR uraian_pekerjaan ILIKE '%diketahui%'`.

Sengaja TIDAK memakai aturan "berhenti membaca begitu ketemu TOTAL": kalau ada berkas yang
punya baris Total per seksi di tengah tabel, aturan itu memotong sisa berkasnya diam-diam —
kegagalan yang jauh lebih mahal daripada satu baris sampah.

### Template laporan docking tidak seragam

Empat berkas di arsip pernah terbaca **nol baris tanpa error** karena judul kolomnya beda.
Semuanya sudah ditangani, dan tiap kasusnya dijaga `tests/test_docking_format_lain.py`:

| Yang beda | Contoh berkas | Kalau tidak ditangani |
|---|---|---|
| Kolom uraian bernama `Nama Barang` | Lampiran Perjanjian KMP. Portlink II 2026 | 141 baris hilang |
| Kolom harga bernama `INDUK (Rp.)` | Realisasi LCT. ARJHUNA 2025 | 214 baris hilang |
| Tanpa label `NAMA KAPAL`, nama kapal ada di baris `Lokasi` | Lampiran Perjanjian Marina Segunda / Prima Nusantara | kapal kosong, baris tidak bisa disimpan |
| `PERIODE DOCKING : Nopember` dan `2025` di dua sel terpisah | Realisasi MV. Bali Hai II | tahun terisi "Nopember", lalu ikut jadi prefix ID |

Kegagalan jenis ini paling mahal karena tidak bersuara: berkas yang "berhasil diimpor 0 baris"
terlihat sama persis dengan berkas yang memang kosong.

### Konteks baris induk di jalur docking

`docking_parser` mengisi `induk_uraian` juga, dan kedalamannya dibaca dari **kolom**, bukan
tanda baca: berkas docking menggeser teks satu kolom ke kanan tiap turun satu tingkat, dengan
tanda hubung menempati sel tersendiri di kolom sebelumnya.

Gunanya bukan menghapus perbedaan harga — perbedaan itu data yang sah — melainkan menyimpan
**alasannya**. Di KMP. GILIMANUK 2026 ada 15 baris berbunyi persis `Elbow` seharga Rp 300.000
sampai Rp 2.100.000; sesudah ini tiap baris menyebut jalur pipanya (`Pipa isap BBM`,
`Pipa outboard got`, `Pipa tekan OWS di Car Deck`).

Batasnya jujur: rantai induk TIDAK memisahkan ukuran pipa, karena ukurannya ada di baris
saudara tepat di atasnya (`- Pipa Sch. 40 uk 1,5"`), bukan di baris induk. Dua Elbow di jalur
pipa yang sama tetap terlihat serupa.

### Repair List — dokumen awal pekerjaan, beda dari laporan realisasi

`services/repair_list_parser.py` membaca "REPAIR LIST"/"RINCIAN": dokumen kesepakatan di
**awal** pekerjaan, yang jadi dasar penagihan. `docking_parser.py` membaca "REALISASI BIAYA
DOCKING", laporan di **akhir**. Keduanya tidak bisa dibaca parser yang sama — yang paling
menentukan, di repair list kolom harga satuan berjudul **"SATUAN"**, bukan "HARGA", sehingga
docking_parser membacanya nol baris tanpa error apa pun.

Barisnya masuk sebagai `tipe_perjanjian = "Induk"`; yang membedakannya dari baris laporan
realisasi cuma `audit_log.detail->>'sumber' = 'import-repair-list'`. Ini keputusan sadar
(24 Agustus 2026): Basarnas tidak menegosiasikan ulang repair list-nya, jadi memisahkannya
jadi tipe ketiga belum berbayar. Kalau nanti ada klien yang harga kesepakatannya benar-benar
beda dari harga realisasi, tipe ketiga jadi perlu.

**Palang rekonsiliasi.** Jumlah semua baris yang diambil (`volume × harga_satuan`) harus persis
sama dengan angka JUMLAH di berkas, dan selisihnya ditampilkan di layar pratinjau sebelum apa
pun disimpan — dihitung ulang tiap kali tabelnya disunting. Inilah alasan sebenarnya kolom
`volume` ditambahkan: tanpa angkanya, palang ini mustahil dipasang. Diverifikasi terhadap tiga
berkas Basarnas (KN SAR 207, ANTAREJA 233, WIDURA 225): 385 baris, Rp 7.933.170.000, selisih
Rp 0 di ketiganya.

PPN tidak ikut disimpan — PPN di aplikasi ini ada di tingkat dokumen penawaran, bukan per baris
katalog (keputusan yang sudah final di atas).

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
