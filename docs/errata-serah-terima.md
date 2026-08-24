# Errata — Dokumen Serah Terima

Dokumen Serah Terima edisi **18 Agustus 2026** sudah tidak lengkap sejak commit `d3f3ef4`
(24 Agustus 2026). Berkas ini mencatat apa yang berubah, supaya PDF-nya tetap bisa dipakai
tanpa harus ditulis ulang.

Berkas ini sengaja dipertahankan, bukan dihapus. PDF Dokumen Serah Terima hidup di luar repo,
jadi tidak ada yang memaksanya ikut mutakhir waktu kodenya berubah. Berkas ini ikut — dan
begitu ada perubahan kode yang membuat PDF-nya salah, **catat di sini**, jangan dibiarkan
hanya di kepala.

**Aturan mainnya tetap:** kalau errata dan PDF bertentangan, errata yang benar — sampai PDF-nya
diperbarui, lalu berkas ini dikosongkan lagi.

> Catatan penyusunan: catatan di bawah merujuk ke **topik**, bukan nomor bagian, kecuali untuk
> risiko yang memang sudah bernomor di PDF. Nomor bagiannya belum diisi karena penyusunnya
> tidak sedang memegang PDF-nya. Tolong lengkapi waktu PDF-nya dibuka.

---

## A. Sudah tidak berlaku — koreksi wajib

### A1. §Impor Excel — "dua mode impor"

**Salah sejak 24 Agustus 2026.** Sekarang ada **tiga**: Laporan Docking, **Repair List /
Rincian Negosiasi**, dan Format Rapi. Mode Repair List membaca dokumen kesepakatan di *awal*
pekerjaan ("REPAIR LIST" / "RINCIAN"), yang bentuknya berbeda dari laporan realisasi — paling
menentukan, kolom harga satuannya berjudul "SATUAN", bukan "HARGA".

Kenapa penting: sebelum ini repair list harus diekstraksi manual di luar aplikasi. Orang yang
membaca PDF akan mengira pekerjaan itu masih perlu.

### A2. §Struktur tabel — daftar kolom `tabel_katalog_harga`

**Bertambah empat kolom nullable:** `volume` (NUMERIC), `satuan` (TEXT), `induk_uraian` (TEXT),
`keterangan` (TEXT). Ditambahkan lewat `ensure_katalog_kolom_rincian()`, dipanggil sebelum
`ensure_kategori_table()` di `main.py`.

Tidak ada backfill: 7.058 baris lama tetap `NULL` di keempatnya, dan itu jawaban yang jujur —
nilainya memang tidak diketahui. Tidak ada kolom lama yang diubah atau dihapus.

Kenapa penting: keempatnya **sengaja tidak ikut di-UPDATE** oleh `bulk_patch()`. Layar edit
katalog cuma mengirim delapan kolom lama; kalau keempatnya ikut, menyunting satu sel apa pun
akan menimpanya jadi `NULL` tanpa error. Siapa pun yang menambahkannya ke SQL itu tanpa juga
mengirim nilainya dari layar akan menghapus data provenance impor secara diam-diam.

### A3. §Katalog harga — "volume_satuan menyimpan volume dan satuan"

**Tidak pernah begitu.** `volume_satuan` berisi **satuan saja** — "Ls", "Hari", "Kali". Dugaan
bahwa isinya `"269 m²"` keliru; kuantitasnya tidak pernah tersimpan dari jalur mana pun.

Di `docking_parser` angkanya bahkan sudah dibaca sejak awal, tapi cuma dipakai membagi kolom
Jumlah jadi harga satuan, lalu dibuang. Sekarang ikut tersimpan di `volume`.

Kenapa penting: siapa pun yang membangun laporan nilai kontrak dari `volume_satuan` akan
mendapat angka yang salah tanpa tanda apa pun.

### A4. §Risiko impor — "aplikasi tidak bisa memverifikasi impornya sendiri"

**Sudah tidak berlaku untuk jalur Repair List.** Sebelum menyimpan, layar pratinjau
menampilkan nilai yang terbaca, angka **JUMLAH** yang tertulis di berkas, dan selisihnya —
dihitung ulang tiap kali tabelnya disunting. Diverifikasi terhadap tiga berkas Basarnas:
385 baris, Rp 7.933.170.000, selisih Rp 0.

**Masih berlaku untuk jalur Laporan Docking**, dan itu disengaja. Laporan docking punya baris
tarif bersyarat (Keel block, Bottom share, "Repair Propeller Blade jika terjadi kerusakan")
yang berharga satuan tapi kolom Jumlah-nya kosong dan memang tidak ikut TOTAL BIAYA. Palang
yang berbunyi merah padahal impornya benar akan cepat diabaikan.

### A5. §Kategori — "90 alias"

**Sekarang 100.** Tujuh ditambahkan 18 Agustus, tiga lagi 24 Agustus. Disimulasikan terhadap
cadangan produksi 24 Agustus: 6.673 baris kategorinya tidak berubah, 385 yang kosong terisi,
**nol tergeser**.

### A6. §Pengujian — "97 tes"

**Sekarang 201.**

### A7. §Impor Format Rapi — "berkas berisi banyak kapal"

**Sekarang ditolak dengan menyebut nama kapalnya.** Sebelumnya berkas seperti itu tetap
diproses sampai selesai: seluruh barisnya tercatat atas nama kapal yang kebetulan muncul
paling atas, tanpa peringatan apa pun. Karena kapal dan tahun ikut membentuk prefix ID baris,
salahnya permanen.

Perusahaan dan tipe yang bercampur cuma memperingatkan — keduanya tidak ikut ke ID, jadi masih
bisa dibetulkan lewat layar edit.

---

## B. Masih berlaku — jangan dianggap beres

### B1. Risiko #11 (nama kapal bebas ketik) — terbuka, dan sekarang ada buktinya

Cadangan produksi 24 Agustus memuat **`KMP. PRIMA  NUSANTARA`** (dua spasi) dan
**`KMP. PRIMA NUSANTARA`** sebagai dua kapal berbeda. Berkas repair list menulis
`KN. SAR 233` sementara katalog menyimpan `KN SAR ANTAREJA 233`; `KMP. GILIMANUK II`
tersimpan sebagai `KMP. GILIMANUK`.

Akibat yang sudah terukur: waktu mencocokkan baris katalog ke berkas Excel sumbernya untuk
mengisi kuantitas, 161 baris gagal terhubung semata-mata karena namanya beda.

### B2. Cakupan kategori akan turun lagi tiap impor, bukan sekali beres

PDF edisi 18 Agustus mencatat 100% setelah deploy. Per 24 Agustus angkanya **94,5%** — 385
baris repair list yang baru masuk belum punya alias. Setelah deploy `d3f3ef4` kembali 100%.

Sebabnya belum berubah: `selaraskan_kategori()` cuma jalan saat app start, **belum di jalur
impor**. Selama itu belum diperbaiki, polanya akan berulang: turun tiap impor, pulih tiap
deploy. Angka "100%" di dokumen mana pun cuma benar sesaat — hitung ulang sebelum mengutip.

### B3. Risiko #5 (penghapusan permanen tanpa jejak) — belum tertutup

Palang rekonsiliasi menjaga **saat impor**, bukan sesudahnya. Baris yang terhapus dari layar
katalog tetap hilang tanpa cara memulihkannya; `audit_log` mencatat bahwa penghapusan terjadi,
bukan isi barisnya.

### B4. Kuantitas ada di 31% baris, sisanya tidak akan pernah ada

Backfill **sudah dijalankan** 25 Agustus 2026 dari 20 berkas Excel di arsip: 2.127 baris
lama terisi `volume`/`satuan`/`induk_uraian`/`keterangan`, plus 83 baris dari dua kapal baru.

Keadaan sekarang: `volume` 2.210 dari 7.142 baris (31%). Sisanya tetap `NULL`, dan itu
permanen kecuali berkas sumbernya ketemu:

- **420 baris** dilewati karena berkasnya memberi lebih dari satu volume untuk kunci yang
  sama — sengaja tidak ditebak.
- **4.511 baris** tidak punya berkas sumber sama sekali.

Cadangan keadaan sebelum backfill (2.127 baris lengkap) ada di `backfill-rollback.csv`,
di luar repo. Diverifikasi sesudahnya: nol baris hilang, nol kolom lama berubah.

---

## C. Sudah diketahui, belum dikerjakan

### C1. Pencarian belum mencakup `induk_uraian`

`KOLOM_CARI_KATALOG` masih dua kolom, jadi mengetik "Main Engine Tengah" tidak menemukan baris
part yang konteksnya ada di kolom itu. Mencari nama partnya sendiri tetap jalan.

Bukan sekadar mengubah satu tuple: ekspresi index harus persis sama dengan ekspresi query, dan
`CREATE INDEX IF NOT EXISTS` **tidak** membangun ulang index yang namanya sudah ada — index
lamanya tetap terpasang tapi tidak pernah tersentuh lagi. Perlu nama index baru + DROP yang lama.

### C2. `induk_uraian` jalur docking tidak memisahkan ukuran pipa

Rantai induk menyebut jalur pipanya ("Pipa isap BBM", "Pipa outboard got"), tapi ukurannya ada
di baris **saudara** tepat di atasnya (`- Pipa Sch. 40 uk 1,5"`), bukan di baris induk. Dua
Elbow di jalur yang sama tetap terlihat serupa.

Per cadangan 24 Agustus ada **35 kelompok / 177 baris** yang uraian, kapal, tahun, dan tipenya
sama persis tapi harganya berbeda. Sebagian besar itu data yang sah — beda ukuran, beda
sub-item — yang belum punya tempat untuk menyimpan pembedanya.

### C3. Berkas Excel sumber tidak dikumpulkan di satu tempat

68% baris katalog sudah kehilangan berkas sumbernya. Angka itu akan terus tumbuh selama
berkasnya tidak diarsipkan per kapal per tahun, dan ini satu-satunya bagian yang tidak bisa
diperbaiki belakangan.

### C4. ~~Dua kapal di arsip belum masuk katalog~~ — selesai 25 Agustus 2026

`MV. AQUA BLU` (49 baris) dan `KLM. ILIKE` (35 baris) sudah masuk. Katalog kini 7.142 baris.

### C5. Aplikasi belum menghasilkan keluaran apa pun

Penawaran masih disusun manual di Excel. Ini jurang terbesar yang tersisa antara "katalog" dan
"alat yang menyelesaikan pekerjaan", dan tidak berubah oleh commit `d3f3ef4`.

---

## Cara memakai berkas ini

Tiap catatan sebutkan: bagian berapa di PDF, apa yang sekarang salah, dan apa yang benar.

```
### A1. §7.C — "Tab AHSP tidak bisa membuat material baru dari sana"

**Salah sejak Sesi 3.2.** [penjelasan apa yang sebenarnya terjadi sekarang]

Kenapa ini penting diperbaiki: [akibatnya kalau orang percaya versi lama]
```

Tiga kelompok yang dipakai:

- **A. Sudah tidak berlaku — koreksi wajib**
- **B. Masih berlaku — jangan dianggap beres** (angka yang bergeser, risiko yang belum tutup)
- **C. Sudah diketahui, belum dikerjakan**

---

Terakhir diperbarui: **25 Agustus 2026**, sesudah backfill dan impor dua kapal baru.

Terakhir dikosongkan: **18 Agustus 2026**, bersamaan dengan terbitnya PDF edisi 18 Agustus 2026.

Edisi PDF sebelumnya: 10 Agustus 2026, commit `9513753`.
