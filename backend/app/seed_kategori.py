"""Master kategori pekerjaan kanonik + pemetaan sebutan lama.

11 kategori (10 jenis pekerjaan + LAIN-LAIN) dan 83 alias, disepakati VP marketing 2026.
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
        "PEKERJAAN PIPA-PIPA",
        "PEKERJAAN TAMBAHAN PIPA- PIPA",
        "PIPA",
        "PIPA - PIPA",
        "PIPA - PIPA (PIPA YARD SUPPLY)",
        "PIPA- PIPA",
        "PIPA-PIPA",
        "PIPA-PIPA DIKAMAR MESIN DAN DECK (BERDASARKAN RL YANG DIKIRIM)",
        "PIPING",
    ),
    "REPLATING": (
        "PEKERJAAN REPLATING",
        "PEKERJAAN REPLATING PLAT",
        "REPLATING",
    ),
    "PELAYANAN UMUM": (
        "GENERAL SERVICE",
        "GENERAL SERVICES",
        "PELAYANAN UMUM",
        "PELAYANAN UMUM ( GENERAL SERVICES )",
        "PELAYANAN UMUM (GENERAL SERVICES)",
        "PELAYANAN UMUM KAPAL ( GENERAL SERVICES )",
        "UMUM",
    ),
    "PERAWATAN LAMBUNG": (
        "ATAS GARIS AIR",
        "BAGIAN LAMBUNG",
        "HULL CLEANING & PAINTING",
        "HULL MAINTENANCE",
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
    ),
    "JANGKAR & RANTAI JANGKAR": (
        "JANGKAR & RANTAI JANGKAR",
        "JANGKAR, RANTAI JANGKAR & CERUK JANGKAR",
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
        "KAMAR MESIN",
        "LAIN - LAIN",
        "LAIN- LAIN",
        "LAIN-LAIN",
        "MEKANIK",
        "MEKANIKAL",
        "OTHERS",
        "PEKERJAAN ACCOMODATION PASSANGER DECK (NON REPLATING)",
        "PEKERJAAN BENGKEL",
        "PEKERJAAN DI CARDECK DAN WINCH DECK (NON REPLATING)",
        "PEKERJAAN DI KAMAR MESIN (NON REPLATING)",
        "PEKERJAAN DI RAMPDOOR",
        "PEKERJAAN LISTRIK",
        "PEKERJAAN NAVIGATION DECK (NON REPLATING)",
        "PEKERJAAN TAMBAHAN",
        "PEKERJAAN TOP DECK (NON REPLATING)",
        "ULTRASONIC TEST DAN NDT",
    ),
}


def baris_kategori() -> list[dict[str, object]]:
    """Kategori beserta urutan tampilnya, siap dipakai executemany."""
    return [{"nama": nama, "urutan": (i + 1) * 10} for i, nama in enumerate(PETA)]


def baris_alias() -> list[dict[str, str]]:
    """Pasangan (alias, nama kategori), siap dipakai executemany."""
    return [{"alias": alias, "nama": nama} for nama, daftar in PETA.items() for alias in daftar]
