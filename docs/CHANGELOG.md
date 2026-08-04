# Catatan Perubahan — shipyard-pricing

Ditulis untuk dibaca cepat: apa yang berubah, kenapa, dan apa bedanya buat orang yang
memakai aplikasinya. Yang terbaru di atas.

Versi bacanya (lebih enak dibuka): lihat tautan artefak di pesan sesi, atau baca berkas ini
langsung di GitHub.

---

## 3 Agustus 2026 — upah dan alat bisa diinput, dan fondasi Struktur Biaya

Dua langkah pertama Langkah 3 roadmap (lihat
[rencana-langkah-3-struktur-biaya.md](rencana-langkah-3-struktur-biaya.md)).

**Katalog Material sekarang menampung empat jenis, bukan cuma bahan.** Ada pemilih
Bahan / Upah / Alat / Konsumabel di atas tabel. Sebelumnya `jenis = 'BAHAN'` dikunci mati di
enam tempat di kueri, jadi tidak ada satu pun cara memasukkan tarif tukang atau alat —
padahal analisa harga satuan tanpa upah dan alat cuma jadi daftar belanja.

Untuk Upah dan Alat, kolom Supplier dan Kapal hilang dari tabel, form, dan susunan tempel
Excel. Tarif tukang dan kompresor sendiri tidak dibeli dari supplier mana pun; menampilkan
dua kolom yang selamanya kosong cuma bikin orang mengira ada yang belum diisi.

Tab Bahan tidak berubah isinya sama sekali — nilai bawaannya tetap `'BAHAN'`, jadi kueri yang
dijalankan sama persis dengan sebelumnya. Ada tes otomatis yang menjaga batas itu.

**Tabel `ahsp` dan `ahsp_komponen` beserta API-nya sudah berdiri**, tanpa tampilan dulu.
Tiga hal yang sengaja ditolak aplikasinya:

- **Komponen tanpa harga tidak pernah dihitung sebagai nol.** Analisa yang separuh biayanya
  belum berharga ditandai belum lengkap, komponennya disebut satu per satu, dan harga
  jualnya ditahan — tidak dikeluarkan angka yang terlihat seperti harga final.
- **Mata uang berbeda tidak dijumlahkan dan tidak dikonversi.** Konversi butuh kurs, kurs
  butuh tanggal dan sumber yang disepakati; menebaknya sama saja mengubah harga diam-diam.
- **Menyimpan rincian itu satu transaksi penuh.** Kalau satu baris bermasalah, tidak ada
  satu pun baris yang tersimpan — pelajaran yang sama dengan perbaikan impor docking
  31 Juli.

Baris komponen menyimpan **qty, shift, dan jumlah hari terpisah**, bukan satu koefisien hasil
perkalian. "4 orang, 1 shift, 0,07 hari" bisa diperiksa orang lapangan; "0,28" tidak bisa.
Semua angka diproses sebagai desimal tepat, bukan bilangan pecahan biner — kalau tidak,
4 × 1 × 0,07 × 50.000 menghasilkan 14.000,000000000002.

**Tidak ada markup di tingkat analisa harga satuan.** Ini diverifikasi dari file Excel asli
perusahaan: 54 dari 54 blok punya nilai akhir sama persis dengan jumlah subtotalnya, tanpa
satu pun baris overhead atau keuntungan. Marginnya sudah tertanam di tarif tiap komponen, dan
PPN ditambahkan sekali di tingkat dokumen penawaran — bukan per item.

## 1 Agustus 2026 — cadangan database akhirnya benar-benar ada

**`backup-service` selama ini tidak mencadangkan apa pun.** Berkas `backup.py`-nya kosong
0 byte sejak dibuat 27 Juli 2026 — hash blob-nya `e69de29`, hash baku Git untuk berkas
kosong. Service-nya sukses tiap kali menjalankan berkas kosong, keluar dengan status 0,
tidak pernah terlihat merah. Satu-satunya cadangan yang ada cuma tabel
`backup_katalog_harga_juli2026` berisi 3.054 baris, sementara tabelnya sekarang 4.914 baris.

Sekarang skripnya menyalin **seluruh tabel** jadi CSV, membungkusnya jadi satu `.tar.gz`
beserta manifest jumlah baris, lalu mengunggahnya ke Backblaze B2 — di luar Railway, jadi
selamat kalau ada apa-apa dengan platformnya.

Dua penolakan yang disengaja supaya kegagalan diam tidak terulang: menolak mengunggah kalau
tidak ada tabel atau semua tabel kosong, dan memverifikasi ukuran objek dengan membacanya
ulang dari B2 sesudah unggah. Kalau salah satu tidak terpenuhi, service-nya gagal terang-terangan.

Cadangan pertama sudah jalan dan **sudah diuji pulih**: diunduh kembali dari B2, dibongkar,
dan jumlah baris tiap tabel cocok persis dengan database. Termasuk 2.950 baris yang memuat
newline di dalam sel — dibandingkan byte demi byte, identik.

---

## 31 Juli 2026 (ketiga) — impor tidak lagi menggantung tanpa kabar

**Impor docking punya batas waktu 5 menit.** Sebelumnya permintaan yang menggantung tidak
pernah selesai dan tombolnya terkunci selamanya. Kalau batas itu terlampaui, pesannya
menyebut akibatnya: penyimpanan belum tentu gagal, jadi muat ulang dan cek tabelnya dulu
sebelum mencoba lagi. Mencoba ulang secara buta justru yang bikin kejadian 31 Juli
membingungkan.

**Saat menyimpan, jumlah barisnya ditampilkan** beserta peringatan jangan menutup halaman.

Deteksi tahun dari nama berkas sengaja dibiarkan manual — angka tahun di nama berkas itu
tahun terbit dokumen realisasi (saat deal dan pembayaran), bukan waktu survei dan
pengerjaan, jadi keduanya memang bisa berbeda.

---

## 31 Juli 2026 (kedua) — impor docking dan input material

Menangani kegagalan impor docking KMP. RHAMA GIRI NUSA (396 baris) yang berakhir
`Failed to fetch`, dan mempermudah input katalog material.

**Impor docking tidak bisa lagi menyimpan separuh data.** Induk dan Addendum kini satu
transaksi. Sebelumnya Induk bisa tersimpan sementara Addendum gagal, tanpa cara bagi
pengguna untuk tahu bahwa separuh datanya sudah masuk.

**Penomoran ID tidak bisa lagi tabrakan.** Nomor urut dihitung di dalam transaksi yang
sama dengan penyimpanannya, dan dikunci per kapal+tahun sehingga dua orang yang mengimpor
kapal sama bersamaan tidak saling menabrak. Sekaligus memperbaiki pencocokan awalan ID —
tanda `_` pada nama kapal dulu diperlakukan sebagai wildcard, sehingga nomor urut satu
kapal bisa melompat gara-gara baris kapal lain.

**Pesan error database sekarang terbaca.** Sebelumnya error tersangkut di lapisan yang
membuat browser memblokir responsnya, jadi yang muncul cuma `Failed to fetch` dan sebab
aslinya hilang. Sekarang tampil sebagai pesan yang bisa ditindaklanjuti.

**Impor jadi jauh lebih sedikit bolak-balik ke database** — 396 baris turun dari 400
perintah menjadi 8.

**Input katalog material punya jalan tengah.** Sebelumnya cuma ada dua pilihan: menempel
seluruh tabel dari Excel, atau mengisi satu baris manual berulang kali.

- Form **Input Beberapa Baris**: supplier, kapal, tahun, tanggal, mata uang, dan dokumen
  diisi sekali di atas; per barang tinggal mengetik nama, part number, satuan, dan harga.
  Untuk quotation 25 baris, isian turun dari 225 sel jadi 100 plus 6 isian bersama.
- **Pratinjau paste bisa diedit di tempat**, tidak perlu mengulang paste dari Excel gara-gara
  satu sel meleset. Tiap kolom punya tombol isi-ke-bawah, dan tiap baris bisa diduplikat.

---

## 31 Juli 2026 — `ac6414e`

- **Kolom harga akhirnya menerima desimal.** Sebelumnya mengetik `49.0` langsung kehilangan
  titiknya, jadi harga pecahan mustahil dimasukkan lewat form. Koma juga diterima (`49,5`).
  Titik sebagai pemisah ribuan sengaja tidak ditebak — `1.050` ambigu dan menebaknya bisa
  mengubah harga diam-diam.
- **Grafik tren material bisa dipersempit** per supplier dan per material.
- **Paste dari Excel punya isian Jenis Dokumen dan Nomor Dokumen** yang berlaku untuk seluruh
  baris. Sebelumnya tidak ada tempat sama sekali untuk nomor quotation, sehingga asal-usul
  29 dari 46 titik harga tidak tercatat.

## 30 Juli 2026 — `d18c8ab`

- **Filter kapal, supplier, dan tahun sekarang melihat seluruh riwayat harga.** Sebelumnya
  hanya melihat harga terakhir, jadi material yang pernah dibeli untuk kapal A tapi harga
  terakhirnya dari kapal B hilang dari hasil filter A. Nyata terjadi: filter ANTAREJA
  menampilkan 18 material padahal 25. Harga yang ditampilkan kini ikut kapal yang difilter.
- **Opsi filter tidak pernah menyesatkan lagi** — sebuah pilihan hanya muncul kalau
  memilihnya benar-benar menghasilkan baris.
- **Median harga jual jasa menyebutkan kapal penyusunnya.** Median dari 2 kapal dan median
  dari 20 kapal terlihat sama meyakinkan tanpa informasi ini.
- **Tren harga material punya grafik**, bukan cuma tabel daftar. Satu grafik per mata uang.
- **Pratinjau dampak paste**: sebelum menyimpan, tiap baris diberi label material baru,
  titik harga baru (dengan persen perubahannya), atau dilewati karena harganya sama persis.
- **Part number jadi penentu identitas material** kalau ada. Tidak diwajibkan, karena cat,
  plat, dan konsumabel memang tidak punya nomor.

## 29 Juli 2026 — `78fc310` dan `aecc496`

Langkah 2 roadmap: fondasi tren harga.

- **Tab Analitik baru**: tren harga jual jasa 2024–2026 dari data realisasi docking, dibaca
  saja tanpa mengubah tabel aslinya.
- **Drawer Riwayat Harga** di tiap baris material — daftar harga, grafik, tambah dan hapus
  titik harga.
- **Jejak audit**: siapa menambah, mengubah, atau menghapus data, tercatat di tabel terpisah.
- **Material kembar digabung** — 43 baris menjadi 21 material unik. Duplikasi itu membuat
  riwayat harga satu barang terbelah sehingga tren tidak akan pernah terbentuk.
- **Menyimpan material tidak lagi memalsukan riwayat harga.** Sebelumnya membetulkan typo
  pada nama pun menghasilkan satu "titik harga" baru bertanggal hari itu.
- Dokumen [catatan-tabel-katalog-harga.md](catatan-tabel-katalog-harga.md) mencatat apa yang
  dilakukan dan tidak dilakukan terhadap tabel harga jasa.

## 28 Juli 2026 — `d5ca3ea` dan `8d1c8e1`

Langkah 1 roadmap: tab Katalog Material.

- Tabel `supplier`, `sumber_daya`, dan `sumber_daya_harga`, beserta tampilan katalognya.
- Kolom kapal, mata uang, dan tahun pembelian.
- Kolom kode dihapus — part number asli lebih pas ditaruh di spesifikasi.

## 27 Juli 2026 — `009af0e` dan `70305c4`

- Login dipindah sepenuhnya ke Portal; aplikasi ini hanya memverifikasi token.
- Perombakan tampilan dan pemindahan konfigurasi ke variabel lingkungan.
