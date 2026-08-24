"""Master kategori pekerjaan kanonik + pemetaan sebutan lama.

11 kategori (10 jenis pekerjaan + LAIN-LAIN) dan 100 alias. Yang 83 pertama disepakati VP
marketing 2026; 7 berikutnya ditambahkan 18 Agustus 2026 setelah menghitung cadangan
produksi 17 Agustus menemukan 549 baris berteks kategori yang belum punya alias sama
sekali; 7 terakhir ditambahkan 24 Agustus 2026 untuk sebutan seksi di berkas REPAIR LIST,
yang bentuknya memang beda dari laporan realisasi docking (tanpa alias itu, 374 dari 385
baris tiga repair list Basarnas masuk tanpa kategori sama sekali); 3 terakhir muncul waktu
seluruh arsip 20 berkas dibaca sekaligus, 24 Agustus 2026.
Catatan lengkap keputusannya ada di `docs/bundel-kategori-claude-code.md`; peta yang sama
tersimpan sebagai data mentah di `docs/final_peta.json`, dan `tests/test_kategori.py`
menjaga keduanya tidak berpisah diam-diam.

Kenapa data ini jadi modul Python, bukan `docs/seed_kategori.sql` yang dibaca saat start:
root service backend di Railway adalah `/backend`, jadi `docs/` TIDAK ikut ke dalam
container. Berkas .sql di sana akan ketemu waktu dites lokal lalu hilang di produksi --
gagal cuma di tempat yang tidak kelihatan. Selain itu pg8000 memakai extended query
protocol yang tidak menerima banyak statement sekaligus, jadi berkas .sql tetap harus
dipecah sendiri. Disimpan sebagai data Python, seedingnya bisa parameterized penuh sesuai
aturan repo ini.

Urutan tampil diturunkan dari urutan kunci di `PETA` (10, 20, 30, ...), bukan ditulis
terpisah -- dua daftar yang harus sejalan cepat atau lambat akan berpisah.
"""

# Urutan kunci di sini menentukan urutan tampil di dropdown. LAIN-LAIN sengaja terakhir.
PETA: dict[str, tuple[str, ...]] = {
    "PIPA - PIPA": (
        "PEKERJAAN PIPA",
        "PEKERJAAN PIPA DAN VALVE",
        "PEKERJAAN PIPA-PIPA",
        "PEKERJAAN TAMBAHAN PIPA- PIPA",
        "PERPIPAAN",
        "PIPA",
        "PIPA - PIPA",
        "PIPA - PIPA (PIPA YARD SUPPLY)",
        "PIPA- PIPA",
        "PIPA-PIPA",
        "PIPA-PIPA DIKAMAR MESIN DAN DECK (BERDASARKAN RL YANG DIKIRIM)",
        "PIPING",
        # Seksi VI di ketiga repair list Basarnas. Pompanya ikut ke sini bersama
        # perpipaannya karena begitulah dokumennya menyatukan mereka; memecahnya butuh
        # kategori "POMPA" tersendiri, dan itu keputusan yang lebih besar dari ini.
        "POMPA DAN PERPIPAAN",
    ),
    "REPLATING": (
        "PEKERJAAN REPLATING",
        "PEKERJAAN REPLATING PLAT",
        "REPLATING",
    ),
    "PELAYANAN UMUM": (
        # Seksi I repair list: satu baris lump sum Rp 100 juta. Sebutannya menggabung dua
        # kategori yang di repo ini terpisah, jadi ini memang pilihan, bukan kepastian --
        # dan yang lebih dekat adalah PELAYANAN UMUM, sejalan dengan alias
        # "PELAYANAN UMUM/GENERAL SERVICES" yang bentuknya sama persis. Kalau ternyata
        # yang dimaksud biaya naik-turun dok, pindahkan satu baris ini ke
        # "DOCKING & UNDOCKING".
        "DOCKING/ GENERAL SERVICE",
        "GENERAL SERVICE",
        "GENERAL SERVICES",
        "PELAYANAN UMUM",
        "PELAYANAN UMUM ( GENERAL SERVICES )",
        "PELAYANAN UMUM (GENERAL SERVICES)",
        "PELAYANAN UMUM KAPAL ( GENERAL SERVICES )",
        "PELAYANAN UMUM/GENERAL SERVICES",
        "UMUM",
    ),
    "PERAWATAN LAMBUNG": (
        "ATAS GARIS AIR",
        "BAGIAN LAMBUNG",
        "HULL CLEANING & PAINTING",
        "HULL MAINTENANCE",
        "PERAWATAN LAMBUNG KAPAL (BGA) & (AGA)",
        # Seksi II repair list. Sub-seksinya (di bawah/di atas garis air, main deck, top
        # deck) tidak jadi kategori -- mereka mendarat di `induk_uraian`.
        "LAMBUNG KAPAL",
        "PERAWATAN LAMBUNG",
        "PERAWATAN LAMBUNG ( BGA )",
        "PERAWATAN LAMBUNG ( BGA ) DAN SUPERSTRUKTUR",
        "PERAWATAN LAMBUNG (BGA)",
        "PERAWATAN LAMBUNG (HULL)",
        "PERAWATAN LAMBUNG KAPAL",
    ),
    "KEMUDI, PROPELLER & POROS": (
        "KEMUDI, PROPELLER & POROS",
        "KEMUDI, PROPELLER, TAIL SHAFT",
        "KEMUDI, PROPELLER, TAIL SHAFT DAN STERN TUBE",
        "KEMUDI, PROPELLER, TAIL SHAFT, STERN TUBE",
        "PEKERJAAN PROPULSI",
        "PROPELLER & SHAFTING",
        "PROPELLER SHAFTING, RUDDER & RAMPDOOR",
        "PROPULSION SYSTEM",
        "RUDDER & RUDDER STOCK",
        "SISTEM PROPULSI",
        "TAIL SAHFT, PROPELLER, RUDDER DAN STERN BUSH",
        "TAIL SHAFT, PROPELLER, RUDDER & STERN BUSH",
        "VOID KEMUDI",
    ),
    "SEA CHEST & VALVE": (
        "KRAN-KRAN",
        "SEA CHEST",
        "SEA CHEST & SEA VALVE",
        "SEA CHEST & SEA VALVES",
        "SEA CHEST & VALVE",
        "SEA CHEST DAN SEA VALVE",
        "SEA CHEST, SEA VALVE & OVER BOARD",
        "VALVE-VALVE",
    ),
    "DOCKING & UNDOCKING": (
        "DOCKING & UNDOCKING",
        "DOCKING AND UNDOCKING",
        "DOCKING DAN UNDOCKING",
    ),
    "KONSTRUKSI": (
        "KONSTRUKSI",
        "PEKERJAAN KONSTRUKSI",
        # Salah ketik di laporan asli. Justru ini gunanya tabel alias:
        # teks aslinya tidak disentuh, koreksinya di kategori_id.
        "PEKERJAAN KONTRUKSI",
    ),
    "JANGKAR & RANTAI JANGKAR": (
        "JANGKAR & RANTAI JANGKAR",
        "JANGKAR, RANTAI JANGKAR & CERUK JANGKAR",
        "PEKERJAAN JANGKAR, RANTAI JANGKAR DAN WIRE",
        "JANGKAR, RANTAI JANGKAR DAN CERUK JANGKAR",
        "JANGKAR, RANTAI JANGKAR DAN CERUK JANGKAR "
        "( RANTAI = 40 MM , KANAN = 8 SEGEL, KIRI = 7 SEGEL )",
        "RANTAI JANGKAR DAN CERUK",
    ),
    "TANGKI": (
        # CLEANING (5 baris) masuk sini, bukan PERAWATAN LAMBUNG -- asumsi K-A1.
        "CLEANING",
        "PERAWATAN TANGKI-TANGKI",
        "TANGKI",
        "TANGKI - TANGKI",
        "TANGKI-TANGKI",
        "TANK CLEANING",
    ),
    "LAIN-LAIN": (
        # 442 baris PEKERJAAN TAMBAHAN / ADDITIONAL WORK jatuh ke sini (keputusan K-5),
        # yang bikin LAIN-LAIN lahir di 13,8%. Disengaja, bukan bug: untuk baris-baris itu
        # jenis pekerjaannya memang tidak tercatat di kolom kategori.
        "ADDITIONAL WORK",
        # Sebutan seksi mesin di laporan realisasi; sejalan dengan MEKANIK/PERMESINAN.
        "ENGINE (SESUAI RL YANG DIKIRIM)",
        "KAMAR MESIN",
        "LAIN - LAIN",
        "LAIN LAIN",
        "LAIN- LAIN",
        "LAIN-LAIN",
        "MEKANIK",
        "MEKANIKAL",
        "NAVIGASI DAN KOMUNIKASI",
        "OTHERS",
        "PEKERJAAN ACCOMODATION PASSANGER DECK (NON REPLATING)",
        "PEKERJAAN BENGKEL",
        "PEKERJAAN DI CARDECK DAN WINCH DECK (NON REPLATING)",
        "PEKERJAAN DI KAMAR MESIN (NON REPLATING)",
        "PEKERJAAN DI RAMPDOOR",
        "PEKERJAAN LISTRIK",
        "PEKERJAAN MEKANIK",
        "PEKERJAAN NAVIGATION DECK (NON REPLATING)",
        "PEKERJAAN TAMBAHAN",
        "PEKERJAAN TOP DECK (NON REPLATING)",
        # Dua seksi repair list yang tidak punya padanan di 11 kategori kanonik.
        # PERMESINAN yang paling terasa: 160 dari 385 baris ada di sana. Ikut jejak
        # "MEKANIK"/"MEKANIKAL"/"KAMAR MESIN" yang sudah lebih dulu di LAIN-LAIN --
        # bukan karena itu memuaskan, tapi karena kategori "PERMESINAN" tersendiri adalah
        # keputusan master data, bukan keputusan impor.
        "PERLENGKAPAN LAMBUNG, PEMADAM,INTERIOR DAN KELISTRIKAN KAPAL",
        "PERMESINAN",
        "ULTRASONIC TEST DAN NDT",
    ),
}


def baris_kategori() -> list[dict[str, object]]:
    """Kategori beserta urutan tampilnya, siap dipakai executemany."""
    return [{"nama": nama, "urutan": (i + 1) * 10} for i, nama in enumerate(PETA)]


def baris_alias() -> list[dict[str, str]]:
    """Pasangan (alias, nama kategori), siap dipakai executemany."""
    return [{"alias": alias, "nama": nama} for nama, daftar in PETA.items() for alias in daftar]
