# shipyard-pricing — konteks untuk Claude Code

Aplikasi internal PT Dukuh Raya (galangan kapal, Lombok). Katalog harga jasa, katalog
material, dan analisa harga satuan (AHSP). Pengguna aktif: satu orang. Dikerjakan solo.

Terakhir diperbarui: 22 September 2026.

## Stack

- **Backend**: FastAPI (`backend/`), SQLAlchemy pakai raw SQL lewat `text()`, driver `pg8000`.
  SELALU parameterized query — jangan pernah f-string ke SQL.
- **Frontend**: React + TypeScript + Vite + Tailwind v4 (`frontend/`). Satu halaman utama
  `src/pages/DashboardPage.tsx` dengan beberapa tab. Design system: navy `--ink`/`--marine`
  + aksen brass, heading "Space Grotesk", teks "Plus Jakarta Sans" (22 September 2026,
  menggantikan Inter — lebih bulat dan lebih tenang di ukuran 12-13px yang mengisi tabel).
  Angka tabular secara global lewat `body`, dikembalikan ke proporsional di `p` supaya angka
  di dalam kalimat tetap enak dibaca. Satu aturan `:focus-visible` untuk semua yang bisa
  di-Tab — app entri data, fokus yang tak kelihatan artinya kehilangan tempat.
  Tombol pakai `.btn .btn-primary/secondary/danger/accent`
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
  seed_kategori.py  -- 11 kategori + 126 alias, dipakai ensure_kategori_table()
  routers/          -- ahsp, analitik, catalog, kategori, material
  services/         -- ahsp, analitik, audit, catalog, docking_parser, material, pencarian,
                       repair_list_parser
  schemas/          -- pydantic
backend/tests/      -- 201 tes, harus tetap lulus setelah perubahan apa pun
```

## Perubahan skema — TIDAK ada Alembic

Pola yang dipakai: fungsi `ensure_xxx_table()` di `backend/app/database.py` yang menjalankan
DDL mentah dan idempoten saat app start, lalu dipanggil dari `main.py`. Pola terbersih untuk
ditiru: **`ensure_audit_table()`**. Untuk menambah kolom ke tabel yang sudah berisi data lihat
`tahun_pembelian` di `ensure_material_tables()` — tambah nullable, backfill, baru `SET NOT NULL`.

Urutan pemanggilan di `main.py`: `ensure_material_tables()`, `ensure_partno_unique()`,
`ensure_katalog_kolom_rincian()`, `ensure_kategori_table()`, `ensure_ahsp_tables()`,
`ensure_audit_table()`, `ensure_klien_induk()`, `ensure_pencarian_index()`.

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
| `klien_induk` | Pemetaan ejaan PT yang sebenarnya satu induk. Dipakai lewat `COALESCE` saat membaca; `nama_perusahaan` tidak pernah ditimpa. |

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
analitik **nilai pekerjaan** (volume × harga; 22 September 2026), filter **jenis kapal**,
AHSP/Struktur Biaya (Langkah 3 sampai Sesi 3.2, sudah di produksi — termasuk membuat material
baru langsung dari layar AHSP), kategori pekerjaan kanonik (11 kategori, 126 alias), dan
impor Repair List (mode ketiga di tab Import Excel).

Diketahui terbatas:

- Aplikasi belum menghasilkan keluaran apa pun — penawaran masih disusun manual di Excel.
  Ini jurang terbesar yang tersisa antara "katalog" dan "alat yang menyelesaikan pekerjaan".
- **Analitik "Ke Mana Uangnya Pergi" cuma mencakup 40,4% baris** (3.243 dari 8.024,
  per 22 September 2026), dan cakupannya **tidak acak** — dia mengikuti jalur impor, jadi
  per kapal melompat dari 24% (SINDU TRITAMA) sampai 100% (PRATHITA IV). Karena itu
  `per_kapal` membawa `n_baris` DAN `n_baris_bernilai`, dan layarnya menampilkan pecahannya
  per baris. **Jangan pernah menambahkan `WHERE volume IS NOT NULL` ke query per-kapal** —
  penyebutnya hilang, tiap kapal terlihat 100% terukur, dan nilai yang memotret seperempat
  pekerjaan terbaca sebagai nilai penuh. Dijaga `tests/test_nilai_pekerjaan.py`.
- **`satuan` punya 37 ejaan untuk ~20 satuan nyata**: `m²`(206)/`m2`(160)/`m'`(5),
  `mtr`(214)/`m`(59)/`mter`(1), `pcs`/`pc`/`buah`/`bh`, `tangki`/`tanki`, `liter`/`ltr`,
  `segel`/`shackle`. Belum dinormalisasi karena analitik yang ada tidak mengelompokkan per
  satuan. Begitu ada layar yang menjawab "harga per m² wajarnya berapa", pemetaan satuan
  kanonik (pola `kategori_alias`) jadi prasyarat mutlak — tanpa itu m² dan m2 jadi dua
  kelompok yang masing-masing separuh.
- **Dua baris uji di produksi**: `KMP. TES` / `PT. TES FERRY`, nama yang sama dengan fixture
  di `tests/test_docking_volume.py`. Ikut terhitung di KPI dan dropdown. Belum dihapus.
- Tab Struktur Biaya baru berisi satu analisa (13 komponen). `shift` dan `jml_hari` isinya 1
  di seluruh baris; cuma `qty` yang dipakai.
- `uq_sd_identitas` cuma menolak nama yang persis sama, jadi penjaga duplikat di layar
  sengaja dibuat lebih longgar daripada index-nya.
- **Cakupan kategori tidak lagi turun tiap impor** (23 September 2026). Dulu
  `selaraskan_kategori()` cuma jalan saat app start, jadi baris hasil impor menunggu deploy
  berikutnya (90,2% di produksi sebelum itu). Sekarang `database.kategori_id_sql()` me-resolve
  `kategori_id` di dalam INSERT `_insert_rows()` — semua jalur simpan lewat situ — dan di
  UPDATE `bulk_patch()` untuk baris `kategori_sumber = 'alias'`. `selaraskan_kategori()` tetap
  jalan saat app start untuk alias yang baru ditambahkan. Yang masih bisa kosong hanyalah
  sebutan yang belum punya alias. Kelihatan di tab Analitik (`cakupan.tanpa_kategori`).
  Riwayatnya: per cadangan 17 Agustus 2026, 6.017/6.673 baris punya `kategori_id`, 656 kosong;
  107 di antaranya cocok alias lama, sisanya 549 memakai tujuh sebutan yang belum punya alias.
  Ketujuhnya ditambahkan 18 Agustus (83 → 90 alias) → dihitung ulang terhadap cadangan yang
  sama: 6.673/6.673 = **100,00%**.
  Tujuh alias lagi ditambahkan 24 Agustus (90 → 97) untuk sebutan seksi di berkas REPAIR LIST,
  yang bentuknya memang beda dari laporan realisasi. Tanpa ketujuhnya, 374 dari 385 baris tiga
  repair list Basarnas masuk tanpa kategori; dengan ketujuhnya, 385/385 terpetakan.
  Satu di antaranya keputusan, bukan kepastian: `DOCKING/ GENERAL SERVICE` dipetakan ke
  PELAYANAN UMUM, padahal sebutannya menggabung dua kategori yang di repo ini terpisah. Kalau
  yang dimaksud biaya naik-turun dok, pindahkan satu baris alias itu ke DOCKING & UNDOCKING.
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
nyata: ada baris "tarif" (Keel block, Bottom share, Side Block, "Repair Propeller Blade jika
terjadi kerusakan") yang punya harga satuan tapi kolom Jumlah-nya kosong, dan memang tidak ikut
TOTAL BIAYA di berkasnya. Menjumlahkan `volume × harga` seluruh baris melebihi TOTAL BIAYA
sekitar 0,4% (Rp 5,5 juta di MISHIMA, Rp 7,0 juta di GILIMANUK II). Itu bukan baris yang jatuh
— itu tarif bersyarat. Palang yang berbunyi merah padahal impornya benar akan cepat diabaikan,
dan begitu diabaikan dia tidak menjaga apa pun.

Baris repair list tidak punya masalah itu: di ketiga berkas Basarnas semua baris berharga
punya VOL, dan selisihnya nol.

### Blok tanda tangan pernah jadi baris harga (diperbaiki 24 Agustus 2026)

Di baris `Diketahui dan Disetujui oleh :` ada sel tanggal di kolom harga satuan, dan xlrd
mengembalikannya sebagai **nomor seri Excel**. Jadi tiap berkas docking menyumbang satu baris
katalog palsu seharga 46.197 (MISHIMA) atau 45.903 (GILIMANUK II) — angka yang cukup masuk
akal sebagai harga sehingga tidak pernah ada yang curiga. `NOISE_EXACT` sekarang memuat
`diketahui`, `disetujui`, `mengetahui`, `dibuat oleh`.

**Sudah dihitung di produksi (22 September 2026): nol baris palsu.** Keempat kata itu
dicari ke seluruh 8.024 baris dan cuma satu yang kena — `Dibuatkan laporan pengedokan kapal
(Docking Report) mengetahui class`, Rp 5.000.000, KMP. TRIMAS ELLISA. Itu baris pekerjaan
yang sah, kebetulan memuat kata "mengetahui". **Jangan dihapus.** Ini juga pengingat bahwa
`NOISE_EXACT` benar dipakai sebagai pencocokan persis, bukan `ILIKE '%...%'`: kalau
pencocokannya longgar, baris ini yang jadi korban.

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
| Sub-kolom harga bernama `Sat`, bukan `Satuan` | Docking DEAL KMP. PRATHITA IV | 154 baris masuk dengan angka TOTAL sebagai harga satuan |
| Label dan nilai menyatu di satu sel: `": KMP PRATHITA IV"` | idem | nama kapal berawalan titik dua, ikut jadi prefix ID |
| Tanpa `PERIODE DOCKING`; tahun cuma ada di sel tanggal tak berlabel | idem | tahun kosong, baris tidak bisa disimpan sama sekali |
| Angka `0` di kolom nomor sebagai pengisi baris lanjutan | idem | 56 uraian berawalan "0 ", dan induk tergusur oleh anaknya |
| Baris berharga yang uraiannya ada di baris induk | idem | 2 baris masuk katalog bernama "0" |

Kegagalan jenis ini paling mahal karena tidak bersuara: berkas yang "berhasil diimpor 0 baris"
terlihat sama persis dengan berkas yang memang kosong.

Tiga baris terakhir (1 September 2026) beda jenisnya dan lebih buruk: berkasnya terbaca
**penuh**, 154 baris, tanpa satu pun tanda bahaya — cuma angkanya yang salah. Sumbernya
fallback `cols[-1]` di `col_for_sub()`: kalau sub-header tidak dikenali, dia diam-diam memilih
kolom TERAKHIR grup, dan di grup harga dua kolom itu selalu kolom Jumlah. Sekarang urutannya
ejaan persis → sinonim (`sat` ≡ `satuan`) → POSISI (`satuan` ke kiri, `jumlah` ke kanan).

Ini **satu-satunya palang di jalur docking**, dan sengaja palang STRUKTUR, bukan penjumlahan:
kalau Satuan dan Jumlah jatuh ke kolom yang sama di grup berkolom banyak, parser bilang. Dia
memeriksa susunan judul, jadi tidak punya masalah bunyi-palsu yang membuat palang rekonsiliasi
tidak dipasang di jalur ini (lihat bagian Kuantitas di atas).

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

Pengisi tata letak dikumpulkan di `_pengisi()` (1 September 2026): kosong, `-`, dan **angka 0**.
Yang ketiga baru muncul di PRATHITA IV, dipakai sebagai nomor urut baris lanjutan, dan ikut ke
dua tempat: teks uraian, dan kedalaman kolom lewat `col_a_str`.

Baris berharga yang uraiannya kosong **meminjam** uraian dari induk terdalamnya, dan induk itu
dikeluarkan dari rantai supaya tidak muncul dua kali. Baris pinjaman tidak pernah jadi induk
baris berikutnya, dan tiap pinjaman muncul sebagai peringatan.

**Palangnya volume, bukan daftar kata.** Baris kaki berkas (`Jumlah`, `PPN 11%`,
`Jumlah + PPN`) juga tidak punya uraian di rentang kolom uraian -- labelnya duduk di kolom
harga. Yang membedakannya: baris lanjutan yang sah punya volume, baris kaki cuma punya satu
angka jadi. Memakai daftar kata seperti "jumlah"/"total" akan membuang baris pekerjaan yang
sungguhan memuat kata itu. Tanpa palang ini, tiga baris kaki PRATHITA IV masuk katalog dan
jumlah impor jadi 3,2x angka yang benar.

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

Drawer Riwayat Harga (22 September 2026) mengelompokkan titik harga per **tahun beli**, bukan
mengurutkannya diam-diam seperti dulu: backend selalu mengurutkan `tahun_pembelian` dulu,
sementara tabelnya cuma menampilkan `berlaku_dari`, jadi baris yang dua tahunnya berbeda
tampak melompat tanpa sebab. Baris seperti itu sekarang bertanda "beda tahun".

Grafik di drawer memakai sumbu waktu numerik atas `berlaku_dari` — itu satu-satunya tanggal
nyata yang dipunyai tiap titik. Titik yang tahunnya tidak cocok **sengaja tidak digeser** ke
tahun pembeliannya: bulan sebenarnya tidak diketahui, dan menebaknya akan menampilkan angka
yang tidak ada di dokumen mana pun. Titiknya ditandai kuning berongga plus keterangan.
Kalau suatu saat mau digeser, itu keputusan soal data, bukan soal tampilan.

Konsekuensi yang disengaja: grafik tren punya satu titik per tahun. Kalau ada beberapa
pembelian di tahun yang sama, yang tergambar adalah yang paling baru di tahun itu.

## Dokumen

`docs/roadmap-fitur.md`, `docs/desain-katalog-material.md` (ERD + DDL + query analitik),
`docs/catatan-tabel-katalog-harga.md`, `docs/CHANGELOG.md`.

`docs/rencana-langkah-3-struktur-biaya.md` — bukan lagi rencana (fiturnya sudah jalan), tapi
temuan dari file Excel AHSP asli dan alasan di balik model datanya. `database.py`,
`schemas/ahsp.py`, dan `services/ahsp.py` merujuk ke **nomor bagian 2 dan 3** di dokumen itu
dari docstring-nya — kalau memangkasnya lagi, jaga penomoran itu.

**`docs/errata-serah-terima.md`** — Dokumen Serah Terima (PDF, di luar repo) disusun 10
Agustus 2026 dan repo sudah bergerak sejak itu. Kalau errata dan PDF bertentangan, errata
yang benar. Baca ini sebelum memercayai PDF-nya.

Arsip keputusan kategori: `docs/bundel-kategori-claude-code.md`, `docs/final_peta.json`,
`docs/seed_kategori.sql` (yang benar-benar dijalankan `backend/app/seed_kategori.py`).
Migrasi tahun yang sudah dijalankan: `docs/perbaikan-tahun-katalog.sql`. Pembungkus
Python-nya (`backend/perbaiki_tahun.py`, 300 baris) dibuang 22 September 2026 — sekali
jalan, sudah jalan, dan SQL-nya tetap jadi catatan yang berlaku.

## Kebiasaan kerja

- Baca dulu file yang relevan sebelum edit. Jangan asumsi struktur.
- Tunjukkan rencana/diff sebelum eksekusi perubahan besar (skema DB, banyak file).
- Jangan bikin fitur di luar scope yang diminta dalam satu sesi.
- Kalau ragu soal keputusan yang mengubah kode — **tanya dulu**, jangan langsung eksekusi.
- Setelah ubah frontend: jalankan `npx tsc -b` dan `npm run build` sampai bersih.
- Setelah ubah backend: jalankan tes, semuanya harus lulus.
- Jangan mengaku sudah menguji sesuatu yang belum diuji.
