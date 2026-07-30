# Catatan: apa yang dilakukan branch `feat/analitik-tren-harga` ke `tabel_katalog_harga`

**Ringkasnya: dibaca, tidak diubah sama sekali.**

Dokumen ini sengaja dibuat supaya klaim di atas bisa diverifikasi, bukan cuma dipercaya.

*Status: sudah di-merge ke `main` sebagai `78fc310` (29 Juli 2026) dan ter-deploy.*

---

## 1. Yang TIDAK dilakukan

Tidak ada satu pun dari ini yang menyentuh `tabel_katalog_harga`:

- ❌ tidak ada `ALTER TABLE` — struktur kolom persis seperti sebelumnya
- ❌ tidak ada kolom baru (`layanan_id` / `kategori_id` di dokumen desain **belum** dibuat)
- ❌ tidak ada `INSERT` / `UPDATE` / `DELETE` baru dari fitur analitik
- ❌ tidak ada index, constraint, trigger, atau view baru di atasnya
- ❌ tidak ada pembersihan data (kategori yang berantakan **dibiarkan apa adanya**)

Jumlah baris sebelum dan sesudah seluruh pekerjaan branch ini: **4.239 → 4.239**
(diverifikasi setelah migrasi dan setelah smoke test API).

## 2. Yang dilakukan: hanya SELECT

Modul baru [`backend/app/services/analitik.py`](../backend/app/services/analitik.py) membaca
tabel ini untuk menghitung median harga jual per kategori pekerjaan per tahun. Semua query
di modul itu diawali `SELECT` — tidak ada perintah tulis.

Teks kategori di database berantakan (huruf besar-kecil campur, newline di tengah string,
non-breaking space dari sel Excel). **Itu dirapikan di dalam query saat dibaca, bukan dengan
memperbaiki datanya**:

```sql
upper(btrim(regexp_replace(replace(kategori_pekerjaan, chr(160), ' '), '\s+', ' ', 'g')))
```

Konsekuensinya: kalau normalisasi ini nanti dianggap keliru, cukup ubah satu konstanta —
tidak ada data yang perlu di-rollback.

## 3. Satu perubahan tulis yang menyentuh alur tabel ini: audit log

Fitur log perubahan mencatat siapa mengubah apa. Untuk `tabel_katalog_harga`, pencatatan
dilakukan **tanpa menyentuh tabelnya**: barisnya ditulis ke tabel terpisah `audit_log`.

Alasan memilih tabel terpisah daripada kolom `diubah_oleh`:
1. `tabel_katalog_harga` tidak boleh diubah strukturnya;
2. yang berguna justru riwayat perubahannya, bukan cuma penyunting terakhir.

Yang berubah di kode jalur tulis lama ([`services/catalog.py`](../backend/app/services/catalog.py)):
`bulk_create()` dan `bulk_patch()` sekarang menerima parameter `aktor` dan memanggil
`audit.catat()`. **Perintah SQL ke `tabel_katalog_harga` sendiri tidak diubah satu karakter pun** —
INSERT/UPDATE/DELETE-nya sama persis seperti sebelumnya.

## 4. Temuan tentang isi tabel — semuanya dibiarkan apa adanya

Pemeriksaan data memunculkan empat hal. Tidak ada satu pun yang diperbaiki; semuanya dicatat
di sini supaya jadi bahan keputusan nanti, bukan diam-diam diubah.

**212 grup baris identik, total 302 baris berlebih** — sama persis di kapal, tahun, tipe,
kategori, uraian, satuan, dan harga. Contohnya `Elbow sch40 3"` seharga 1.050.000 muncul
delapan kali di KMP. MARINA SEGUNDA 2024.

Ini sengaja **tidak** di-dedup. Tabel ini tidak punya kolom kuantitas, jadi delapan baris
seperti itu kemungkinan besar memang delapan item nyata di laporan aslinya — pengulangan
barisnya justru cara laporan mencatat jumlah. Menghapusnya berarti membuang data yang sah.
Kolom `id` juga nol duplikat, jadi tidak ada tanda impor ganda. Ini berbeda dari kasus
`sumber_daya` di bagian bawah dokumen, di mana duplikasinya terbukti kecelakaan impor dan
merusak fitur.

**Kerusakan encoding di data lama**, mis. `elbow sch40 ?3"` yang aslinya kemungkinan `Ø3"`.

**Jumlah kapal per tahun timpang** — 2024 dua kapal, 2025 delapan, 2026 dua puluh. Naik-turun
garis pada grafik bisa sekadar efek berubahnya campuran kapal, bukan bukti harga naik. Karena
itu halaman analitik menampilkan peringatan berisi angka ini, bukan menyembunyikannya.

**Tren per pekerjaan praktis tidak mungkin.** Dari 3.463 uraian unik, hanya 86 yang muncul di
lebih dari satu tahun, karena `uraian_pekerjaan` teks bebas. Yang bisa jadi tren cuma agregat
per kategori — dan dari 77 kategori, 18 punya data di dua tahun atau lebih.

## 5. Cara memverifikasi sendiri

```bash
# tidak boleh ada hasil selain di services/catalog.py (jalur tulis lama, tidak diubah)
grep -rn "INSERT INTO\|UPDATE \|DELETE FROM\|ALTER TABLE" backend/app/services/analitik.py

# jumlah baris harus tetap
psql "$DATABASE_URL" -c "SELECT COUNT(*) FROM tabel_katalog_harga;"   -- 4239

# struktur kolom harus tetap 10 kolom
psql "$DATABASE_URL" -c "\d tabel_katalog_harga"
```

---

# Perubahan DB lain di branch ini (di luar `tabel_katalog_harga`)

Supaya lengkap — ini yang **memang** diubah, semuanya di tabel milik Katalog Material:

| Perubahan | Tabel | Sifat |
|---|---|---|
| Dedup material kembar | `sumber_daya`, `sumber_daya_harga` | **destruktif, sekali jalan** |
| Unique index `uq_sd_identitas` | `sumber_daya` | menambah constraint |
| Tabel `audit_log` | *(baru)* | menambah tabel |

## Detail dedup (satu-satunya operasi destruktif)

**Masalah yang diperbaiki:** `bulk_create()` dulu selalu membuat master baru, jadi paste batch
yang sama dua kali menghasilkan material identik sebagai baris `sumber_daya` terpisah. Di data
produksi ini benar-benar terjadi: **11 item ke-input 3× menjadi 33 baris**. Akibatnya riwayat
harga satu barang terpecah ke beberapa master, dan tren harga tidak akan pernah terbentuk.

**Yang dijalankan** (di `_dedup_sumber_daya()`, [`database.py`](../backend/app/database.py)):
1. semua `sumber_daya_harga` dialihkan ke master ber-id terkecil di tiap grup kembar;
2. master kembar yang sudah kosong dihapus;
3. baris harga yang persis identik (harga, tanggal, supplier, mata uang sama) disisakan satu —
   baris begini adalah input berulang, bukan perubahan harga, dan kalau dibiarkan akan muncul
   sebagai titik palsu di grafik;
4. dipasang unique index supaya duplikat tidak bisa muncul lagi.

**Hasil di produksi:** 43 material → **21 material**, 43 titik harga → **21 titik harga**.
Tidak ada informasi harga yang hilang — yang hilang hanya salinan identiknya.

**Idempoten & aman diulang:** setelah `uq_sd_identitas` terpasang, fungsi ini langsung
keluar tanpa memindai apa pun, jadi tidak membebani tiap app start.

**Perhatian:** langkah ini **tidak punya rollback otomatis**. Kalau ingin cadangan sebelum
deploy pertama ke lingkungan lain, `CREATE TABLE sumber_daya_backup AS SELECT * FROM sumber_daya;`
dulu (di produksi sudah terlanjur jalan saat pengembangan branch ini, dan hasilnya sudah diverifikasi).

## Perbaikan perilaku: edit tidak lagi memalsukan riwayat harga

`bulk_patch()` dulu menyisipkan baris `sumber_daya_harga` baru **setiap kali** material di-edit —
membetulkan typo di kolom nama pun menghasilkan satu "titik harga" baru bertanggal hari itu.
Untuk tabel katalog biasa efeknya tak terlihat; untuk grafik tren itu fatal, karena riwayatnya
jadi campuran antara perubahan harga asli dan jejak penyuntingan.

Sekarang baris harga baru hanya disisipkan kalau ada yang benar-benar berubah (harga, mata uang,
supplier, tanggal berlaku, tahun pembelian, atau kapal). Respons `PATCH /material` menambah field
`titik_harga_baru` supaya jelas berapa yang benar-benar tercatat sebagai perubahan harga.

## Perbaikan perilaku: paste berulang tidak lagi menumpuk titik harga identik

Setelah `bulk_create()` memakai ulang material yang sudah ada, paste file yang sama dua kali
memang tidak lagi membuat material kembar — tapi masih menambah titik harga yang identik, yaitu
titik palsu yang sama seperti kasus di atas. Sekarang baris harga dilewati kalau sidik jarinya
(material, harga, mata uang, supplier, tanggal berlaku, tahun, kapal) sudah ada, termasuk
duplikat di dalam satu batch. Respons `POST /material/bulk` mengembalikan `saved`,
`titik_harga_baru`, dan `dilewati` supaya UI bisa menyebutkan berapa baris yang dilewati.

## Perbaikan: filter kapal/supplier/tahun melihat seluruh riwayat

Ketiganya adalah sifat **pembelian**, bukan sifat materialnya — satu material bisa dibeli
untuk beberapa kapal, dari beberapa supplier, di beberapa tahun. Sebelumnya penyaringan
dilakukan lewat `v_harga_terkini`, yaitu harga terakhir saja, sehingga material yang pernah
dibeli untuk kapal A tapi harga terakhirnya dari kapal B **hilang** saat difilter kapal A.

Masalahnya baru muncul setelah kapal kedua masuk: filter ANTAREJA menampilkan 18 material,
padahal sebenarnya 25. Angkanya salah tanpa memberi tanda apa pun.

Sekarang penyaringan melihat seluruh riwayat harga, dan baris harga yang **ditampilkan**
adalah yang terbaru di antara yang lolos filter — jadi memfilter ANTAREJA menampilkan harga
ANTAREJA (€417,83), bukan harga PUNTADEWA (€456,18) untuk barang yang sama. KPI "Total
Kapal" dan "Total Supplier" ikut dihitung dari seluruh riwayat.

Opsi filternya juga dibuat tidak pernah menyesatkan: sebuah nilai hanya jadi pilihan kalau
memilihnya benar-benar menghasilkan baris. Diverifikasi dengan menyapu 81 kombinasi filter
yang bisa dipilih pengguna — nol yang berujung hasil kosong.

## Perbaikan: median jasa menyebutkan kapal penyusunnya

Median per kategori per tahun tidak bisa ditindaklanjuti kalau tidak jelas kapal mana yang
menyusunnya: Rp 2.500.000 untuk "ADDITIONAL WORK 2026" ternyata berasal dari 54 baris tapi
hanya 2 kapal, sementara angka lain berasal dari 20 kapal. Keduanya terlihat sama meyakinkan.

Tabel angka sekarang memuat kolom kapal penyusun median (dengan penanda "1 kapal saja"),
rentang minimum–maksimum, dan tooltip grafiknya menyebutkan jumlah baris serta kapal.
Datanya diambil lewat `array_agg` atas grup yang sama dengan median — diverifikasi cocok
dengan query langsung ke DB, dan `n_kapal` sama dengan panjang daftar kapal di semua 91 baris.

## Fitur: pratinjau dampak paste

`POST /material/bulk/preview` menjalankan seluruh logika keputusan tanpa menulis apa pun,
lalu melaporkan per baris: material baru, titik harga baru (beserta harga lama dan persen
perubahannya), atau dilewati karena harganya sudah persis sama. Endpoint ini memakai fungsi
keputusan yang sama dengan jalur simpan, jadi hasilnya tidak bisa berbeda dari kenyataan.

Alasannya: kemampuan membedakan "material baru" dan "titik harga baru" sudah ada sejak
sebelumnya, tapi antarmuka tidak pernah mengatakannya. Orang yang teliti menyangka
aplikasinya akan bikin material kembar, lalu memilih memasukkan data manual satu per satu.
Itu kegagalan komunikasi, bukan kegagalan fungsi.

## Perubahan: part number jadi penentu identitas material

Part number (disimpan di `spesifikasi`) adalah identitas sebenarnya; nama cuma label yang
bisa ditulis berbeda oleh orang berbeda. Jadi kalau part number ada, itu yang menentukan —
"AIR FILTER ELEMENT" dan "Air Filter Elem." dengan part number sama adalah satu barang, dan
harga keduanya menempel di riwayat yang sama.

Part number **tidak** dijadikan wajib. Katalog ini akan memuat cat per liter, plat per
ukuran, dan konsumabel yang memang tidak punya nomor; kunci wajib akan memblokirnya. Kalau
part number tidak ada, identitas jatuh ke nama + satuan, dan pratinjau memberi tahu bahwa
identitasnya bertumpu pada penulisan nama.

Dijaga index `uq_sd_partno` (unik per jenis, hanya untuk baris yang punya spesifikasi).
Index ini dipasang di transaksi terpisah dan kegagalannya tidak menjatuhkan aplikasi —
aturan yang sama sudah berlaku di layer aplikasi, index cuma jaring pengaman di tingkat DB.

Pratinjau juga memperingatkan kalau part number cocok tapi namanya berbeda: material lama
yang dipakai dan nama di paste diabaikan. Itu biasanya benar, tapi bisa juga tanda part
number salah ketik, jadi harus kelihatan sebelum disimpan.

## Perbaikan: opsi filter kategori selaras dengan datanya

Daftar kategori di tab Analitik dibuat dari `DISTINCT` biasa, sementara datanya disaring
`HAVING COUNT(*) >= min_sampel`. Akibatnya 13 dari 77 opsi bisa dipilih tapi grafiknya kosong.
`kategori_options()` sekarang memakai saringan yang sama. Diverifikasi pada `min_sampel`
1/3/5/10: jumlah opsi selalu sama persis dengan jumlah kategori yang punya data
(77/64/58/46), tanpa opsi kosong dan tanpa kategori yang hilang dari daftar.
