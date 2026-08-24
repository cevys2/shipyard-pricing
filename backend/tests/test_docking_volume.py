"""Laporan docking: Qty ikut tersimpan, dan blok tanda tangan berhenti jadi baris harga.

Qty SUDAH dibaca `docking_parser` sejak awal -- dipakai membagi kolom Jumlah jadi harga
satuan, lalu dibuang. Jadi selama ini `tabel_katalog_harga` tidak pernah menyimpan
kuantitas dari jalur mana pun: `volume_satuan` isinya satuan saja ("Ls", "Hari", "Kali"),
bukan "269 m2" seperti yang sering diduga. Akibatnya "berapa nilai pekerjaan pengecatan
untuk kapal ini" tidak bisa dijawab, dan harga antar kapal tidak bisa dibandingkan dengan
adil -- Rp 200.000/m2 di kapal yang 269 m2 dan yang 230 m2 terlihat identik.

Berkas contoh dibangun di memori dengan tata kolom yang sama persis dengan dua berkas
docking asli di root repo: NO di kolom 0, URAIAN membentang 1-11, VOLUME (Qty, Sat) di
12-13, HARGA (Satuan, Jumlah) di 14-15, KETERANGAN di 17.
"""

import io

import pytest
from openpyxl import Workbook

from app.services.docking_parser import parse_docking_file

LEBAR = 18


def _baris(**sel) -> list:
    row = [None] * LEBAR
    for ci, v in sel.items():
        row[int(ci[1:])] = v
    return row


def _berkas(isi: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(_baris(c0="NAMA KAPAL", c2=":", c3="KMP. TES"))
    ws.append(_baris(c0="PEMILIK", c2=":", c3="PT. TES FERRY"))
    ws.append(_baris(c0="PERIODE DOCKING", c2=":", c3=2026))
    ws.append(_baris(c0="SCOPE OF WORK"))
    ws.append(_baris(c0="NO", c1="URAIAN", c12="VOLUME", c14="HARGA (Rp.)", c17="KETERANGAN"))
    ws.append(_baris(c12="Qty", c13="Sat", c14="Satuan ", c15="Jumlah"))
    ws.append(_baris(c0="I", c1="GENERAL SERVICES"))
    for row in isi:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _induk(isi):
    return parse_docking_file(_berkas(isi), "docking.xlsx")["induk"]


def _satu(isi):
    (item,) = _induk(isi)
    return item


# --- Qty jadi `volume` ------------------------------------------------------------------

def test_qty_dan_sat_keluar_sebagai_angka_dan_teks_terpisah():
    item = _satu([_baris(c0=1, c1="Aliran listrik dari darat", c12=18, c13="Hari", c14=1_000_000, c15=18_000_000)])

    assert item["volume"] == 18
    assert item["satuan"] == "Hari"
    assert item["harga"] == 1_000_000


def test_volume_satuan_lama_tidak_berubah_artinya():
    """Kolom lama tetap berisi satuannya saja -- baris lama dan baru harus tampil sama."""
    item = _satu([_baris(c0=1, c1="Aliran listrik", c12=18, c13="Hari", c14=1_000_000, c15=18_000_000)])

    assert item["volume_satuan"] == "Hari"


def test_volume_kali_harga_menghasilkan_kembali_kolom_jumlah():
    """Inilah gunanya menyimpan Qty: nilai barisnya bisa dihitung ulang, bukan ditebak.

    Diverifikasi juga di dua berkas docking asli di root repo: 414 baris punya Qty DAN
    kolom Jumlah, dan volume x harga = Jumlah di keempat-ratus-empat-belasnya.
    """
    item = _satu([_baris(c0=1, c1="Sewa genset", c12=25, c13="Hari", c14=500_000, c15=12_500_000)])

    assert item["volume"] * item["harga"] == 12_500_000


def test_harga_satuan_diturunkan_dari_jumlah_kalau_kolom_satuan_kosong():
    """Perilaku lama yang tidak boleh berubah -- Qty-nya memang sudah dipakai di sini."""
    item = _satu([_baris(c0=1, c1="Replating pelat", c12=4, c13="Unit", c15=20_000_000)])

    assert item["harga"] == 5_000_000
    assert item["volume"] == 4


def test_baris_tanpa_qty_volume_jadi_none_bukan_satu():
    """Menebak 1 akan mengarang angka. NULL mengatakan "tidak tahu" dengan jujur."""
    item = _satu([_baris(c0=1, c1="Pekerjaan lump sum", c15=3_000_000)])

    assert item["volume"] is None
    assert item["satuan"] is None
    assert item["volume_satuan"] == "-"
    assert item["harga"] == 3_000_000


def test_baris_berharga_satuan_tanpa_kolom_jumlah_tetap_terambil():
    """Baris "tarif" seperti Keel block: ada harga satuan, kolom Jumlah kosong.

    Baris ini nyata (ada di kedua berkas asli) dan memang TIDAK ikut TOTAL BIAYA di
    berkasnya. Jadi menjumlahkan volume x harga seluruh baris akan melebihi TOTAL BIAYA --
    di dua berkas asli selisihnya Rp 5,5 juta dan Rp 7,0 juta, sekitar 0,4%. Itu bukan
    baris yang jatuh, itu tarif bersyarat; karena itu jalur docking sengaja TIDAK diberi
    palang rekonsiliasi seperti jalur repair list.
    """
    item = _satu([_baris(c0=1, c1="a. Keel block", c12=1, c13="Unit", c14=750_000)])

    assert item["harga"] == 750_000
    assert item["volume"] == 1


@pytest.mark.parametrize("sat", ["Ls", "Kali", "Tangki", "m2"])
def test_bermacam_satuan_lewat_apa_adanya(sat):
    item = _satu([_baris(c0=1, c1="Pekerjaan", c12=2, c13=sat, c14=1_000)])

    assert item["satuan"] == sat


# --- blok tanda tangan ------------------------------------------------------------------

def test_baris_tanda_tangan_tidak_jadi_baris_harga():
    """46.197 itu NOMOR SERI tanggal Excel, bukan rupiah.

    Di baris "Diketahui dan Disetujui oleh :" ada sel tanggal di kolom harga satuan, dan
    xlrd mengembalikannya sebagai angka mentah. Tiap berkas docking menyumbang satu baris
    katalog palsu seharga 46.197 -- cukup masuk akal sebagai harga sehingga tidak pernah
    ada yang curiga. Terbukti ada di kedua berkas asli di root repo.
    """
    isi = [
        _baris(c0=1, c1="Pekerjaan sungguhan", c12=1, c13="Ls", c14=5_000_000, c15=5_000_000),
        _baris(c1="TOTAL BIAYA", c15=5_000_000),
        _baris(c1="Diketahui dan Disetujui oleh :", c12="Jakarta,", c14=46_197),
    ]

    item = _satu(isi)

    assert item["uraian"] == "Pekerjaan sungguhan"


@pytest.mark.parametrize(
    "label", ["Diketahui dan Disetujui oleh :", "Disetujui oleh", "Mengetahui", "Dibuat oleh :"]
)
def test_semua_label_blok_tanda_tangan_dilewati(label):
    isi = [
        _baris(c0=1, c1="Pekerjaan sungguhan", c12=1, c13="Ls", c14=5_000_000, c15=5_000_000),
        _baris(c1=label, c12="Jakarta,", c14=46_197),
    ]

    assert len(_induk(isi)) == 1, f"{label!r} masih terbaca sebagai baris harga"


def test_pekerjaan_yang_kebetulan_berawalan_mirip_tetap_terambil():
    """Palangnya tidak boleh terlalu rakus."""
    isi = [_baris(c0=1, c1="Dibuat baru pondasi electro motor ballast", c12=1, c13="Unit", c14=15_000_000)]

    assert len(_induk(isi)) == 1


# --- keterangan & addendum --------------------------------------------------------------

def test_keterangan_ikut_keluar_untuk_disimpan():
    item = _satu([_baris(c0=1, c1="Pekerjaan", c12=1, c13="Ls", c14=1_000, c17="material owner supply")])

    assert item["keterangan"] == "material owner supply"


def test_pemisahan_induk_addendum_tidak_ikut_berubah():
    """Aturan lama: keterangan mengandung "tambahan" -> Addendum. Jangan sampai rusak."""
    isi = [
        _baris(c0=1, c1="Kerja induk", c12=1, c13="Ls", c14=1_000_000, c15=1_000_000),
        _baris(c0=2, c1="Kerja ekstra", c12=2, c13="Ls", c14=500_000, c15=1_000_000, c17="pekerjaan tambahan"),
    ]

    hasil = parse_docking_file(_berkas(isi), "docking.xlsx")

    assert [i["uraian"] for i in hasil["induk"]] == ["Kerja induk"]
    assert [i["uraian"] for i in hasil["addendum"]] == ["Kerja ekstra"]
    assert hasil["addendum"][0]["volume"] == 2, "Qty harus ikut juga di jalur Addendum"


def test_kepala_berkas_tetap_terbaca():
    hasil = parse_docking_file(
        _berkas([_baris(c0=1, c1="Pekerjaan", c12=1, c13="Ls", c14=1_000)]), "docking.xlsx"
    )

    assert hasil["detected_nama_kapal"] == "KMP. TES"
    assert hasil["detected_nama_perusahaan"] == "PT. TES FERRY"
    assert hasil["detected_tahun"] == "2026"


# --- ujung ke ujung: pratinjau -> simpan -------------------------------------------------

def test_impor_docking_menyimpan_volume_satuan_dan_keterangan():
    """Angka yang sudah benar di parser harus benar-benar MENDARAT di database.

    Sebelum ini jalur docking mengirim empat kolom saja, jadi kolom `volume` tetap NULL
    walaupun parsernya sudah membaca Qty -- impor kelihatan sukses dan tidak ada yang
    memberi tahu bahwa kuantitasnya hilang lagi di langkah terakhir.
    """
    import time

    from fastapi.testclient import TestClient
    from jose import jwt
    from sqlalchemy import text

    from app.config import settings
    from app.database import engine
    from app.main import app

    token = jwt.encode(
        {"sub": "tes@contoh.com", "role": "admin", "exp": int(time.time()) + 600},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    isi = [
        _baris(c0=1, c1="Sewa genset", c12=25, c13="Hari", c14=500_000, c15=12_500_000, c17="BBM owner supply"),
        _baris(c0=2, c1="Kerja ekstra", c12=2, c13="Unit", c14=1_000_000, c15=2_000_000, c17="pekerjaan tambahan"),
    ]
    client = TestClient(app, raise_server_exceptions=False)
    auth = {"Authorization": f"Bearer {token}"}

    pratinjau = client.post(
        "/catalog/import/docking-preview",
        files={"file": ("docking.xlsx", _berkas(isi), "application/vnd.ms-excel")},
        headers=auth,
    ).json()

    def items(daftar):
        return [
            {
                "kategori_pekerjaan": it["kategori"] or "-",
                "uraian_pekerjaan": it["uraian"],
                "volume_satuan": it["satuan"] or "-",
                "harga_satuan": it["harga"],
                "volume": it["volume"],
                "satuan": it["satuan"],
                "keterangan": it["keterangan"],
            }
            for it in daftar
        ]

    resp = client.post(
        "/catalog/import/docking-commit",
        json={
            "nama_perusahaan": pratinjau["detected_nama_perusahaan"],
            "nama_kapal": pratinjau["detected_nama_kapal"],
            "tahun": pratinjau["detected_tahun"],
            "induk_items": items(pratinjau["induk"]),
            "addendum_items": items(pratinjau["addendum"]),
        },
        headers=auth,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["saved"] == 2

    with engine.connect() as c:
        baris = c.execute(
            text(
                "SELECT uraian_pekerjaan, volume, satuan, keterangan, tipe_perjanjian, "
                "coalesce(volume, 1) * harga_satuan AS nilai "
                "FROM tabel_katalog_harga ORDER BY id"
            )
        ).mappings().all()

    genset = next(b for b in baris if b["uraian_pekerjaan"] == "Sewa genset")
    assert float(genset["volume"]) == 25
    assert genset["satuan"] == "Hari"
    assert genset["keterangan"] == "BBM owner supply"
    assert float(genset["nilai"]) == 12_500_000, "nilai baris tidak bisa dihitung ulang dari yang tersimpan"

    ekstra = next(b for b in baris if b["uraian_pekerjaan"] == "Kerja ekstra")
    assert ekstra["tipe_perjanjian"] == "Addendum"
    assert float(ekstra["volume"]) == 2


# --- konteks baris induk (kedalaman dibaca dari kolom) -----------------------------------

def _pipa():
    """Potongan bagian pipa KMP. GILIMANUK 2026, bentuk kolomnya persis seperti aslinya.

    Tanda hubung menempati SEL TERSENDIRI di kolom 1 dan teksnya di kolom 2 -- begitulah
    berkas docking menandai kedalaman. Uraiannya sendiri tidak memuat tanda itu.
    """
    return [
        _baris(c0="IV", c1="PEKERJAAN PIPA DAN VALVE"),
        _baris(c0=1, c1="Pekerjaan Pipa (Galvanies sch 40 seamless)"),
        _baris(c1="Kamar mesin kanan"),
        _baris(c1="Pipa isap BBM"),
        _baris(c1="-", c2='Pipa Sch. 40 uk 1,5"', c12=1.4, c13="M", c14=750_000),
        _baris(c1="-", c2="Elbow", c12=2, c13="Pcs", c14=450_000),
        _baris(c1="Pipa outboard got"),
        _baris(c1="-", c2='Pipa Sch. 40 uk 2"', c12=1.6, c13="M", c14=1_000_000),
        _baris(c1="-", c2="Elbow", c12=3, c13="Pcs", c14=600_000),
    ]


def test_baris_anak_membawa_jalur_pipanya():
    """Dua baris "Elbow" berharga beda karena jalur pipanya beda. Itu data yang sah --
    yang selama ini hilang bukan harganya, melainkan alasan harganya berbeda."""
    elbow = [i for i in _induk(_pipa()) if i["uraian"] == "Elbow"]

    assert len(elbow) == 2
    assert elbow[0]["induk_uraian"].endswith("Pipa isap BBM")
    assert elbow[1]["induk_uraian"].endswith("Pipa outboard got")
    assert elbow[0]["harga"] == 450_000
    assert elbow[1]["harga"] == 600_000


def test_rantai_induk_menyertakan_semua_tingkat_di_atasnya():
    (pertama,) = [i for i in _induk(_pipa()) if i["uraian"] == "Elbow" and i["harga"] == 450_000]

    assert pertama["induk_uraian"] == (
        "Pekerjaan Pipa (Galvanies sch 40 seamless) › Pipa isap BBM"
    )
    assert pertama["kategori"] == "PEKERJAAN PIPA DAN VALVE"


def test_sel_tanda_hubung_tidak_ikut_ke_uraian():
    """Perilaku lama yang harus tetap: uraian tersimpan "Elbow", bukan "- Elbow"."""
    assert {i["uraian"] for i in _induk(_pipa())} == {
        'Pipa Sch. 40 uk 1,5"',
        "Elbow",
        'Pipa Sch. 40 uk 2"',
    }


def test_seksi_romawi_baru_mengosongkan_rantai_induk():
    """Konteks pipa tidak boleh bocor ke seksi berikutnya."""
    isi = _pipa() + [
        _baris(c0="V", c1="PERMESINAN"),
        _baris(c0=1, c1="Overhaul pompa", c12=1, c13="Unit", c14=5_000_000),
    ]

    (pompa,) = [i for i in _induk(isi) if i["uraian"] == "Overhaul pompa"]

    assert pompa["induk_uraian"] is None
    assert pompa["kategori"] == "PERMESINAN"


def test_baris_bernomor_lebih_dangkal_daripada_baris_tanpa_nomor():
    """Butir bernomor memulai blok baru, jadi dia tidak boleh jadi anak baris sebelumnya."""
    isi = [
        _baris(c0="IV", c1="PEKERJAAN PIPA DAN VALVE"),
        _baris(c0=1, c1="Blok pertama"),
        _baris(c1="-", c2="Anak blok pertama", c12=1, c13="Pcs", c14=100_000),
        _baris(c0=2, c1="Blok kedua", c12=1, c13="Ls", c14=200_000),
    ]

    (kedua,) = [i for i in _induk(isi) if i["uraian"] == "Blok kedua"]

    assert kedua["induk_uraian"] is None


def test_baris_tanpa_induk_tetap_none():
    """Berkas yang datar tidak boleh tiba-tiba punya rantai induk kosong berupa string."""
    (item,) = _induk([_baris(c0=1, c1="Sea trial", c12=1, c13="Ls", c14=1_000_000)])

    assert item["induk_uraian"] is None
