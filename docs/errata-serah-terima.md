# Errata — Dokumen Serah Terima

Dokumen Serah Terima (PDF, di luar repo) disusun **10 Agustus 2026 pada commit `9513753`**.
Repo sudah bergerak sejak itu. Berkas ini mencatat apa yang berubah, supaya PDF-nya tetap
bisa dipakai tanpa harus ditulis ulang.

Ditaruh di dalam repo dengan sengaja: PDF-nya hidup di luar, jadi tidak ada yang memaksanya
ikut mutakhir waktu kodenya berubah. Berkas ini ikut.

**Kalau errata dan PDF bertentangan, errata yang benar** — sampai PDF-nya diperbarui, lalu
berkas ini dikosongkan.

Terakhir diperiksa: 10 Agustus 2026, commit `64dd17b`.

---

## A. Sudah tidak berlaku — koreksi wajib

### A1. §7.C — "Tab AHSP tidak bisa membuat material baru dari sana"

**Salah sejak Sesi 3.2.** Tab Struktur Biaya bisa membuat material baru langsung dari layar
AHSP: ketik nama yang belum ada, muncul pilihan "buat baru" (nama, satuan, harga awal), dan
materialnya langsung terpakai sebagai komponen. Lihat `AhspPanel.tsx`, pemanggilan
`api.materialBulkCreate`.

Saran ditampilkan **di atas** pilihan "buat baru", memakai dua kata pertama yang diketik —
karena `uq_sd_identitas` cuma menolak nama yang persis sama, jadi penjaga di layar harus
lebih longgar daripada index-nya.

Kenapa ini penting diperbaiki: orang yang percaya batas ini akan merancang jalan memutar
untuk sesuatu yang sudah tidak ada.

### A2. §9 risiko #2, §7.A jalur A3, §12 poin 3 — tempel harga salah baca ribuan

**Sudah diperbaiki.** `EditableCatalogTable.tsx` sekarang memakai `bacaAngkaUang()` dari
`frontend/src/lib/tsv.ts`. `150.000` tersimpan 150.000, `Rp 150.000` juga, dan sel yang
ditafsirkan begitu dilaporkan balik ke pengguna alih-alih diubah diam-diam.

Anjuran di PDF untuk memakai `angkaTempel()` **tidak bisa diikuti** — fungsi itu sudah
dihapus (commit `14bc54b`) dan dilebur jadi satu pembaca angka bersama. Dulu ada tiga
pembaca angka yang berbeda perilaku untuk masukan yang sama; sekarang satu.

Anjuran "ubah dulu kolom Harga jadi angka polos sebelum menempel" juga sudah tidak perlu.

### A3. §5 — daftar dan urutan `ensure_*()`

Sekarang **enam**, bukan lima, dan `ensure_kategori_table()` menyisip di tengah:

1. `ensure_material_tables()`
2. `ensure_partno_unique()`
3. `ensure_kategori_table()` — **baru**
4. `ensure_ahsp_tables()`
5. `ensure_audit_table()`
6. `ensure_pencarian_index()`

Urutannya tetap tidak boleh diacak, dan sekarang ada satu ikatan tambahan:
`ahsp.kategori_id` menunjuk ke `kategori(id)`, jadi nomor 4 wajib sesudah nomor 3. Sengaja
tidak dibungkus penjaga "kalau tabelnya belum ada, lewati" — penjaga begitu cuma menunda
kegagalannya sampai baris AHSP pertama disimpan, dengan pesan yang jauh lebih sulit dibaca.

### A4. §7.B — penyaring duplikat titik harga

PDF menyebut sidik jarinya memuat **tanggal berlaku**. Sudah tidak.

`berlaku_dari` boleh dikosongkan dan kalau kosong jatuh ke hari ini, jadi memasukkannya
membuat penangkal duplikat hanya bekerja dalam satu hari — faktur yang sama ditempel
besoknya lolos sebagai "harga baru". Sidik jarinya sekarang: material, harga, mata uang,
supplier, tahun pembelian, kapal.

Sekaligus: **urutan "harga mana yang terkini" sekarang `tahun_pembelian`, bukan
`berlaku_dari`.** Sebelumnya pembelian lama yang baru diinput bisa mengalahkan pembelian
yang lebih baru, lalu ikut ke harga komponen AHSP. Satu definisi di
`database.urutan_harga_sql()`, dipakai enam tempat.

### A5. §7.A — "tabelnya datar, 9 kolom"

`tabel_katalog_harga` sekarang punya dua kolom tambahan: `kategori_id` (kategori kanonik,
boleh ditimpa manusia) dan `kategori_sumber` (`alias` atau `manual`). Isi
`kategori_pekerjaan` tetap tidak pernah ditulis ulang — aturan itu masih berlaku penuh.

### A6. §10 — "menunggu keputusan klien"

Dua-duanya sudah dijawab:

- **Sebutan resmi pekerjaan** — diputus VP Marketing: 11 kategori kanonik (10 jenis
  pekerjaan + `LAIN-LAIN`), 83 alias. Sudah jalan di produksi.
- **Keputusan A9** — diputus "jumlahkan jujur". Tidak ada kolom harga yang ditetapkan
  manual. Akibatnya di ±37% kelompok biaya angka aplikasi **lebih tinggi** daripada Excel
  lama. Disengaja. Kalau ada yang melapor "aplikasinya salah hitung", ini sebabnya.

**Sesi 3.2 sudah dikerjakan dan jalan di produksi**, bukan "sudah direncanakan, belum
dikerjakan".

### A7. §10 — dokumen pendamping

Bertambah: `docs/bundel-kategori-claude-code.md` (keputusan kategori + rencana empat sesi),
`docs/final_peta.json` (peta 83 alias), `docs/seed_kategori.sql` (arsip; yang benar-benar
dijalankan adalah `backend/app/seed_kategori.py`), dan berkas ini.

Risiko #6 ("CLAUDE.md sudah tidak sesuai kenyataan") sudah ditutup.

---

## B. Masih berlaku — jangan dianggap beres

Dari 12 risiko di §9, **sembilan masih terbuka**. Yang nomor 1 tetap yang paling penting dan
tetap bukan masalah teknis: akses produksi masih di satu orang, dan tidak ada perbaikan
teknis untuk itu.

Yang angkanya berubah, sisa risiko #12 — data lama `tabel_katalog_harga`:

| Temuan | Di PDF | Sekarang |
|---|---|---|
| Nilai kategori berbeda | 77–78 | **0 masalah** — 78 sebutan terpetakan ke 11 kategori, nol sisa |
| Baris tanpa klasifikasi terpakai | ~13% | **0%** |
| Nilai `Nopember` di kolom `tahun` | ada | **masih ada, 36 baris** |
| Grup baris identik | 212 grup / 302 berlebih | **261 grup / 362 berlebih** |

Bagian kategori selesai. Dua sisanya tidak, dan yang duplikat justru bertambah seiring impor
baru. Keduanya tetap sengaja tidak didedup — tabelnya tidak punya kolom kuantitas, jadi
tidak ada cara memastikan dua baris identik itu salah input atau memang dua pekerjaan.

---

## C. Sudah diketahui, belum dikerjakan

- Resolver kategori dipanggil saat aplikasi start, **belum di jalur impor Excel**. Baris
  hasil impor berikutnya `kategori_id`-nya kosong sampai deploy berikutnya. Angkanya
  ditampilkan di tab Analitik (`cakupan.tanpa_kategori`) supaya penyusutannya kelihatan.
- Tren material: `dari`/`sampai` dan sumbu-X grafiknya masih memakai `berlaku_dari`, jadi
  rentangnya menampilkan hari input, bukan rentang pembelian.
- Tab Struktur Biaya baru berisi satu analisa (13 komponen). `shift` dan `jml_hari` isinya
  1 di seluruh barisnya — hanya `qty` yang dipakai.
