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

---

## Ditunda dengan sengaja (22 September 2026)

### Radix primitives — disetujui arahnya, belum dikerjakan
Dropdown, dialog, tooltip, dan tab di app ini dibuat tangan. Yang hilang bukan tampilannya,
melainkan perilaku keyboard: fokus yang terperangkap di dialog, Esc yang menutup, panah yang
berpindah antar opsi. Ini aplikasi entri data yang dipakai lewat keyboard, jadi itu bukan
kosmetik.

Biayanya nyata: tiap komponen yang memakainya harus ditulis ulang, dan repo ini dirawat satu
orang. Karena itu font dan polish dikerjakan lebih dulu (nol dependensi, satu berkas), dan
Radix menunggu giliran sendiri.

Satu langkah kecil sudah diambil di arah itu: `index.css` sekarang punya **satu** aturan
`:focus-visible` untuk semua yang bisa di-Tab, menggantikan keadaan lama di mana tiap
komponen memutuskan sendiri dan sebagian tidak memutuskan apa pun.

**Diperiksa ulang 23 September 2026 — Radix tidak dipasang.** Kodenya ternyata tidak
seperti yang diduga paragraf di atas: ke-17 dropdown adalah `<select>` bawaan, navigasi tab
berupa tombol biasa, konfirmasi hapus memakai `confirm()` bawaan. Satu-satunya overlay buatan
tangan adalah drawer Riwayat Harga, dan itu dipindah ke `<dialog>` + `showModal()` bawaan:
Tab terkurung di drawer, Esc dan klik latar menutup, fokus kembali ke tombol "Riwayat" asalnya.
Radix baru layak dipertimbangkan kalau muncul widget yang tidak punya padanan bawaan —
combobox dengan pencarian, menu konteks, tooltip.

### Normalisasi satuan — prasyarat, bukan fitur
`satuan` punya 37 ejaan untuk ~20 satuan nyata (`m²`/`m2`/`m'`, `mtr`/`m`/`mter`,
`pcs`/`pc`/`buah`/`bh`, `tangki`/`tanki`, `liter`/`ltr`, `segel`/`shackle`). Belum
dikerjakan karena analitik yang ada tidak mengelompokkan per satuan.

Begitu ada layar yang menjawab **"harga sandblasting per m² wajarnya berapa"** — dan itu
layar yang langsung kepakai waktu menyusun penawaran — pemetaan satuan kanonik jadi
prasyarat mutlak. Polanya sudah ada dan terbukti: `kategori` + `kategori_alias`.

### Keluaran penawaran — jurang terbesar yang tersisa
Belum disentuh. Aplikasi masih belum menghasilkan dokumen apa pun; penawaran tetap disusun
manual di Excel. Analitik "Ke Mana Uangnya Pergi" mempersempit jaraknya sedikit (sekarang
nilai pekerjaan bisa dibaca dari aplikasi), tapi tidak menutupnya.
