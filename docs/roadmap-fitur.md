# Roadmap Update Fitur — Katalog Material & AHSP
*(sumber: slide "Roadmap Update Fitur (Casual)", disetujui bos/klien)*

Pendekatan iteratif — jangan bikin sistem ribet kalau datanya belum siap/kepakai.

## Langkah 1 — Tab "Katalog Material" (QUICK WIN, kerjakan dulu)
Tab UI baru khusus nampilin list harga material dari supplier (Cat, Plat, dll).
Cuma naruh data mentah, simpel.

**Aman 100%**: `tabel_katalog_harga` (harga jasa lama) sama sekali TIDAK disentuh di fase ini.

Struktur data:
- `sumber_daya` — master nama barang & satuan (mis. Cat Epoxy, Kg)
- `sumber_daya_harga` — histori tiap update harga dari supplier A/B/C

Input awal: file Excel harga supplier (cat, plat, dll) dari klien untuk dimasukkan ke database.

## Langkah 2 — Tracking Tren Harga (kalau butuh, setelah Langkah 1 rutin dipakai)
Karena "nama barang" dan "histori harga" sudah dipisah di Langkah 1, tinggal bikin
time series chart. Syarat: harga material harus rajin di-update supaya grafik jalan.
Kegunaan: kelihatan kapan supplier naikin harga → bantu mutusin kapan harga jual disesuaikan.

## Langkah 3 — Justifikasi Harga / AHSP ("Final Boss")
Baru dikerjakan kalau bos/klien butuh breakdown "kenapa harga jasa ini segini" ke klien.
Sistem gabungin Katalog Material + koefisien lapangan (Kg cat per m², jam kerja tukang, dll)
untuk hitung harga modal otomatis.

**Kendala**: solo dev nggak tau angka koefisien teknis lapangan (berapa Kg cat / jam kerja
per 1 m² lambung kapal) — itu harus dari bos/tim lapangan. Tes dulu ke 5-10 pekerjaan
prioritas, jangan langsung semua katalog.

---
**Status saat ini: fokus Langkah 1 saja.**
