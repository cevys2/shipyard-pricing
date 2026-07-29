# Catatan: apa yang dilakukan branch `feat/analitik-tren-harga` ke `tabel_katalog_harga`

**Ringkasnya: dibaca, tidak diubah sama sekali.**

Dokumen ini sengaja dibuat supaya klaim di atas bisa diverifikasi, bukan cuma dipercaya.

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

## 4. Cara memverifikasi sendiri

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
