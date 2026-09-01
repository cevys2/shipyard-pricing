# Catatan Perubahan — shipyard-pricing

Ditulis untuk dibaca cepat: apa yang berubah, kenapa, dan apa bedanya buat orang yang
memakai aplikasinya. Yang terbaru di atas.

Versi bacanya (lebih enak dibuka): lihat tautan artefak di pesan sesi, atau baca berkas ini
langsung di GitHub.

---

## 1 September 2026 — angka total berhenti menyamar jadi harga satuan

**Berkas docking yang menulis "Sat" sekarang terbaca benar.** Ini kegagalan paling mahal
sejauh ini, dan sepenuhnya tanpa suara: tidak ada error, tidak ada peringatan, dan angkanya
cukup masuk akal sehingga tidak ada alasan curiga.

Semua berkas docking yang pernah ditangani menulis sub-kolom harga satuannya **"Satuan"**.
"Docking DEAL KMP. PRATHITA IV" menulisnya **"Sat"** — kata yang sama persis dengan sub-kolom
satuan di grup VOLUME. Pencocokan sama-persis meleset, lalu parser jatuh ke kolom terakhir
grup harga: kolom **Jumlah**. Seluruh 154 baris masuk katalog dengan angka **total** sebagai
harga satuan.

"Penggunaan listrik harian, 19 hari" tersimpan seharga Rp 13.300.000, bukan Rp 700.000.
Baris ber-volume 1 ("Ls", "kali") kelihatan benar, karena di situ satuan dan total memang sama
— jadi gejalanya cuma muncul di sebagian baris.

Buktinya satu angka: jumlah seluruh "harga satuan" yang masuk persis sama dengan angka JUMLAH
di berkasnya, Rp 1.154.862.810. Sesudah perbaikan, volume × harga menjumlah ke angka yang
sama, selisih Rp 0.

**Kalau kamu pernah mengimpor berkas docking bertajuk "Sat", barisnya ada di katalog sekarang.**
Tandanya: harga satuan yang kelihatan terlalu besar untuk satuannya, di baris yang volumenya
lebih dari 1. Impor ulang berkasnya akan menghasilkan angka yang benar.

**Palang baru yang memeriksa bentuk header, bukan angkanya.** Kalau di satu grup harga
sub-kolom Satuan dan Jumlah terbaca di kolom yang sama, layar pratinjau bilang sebelum apa pun
disimpan. Palang ini tidak bisa berbunyi palsu seperti palang penjumlahan — dia memeriksa
susunan judul, bukan menjumlahkan baris yang boleh saja bersyarat.

**Nama kapal tidak lagi kebawa titik dua.** Di berkas ini label dan nilainya menyatu dalam satu
sel: `": KMP PRATHITA IV"`. Titik duanya dulu ikut ke nama kapal, lalu ikut jadi prefix ID
baris. Berlaku juga untuk nama pemilik.

**Tahun terisi walau berkasnya tidak menyebut "PERIODE DOCKING".** Urutan barunya: periode
docking → tanggal **NAIK DOCK / TURUN DOCK** (diambil tahunnya saja) → tanggal perjanjian →
nama sheet/berkas → upaya terakhir dari sel yang benar-benar bertipe tanggal. Yang terakhir
**mengaku sebagai tebakan** lewat peringatan di layar, dan sengaja cuma membaca sel bertipe
tanggal: itu yang membuat "TAHUN PEMBUATAN : 1968" (angka) dan nomor surat berakhiran
"/II/2024" (teks) tidak ikut terbaca. Sebelumnya berkas seperti ini bertahun kosong, dan tanpa
tahun barisnya tidak bisa disimpan sama sekali.

**Layar pratinjau docking: kolom Vol dan Sat dilebarkan, Keterangan menyembunyikan diri kalau
kosong.** Di berkas seperti PRATHITA IV kolom KETERANGAN di Excel-nya kosong di seluruh 281
baris, jadi yang tersisa cuma kolom kosong yang mendesak Vol — padahal Vol bisa berisi 6000
(ltr) dan angkanya terpotong. Kolomnya disembunyikan, bukan dihapus: dialah yang menentukan
sebuah baris masuk Addendum, jadi begitu ada isinya dia muncul lagi. Dihitung per tabel, jadi
Induk boleh kehilangan kolomnya sementara Addendum tetap menampilkannya. Isinya tetap
tersimpan apa pun yang tampil di layar.

**README: `createdb shipyard_test` ternyata belum cukup.** `tabel_katalog_harga` tidak dibuat
oleh repo ini, jadi di database yang benar-benar kosong seluruh suite error di fixture dengan
pesan yang menuding hal lain. DDL-nya sekarang ada di README.

## 24 Agustus 2026 — repair list masuk sendiri, dan impornya memeriksa dirinya sendiri

**Mode impor ketiga: Repair List / Rincian Negosiasi.** Berkas "REPAIR LIST" atau "RINCIAN"
sekarang bisa diunggah langsung. Seksi angka romawi jadi kategori, sub-seksi huruf dan baris
induk yang tidak berharga jadi konteks, dan baris berharga di kedalaman mana pun ikut terambil.
Sebelumnya cuma ada parser untuk "REALISASI BIAYA DOCKING" — dokumen yang lahir di akhir
pekerjaan. Repair list lahir di awal dan justru jadi dasar penagihan, dan memasukkannya berarti
mengekstraksi manual di luar aplikasi.

**Impornya sekarang memeriksa dirinya sendiri.** Sebelum apa pun disimpan, layar pratinjau
menunjukkan tiga angka berdampingan: nilai yang terbaca, angka **JUMLAH** yang tertulis di
berkas, dan selisihnya. Hijau kalau nol, merah kalau tidak. Angkanya dihitung ulang tiap kali
tabelnya disunting, jadi menghapus satu baris langsung terlihat. Sebelumnya satu-satunya cara
tahu ada baris yang jatuh adalah menjumlahkan sendiri di luar aplikasi — dan kalau tidak
dilakukan, tidak ada yang memberi tahu.

**Volume disimpan sebagai angka — di ketiga jalur impor, bukan cuma yang baru.** Kolom baru
`volume` dan `satuan` mendampingi `volume_satuan` yang lama (yang tidak disentuh sama sekali).
Tanpa angkanya, "berapa nilai pekerjaan pengecatan untuk kapal ini" tidak bisa dijawab, dan
membandingkan harga antar kapal jadi menyesatkan: pengecatan di dua kapal sama-sama Rp 200.000
per m², tapi satu 269 m² dan satu 230 m².

Yang mungkin mengejutkan: `volume_satuan` selama ini **tidak pernah** berisi "269 m²" — isinya
satuan saja ("Ls", "Hari", "Kali"). Kuantitasnya tidak pernah tersimpan. Di impor Laporan
Docking angkanya bahkan sudah dibaca sejak dulu, cuma dipakai membagi kolom Jumlah jadi harga
satuan, lalu dibuang. Sekarang ikut tersimpan, dan tabel pratinjau docking punya kolom Vol,
Sat, Nilai, dan Keterangan sendiri.

**Angka "Total" di pratinjau docking sekarang berarti sesuatu.** Sebelumnya yang dijumlahkan
harga satuannya saja — menambahkan Rp/m² ke Rp/hari ke Rp/kali. Sekarang yang dijumlahkan
volume × harga.

**Blok tanda tangan berhenti jadi baris harga.** Di baris "Diketahui dan Disetujui oleh :"
ada sel tanggal yang mendarat di kolom harga satuan, dan pembaca .xls mengembalikannya sebagai
nomor seri Excel. Jadi tiap berkas Laporan Docking menyumbang satu baris katalog palsu seharga
Rp 46.197 — cukup masuk akal sebagai harga sehingga tidak pernah ada yang curiga. Kalau kamu
pernah mengimpor laporan docking, baris seperti itu kemungkinan ada di katalog: cari uraian
yang mengandung "Disetujui" atau "Diketahui".

**Baris beruraian sama tidak lagi ambigu.** Kolom baru `induk_uraian` menyimpan konteks baris
induknya. Di satu repair list ada tiga baris berbunyi persis "Excentric P/N 51.06501-0339" —
yang membedakan cuma baris induk yang tidak berharga di atasnya (Main Engine Tengah / M/E Kiri
/ M/E Kanan), dan harganya memang beda: Rp 12,5 juta untuk yang tengah, Rp 15 juta untuk kiri
dan kanan. Di tabel katalog, induknya muncul sebagai baris kecil di atas uraiannya. Dari tiga
berkas: 44 kelompok baris yang tadinya tidak terbedakan jadi nol.

**Kolom Keterangan ikut tersimpan.** Ada di ketiga berkas dan sering berisi catatan yang
menjelaskan harganya, mis. "Dilaksanakan oleh Kantor Kesehatan Pelabuhan".

**Impor "Format Rapi" menolak berkas berisi lebih dari satu kapal.** Sebelumnya berkas seperti
itu tetap diproses sampai selesai: seluruh barisnya tercatat atas nama kapal yang kebetulan
muncul paling atas, tanpa peringatan apa pun — dan karena kapal dan tahun ikut membentuk ID
baris, salahnya permanen. Sekarang ditolak dengan menyebut kapal-kapalnya. Perusahaan dan tipe
yang bercampur cuma memperingatkan, karena keduanya masih bisa dibetulkan lewat layar edit.

**Empat template laporan docking yang dulu gagal diam-diam sekarang terbaca.** Berkas yang
menamai kolomnya "Nama Barang" alih-alih "Uraian", atau "INDUK (Rp.)" alih-alih "Harga",
sebelumnya menghasilkan **nol baris tanpa pesan error apa pun** — tidak ada bedanya dengan
berkas kosong. Begitu juga berkas yang tidak menulis "Nama Kapal" tapi menyebut kapalnya di
baris "Lokasi". Total 714 baris yang selama ini tidak bisa masuk.

**Baris anak di laporan docking membawa konteks induknya.** Di satu laporan ada 15 baris
berbunyi persis "Elbow" dengan harga Rp 300.000 sampai Rp 2.100.000. Harganya memang beda —
jalur pipanya beda — tapi katalog tidak menyimpan alasannya. Sekarang tiap baris menyebut
jalur pipanya sendiri.

**Sepuluh kategori baru dikenali.** Sebutan seksi di repair list bentuknya beda dari laporan
realisasi. Tanpa alias barunya, 374 dari 385 baris masuk tanpa kategori sama sekali; sekarang
385 dari 385 terpetakan.

Satu hal yang sengaja belum dikerjakan: kotak pencarian belum mencari ke dalam kolom induk,
jadi mengetik "Main Engine Tengah" belum menemukan baris part-nya. Mencari nama partnya sendiri
tetap jalan.

---

## 4 Agustus 2026 — mengisi Upah dan Alat tidak lagi satu-satu

**Tempel satu kolom sekaligus.** Salin daftar nama dari mana pun, tempel di kotak Nama baris
pertama, dan tiap baris teks jadi satu baris sendiri — barisnya ditambah otomatis kalau
kurang. Menyalin beberapa kolom dari Excel juga bisa: tiap kolom mendarat di tempatnya.
Sebelumnya menempel teks banyak baris ke satu kotak cuma menghasilkan satu baris kacau,
karena begitulah perilaku bawaan browser, sehingga daftar apa pun harus disalin sel per sel.

**Istilah pembelian tidak lagi dipaksakan ke tarif sendiri.** Untuk Upah dan Alat, "Tahun
Pembelian" jadi **"Tahun Berlaku"**, "Jenis Dokumen" jadi **"Dasar Penetapan"** dengan pilihan
SK Manajemen / Memo Internal / Hasil Rapat menggantikan Quotation / PO / Invoice yang tidak
pernah relevan, dan "Nomor Dokumen" jadi "Nomor SK / Memo". Tarif tukang tidak dibeli dari
siapa pun; menanyakan tahun pembeliannya tidak pernah masuk akal.

**Kolom Part No. hilang untuk Upah.** Tenaga kerja tidak punya part number. Alat tetap punya —
model dan kapasitas ditulis di situ.

**Titik ribuan pada tempelan dibaca sebagai ribuan.** "150.000" sekarang menjadi seratus lima
puluh ribu, bukan 150. Sebelumnya titik selalu dibaca sebagai desimal — keputusan yang
disengaja untuk isian yang diketik satu per satu, karena "1.050" memang ambigu dan orang yang
mengetik bisa langsung melihat hasilnya. Untuk tempelan puluhan baris keadaannya terbalik:
tidak ada yang memeriksa satu per satu, dan kesalahan 1000× lolos tanpa jejak. Angka yang
ditafsirkan begitu dihitung dan dilaporkan di bawah tabel, jadi penafsirannya tidak diam-diam.
Format desimal dua angka seperti "45.10" dari quotation EUR tetap dibaca sebagai desimal.

## 4 Agustus 2026 — tab "Struktur Biaya"

Tampilan untuk tabel AHSP yang dibangun kemarin. Satu tab baru di sidebar.

Isinya: dua kartu ringkasan (berapa analisa yang rinciannya sudah lengkap, berapa komponen
yang belum berharga), daftar item yang dijual dengan status per baris, dan lembar rincian
yang bisa dibuka dengan mengklik barisnya.

**Urutan kelompok biaya mengikuti data, bukan dipatok.** Di file Excel asli urutannya
berbeda-beda per pekerjaan — 29 blok Upah-Alat-Bahan, 13 cuma Upah-Alat, 8 cuma Alat. Jadi
nomor kelompok diambil dari urutan komponennya, tidak dikunci Bahan-Upah-Alat.

**Menambah komponen baru bisa langsung dari lembar AHSP.** Ketik namanya; yang mirip di
katalog ditampilkan lebih dulu, opsi "buat baru" ada di bawahnya. Barang yang dibuat lewat
sini tersimpan ke Katalog Material juga — memang satu tabel yang sama dilihat dari dua layar.
Pencariannya sengaja memakai dua kata pertama saja: mengetik "Cat Epoxy 5kg" tidak akan
menemukan "Cat Epoxy" yang sudah ada kalau seluruh teksnya dipakai, dan di situlah barang
kembar lahir.

Baris yang komponennya belum berharga diberi latar kuning dan tulisan "belum ada harga",
tidak pernah nol. Kalau ada satu saja yang bolong, angka totalnya diredupkan, dilabeli
"subtotal sementara", dan diberi keterangan bahwa angka itu lebih rendah dari biaya
sebenarnya — harga jualnya sendiri ditahan backend.

Di bawah setiap total tertulis **"belum termasuk PPN"**. Karena harga jual sama persis dengan
biaya modal, angka itu mudah disalahartikan sebagai harga final ke pelanggan.

**Lembar rincian dirombak di hari yang sama: dua bentuk baris, bukan satu.**

Semula tiap baris punya kolom Qty · Satuan · Shift · Jml Hari yang sama, dan kolom terakhir
itu dinamai terhadap satuan yang dijual. Untuk pekerjaan per m² masih terbaca; untuk satuan
lain jadi omong kosong — "hari per Pcs" membuat pekerjaan maintenance terdengar seperti
produksi barang, dan baris pasir terpaksa diisi "Jml Hari = 1" yang tidak berarti apa-apa.

Yang terlewat: **Qty, Shift, dan Jml Hari bukan tiga fakta, melainkan cara menurunkan satu
angka** — koefisien AHSP, yang satuannya milik sumber dayanya sendiri, bukan milik barang
yang dijual. "3 orang × 1 shift × 0,02 hari" adalah cara menuliskan **0,06 OH**.

Sekarang tenaga kerja dan alat menampilkan penurunannya *beserta hasilnya* (Banyaknya ·
Shift · Lama → Koefisien "0,06 OH"), sementara bahan dan konsumabel cuma punya satu kolom
Koefisien — keduanya habis dipakai, tidak punya dimensi waktu sama sekali. Excel aslinya pun
sudah menunjukkan gejala ini: 18 dari 298 barisnya memang cuma memakai Qty × Harga.

Di bawah kotak Lama ada pembanding hidup: ketik 0,02 dan muncul "≈ 50 m² per hari". Kolom itu
punya satu mode gagal yang mahal — salah ketik 0,2 alih-alih 0,02 melipatgandakan harga 10×
tanpa terlihat aneh sedikit pun. Angka pembaliknya jauh lebih mudah dibantah orang lapangan.
Untuk koefisien di atas 1 hari kalimatnya dibalik jadi durasi ("3 hari untuk 1 Unit"), karena
di sana pembaliknya justru membingungkan.

**Catatan untuk yang memakai:** "koefisien" dan "OH" (Orang-Hari) adalah istilah baku AHSP
yang mungkin belum familiar. Artinya sederhana — berapa banyak sumber daya untuk satu satuan
yang dijual.

**Perbaikan menyusul di hari yang sama.** Menghapus material yang sedang dipakai di sebuah
analisa sebelumnya gagal dengan "Gagal menyimpan ke database" — benar bahwa tidak ada data
yang hilang, tapi tidak menyebutkan sebabnya, sehingga satu-satunya tindakan yang masuk akal
(mencoba lagi) dijamin gagal terus. Sekarang penolakannya menyebut barangnya dipakai di
analisa mana dan apa yang harus dilakukan. Selain itu: kotak Qty tidak lagi menampilkan
`2.000000`, komponen kembar ditolak saat dipilih alih-alih saat disimpan, dan tab ini
disembunyikan dari pengguna yang bukan admin — seluruh endpoint-nya memang dibatasi admin,
jadi sebelumnya mereka cuma mendapat pesan "Admin only".

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
