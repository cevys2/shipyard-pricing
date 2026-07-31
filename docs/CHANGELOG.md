# Catatan Perubahan — shipyard-pricing

Ditulis untuk dibaca cepat: apa yang berubah, kenapa, dan apa bedanya buat orang yang
memakai aplikasinya. Yang terbaru di atas.

Versi bacanya (lebih enak dibuka): lihat tautan artefak di pesan sesi, atau baca berkas ini
langsung di GitHub.

---

## Belum di-deploy — sedang dikerjakan

Branch `fix/impor-docking-transaksi`. Menangani kegagalan impor docking
KMP. RHAMA GIRI NUSA (31 Juli 2026, 396 baris) yang berakhir `Failed to fetch`.

- **Penomoran ID impor tidak lagi bisa tabrakan** (`fe0f5eb`) — nomor urut dihitung di
  dalam transaksi yang sama dengan penyimpanannya, dan dikunci per kapal+tahun. Dua orang
  yang mengimpor kapal sama bersamaan tidak lagi saling menabrak. Sekaligus memperbaiki
  pencocokan awalan ID: `_` pada nama kapal dulu diperlakukan sebagai wildcard, sehingga
  nomor urut satu kapal bisa melompat gara-gara baris kapal lain.

Masih menyusul: Induk dan Addendum dalam satu transaksi, pesan error yang tidak lagi
tersembunyi di balik CORS, dan penggabungan INSERT.

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
