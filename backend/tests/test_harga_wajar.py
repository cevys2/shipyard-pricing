"""Harga Wajar: kapan angka ringkas boleh tampil, dan apa yang ikut terhitung.

Semua kegagalan yang dijaga di sini membuat layar tetap terlihat meyakinkan sambil
menyesatkan orang yang sedang menyusun penawaran:

1. Satu berkas dengan banyak baris menentukan median sendirian.
2. Satu kapal yang docking tiap tahun terhitung sebagai beberapa pembanding.
3. Pekerjaan yang harganya menyebar (hasil nego) tetap diberi satu "harga wajar".
4. Sandblasting dan sweepblasting tercampur karena pencarian memaafkan salah ketik.
5. m2 dan m² jadi dua kelompok yang masing-masing separuh.
"""

import time

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import text

from app.config import settings
from app.database import engine, ensure_klien_induk, ensure_pencarian_index, ensure_satuan_table
from app.main import app
from app.services import harga_wajar as svc
from app.services import pencarian


@pytest.fixture(scope="module", autouse=True)
def tabel_siap():
    ensure_satuan_table()
    ensure_klien_induk()
    # Menyalakan pg_trgm supaya tes pencarian ketat benar-benar membuktikan sesuatu: kalau
    # trigram mati, "tidak tercampur" lulus dengan sendirinya.
    ensure_pencarian_index()


_N = iter(range(1, 10_000))


def _baris(
    kapal: str,
    uraian: str,
    harga: float,
    *,
    satuan: str | None = "m2",
    sat_baru: str | None = None,
    tahun: str = "2026",
    pt: str = "PT. TES",
    tipe: str = "Induk",
) -> None:
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO tabel_katalog_harga "
                "(id, nama_perusahaan, nama_kapal, tipe_perjanjian, tahun, kategori_pekerjaan, "
                " uraian_pekerjaan, volume_satuan, satuan, harga_satuan) "
                "VALUES (:id, :pt, :kapal, :tipe, :tahun, 'PENGECATAN', :uraian, :sat, :satn, "
                " :harga)"
            ),
            {
                "id": f"HW-{next(_N)}",
                "pt": pt,
                "kapal": kapal,
                "tipe": tipe,
                "tahun": tahun,
                "uraian": uraian,
                "sat": satuan if satuan is not None else "-",
                "satn": sat_baru,
                "harga": harga,
            },
        )


def _satu(q: str) -> dict:
    """Kelompok satu-satunya dari hasil pencarian -- gagal kalau jumlahnya bukan satu."""
    (k,) = svc.harga_wajar(q)["kelompok"]
    return k


def test_m2_dan_m_kuadrat_satu_kelompok():
    _baris("KMP. A", "Pengecatan lambung", 60_000, satuan="m2")
    _baris("KMP. B", "Pengecatan lambung", 65_000, satuan="m²")
    _baris("KMP. C", "Pengecatan lambung", 70_000, satuan="M2")

    k = _satu("pengecatan")
    assert k["satuan"] == "m²"
    assert k["n_kapal"] == 3
    assert sorted(k["ejaan"]) == ["M2", "m2", "m²"]
    assert k["borongan"] is False


def test_satu_docking_satu_suara():
    """Lima baris dari satu berkas tidak boleh mengalahkan dua kapal lain."""
    for _ in range(5):
        _baris("KMP. A", "Sandblasting lambung", 100_000)
    _baris("KMP. B", "Sandblasting lambung", 60_000)
    _baris("KMP. C", "Sandblasting lambung", 70_000)

    k = _satu("sandblasting")
    # Per baris mediannya 100.000 (5 dari 7 baris). Per docking: [100, 60, 70] -> 70.
    assert k["ringkas"]["median"] == 70_000
    assert k["n_baris"] == 7
    assert k["n_docking"] == 3
    (a,) = [d for d in k["docking"] if d["nama_kapal"] == "KMP. A"]
    assert a["n_baris"] == 5 and a["harga"] == 100_000


def test_jendela_marine_grade_dua_kapal_tanpa_median():
    """Contoh dari lapangan: pekerjaan yang jarang, harganya hasil nego, pembandingnya sedikit."""
    _baris("KMP. A", "Bongkar pasang jendela marine grade", 4_500_000, satuan="unit")
    _baris("KMP. B", "Bongkar pasang jendela marine grade", 7_000_000, satuan="unit")

    k = _satu("jendela marine")
    assert k["alasan"] == "kapal_kurang"
    assert k["ringkas"] is None
    assert k["tampilkan_ringkas"] is False
    # Daftar per docking tetap lengkap -- itu yang berguna untuk pekerjaan yang dinego.
    assert {d["nama_kapal"] for d in k["docking"]} == {"KMP. A", "KMP. B"}


def test_harga_terakhir_jadi_patokan_saat_median_disembunyikan():
    """Bos suka ada angka patokan -- tapi asalnya harus ikut, bukan angka tanpa nama."""
    _baris("KMP. A", "Bongkar pasang jendela marine grade", 4_500_000, satuan="unit", tahun="2025")
    _baris("KMP. B", "Bongkar pasang jendela marine grade", 7_000_000, satuan="unit", tahun="2026")

    k = _satu("jendela marine")
    assert k["tampilkan_ringkas"] is False
    assert k["terakhir"] == {
        "tahun": "2026",
        "docking": [
            {"nama_kapal": "KMP. B", "klien": ["PT. TES"], "harga": 7_000_000, "n_baris": 1}
        ],
    }


def test_harga_terakhir_tidak_memilih_satu_kapal_kalau_tahunnya_sama():
    """Memilih salah satu menurut abjad nama kapal = mengarang patokan."""
    _baris("KMP. B", "Bongkar pasang jendela marine grade", 7_000_000, satuan="unit")
    _baris("KMP. A", "Bongkar pasang jendela marine grade", 4_500_000, satuan="unit")

    terakhir = _satu("jendela marine")["terakhir"]
    assert [(d["nama_kapal"], d["harga"]) for d in terakhir["docking"]] == [
        ("KMP. A", 4_500_000),
        ("KMP. B", 7_000_000),
    ]


def test_satu_kapal_tiga_tahun_tetap_satu_kapal():
    """Tiga kesepakatan dengan klien yang sama bukan tiga pembanding."""
    for tahun in ("2024", "2025", "2026"):
        _baris("KMP. A", "Replating", 30_000, satuan="kg", tahun=tahun)
    _baris("KMP. B", "Replating", 32_000, satuan="kg")

    k = _satu("replating")
    assert k["n_docking"] == 4
    assert k["n_kapal"] == 2
    assert k["alasan"] == "kapal_kurang"


def test_nama_kapal_berspasi_ganda_dihitung_satu_kapal():
    _baris("KMP. PRIMA  NUSANTARA", "Replating", 30_000, satuan="kg", tahun="2025")
    _baris("KMP. PRIMA NUSANTARA", "Replating", 31_000, satuan="kg", tahun="2026")
    _baris("KMP. B", "Replating", 32_000, satuan="kg")

    k = _satu("replating")
    assert k["n_kapal"] == 2


def test_harga_menyebar_tidak_dijadikan_jawaban():
    _baris("KMP. A", "Perbaikan propeller", 100_000, satuan="unit")
    _baris("KMP. B", "Perbaikan propeller", 150_000, satuan="unit")
    _baris("KMP. C", "Perbaikan propeller", 400_000, satuan="unit")

    k = _satu("propeller")
    # Kuartil inklusif [100, 150, 400]: bawah 125.000, atas 275.000 -> 2,2x.
    assert k["ringkas"] == {"median": 150_000, "bawah": 125_000, "atas": 275_000}
    assert k["alasan"] == "menyebar"
    assert k["tampilkan_ringkas"] is False


def test_harga_rapat_ditampilkan():
    _baris("KMP. A", "Pengecatan lambung", 60_000)
    _baris("KMP. B", "Pengecatan lambung", 65_000)
    _baris("KMP. C", "Pengecatan lambung", 70_000)

    k = _satu("pengecatan")
    assert k["ringkas"] == {"median": 65_000, "bawah": 62_500, "atas": 67_500}
    assert k["alasan"] is None
    assert k["tampilkan_ringkas"] is True


def test_pencarian_ketat_tidak_mencampur_sweepblasting():
    if not pencarian.trgm_siap():
        pytest.skip("pg_trgm tidak terpasang -- tes ini tidak membuktikan apa pun tanpanya")
    _baris("KMP. A", "Sandblasting lambung", 120_000)
    _baris("KMP. B", "Sweepblasting lambung", 45_000)

    k = _satu("sandblasting")
    assert [d["nama_kapal"] for d in k["docking"]] == ["KMP. A"]

    # Pembanding: pencarian yang toleran memang mencampurnya. Kalau suatu saat tidak lagi,
    # tes di atas berhenti membuktikan apa pun dan perlu contoh lain.
    toleran = pencarian.bangun("sandblasting", svc.KOLOM_CARI)
    with engine.connect() as c:
        n = c.execute(
            text(f"SELECT COUNT(*) FROM tabel_katalog_harga t WHERE {toleran.kondisi}"),
            toleran.params,
        ).scalar()
    assert n == 2


def test_salah_ketik_tidak_ketemu():
    """Harga dari pencarian ketat: salah ketik = nol hasil. Itu harganya, dan disengaja."""
    _baris("KMP. A", "Sandblasting lambung", 120_000)
    assert svc.harga_wajar("sandblastng")["kelompok"] == []


_ELBOW = (
    'Elbow 2"',
    "Elbow 2 inch",
    "Elbow 12 inch",
    "Elbow 20 inch",
    "Elbow 2,5 inch",
    'Elbow 1/2"',
    'Elbow 3/4"',
    'Elbow 1/4"',
    "Elbow 3 inch",
)


@pytest.mark.parametrize(
    "q, harapan",
    [
        # Angka satu digit tidak boleh dibuang, dan harus cocok sebagai ukuran utuh.
        ("elbow 2", {'Elbow 2"', "Elbow 2 inch"}),
        ('elbow 2"', {'Elbow 2"', "Elbow 2 inch"}),
        ("elbow 2 inch", {"Elbow 2 inch"}),
        ("elbow 12", {"Elbow 12 inch"}),
        ("elbow 2,5", {"Elbow 2,5 inch"}),
        # Pecahan ditahan utuh: 3/4 bukan 3 dan bukan 1/4.
        ('elbow 3/4"', {'Elbow 3/4"'}),
        ("elbow 3", {"Elbow 3 inch"}),
        ("elbow 1/2", {'Elbow 1/2"'}),
        # Koma dan titik desimal dianggap sama.
        ("elbow 2.5", {"Elbow 2,5 inch"}),
    ],
)
def test_ukuran_tidak_tercampur(q, harapan):
    for i, uraian in enumerate(_ELBOW):
        _baris(f"KMP. {i}", uraian, 100_000, satuan="pcs")
    (k,) = svc.harga_wajar(q)["kelompok"]
    ketemu = {b["uraian"] for d in k["docking"] for b in d["baris"]}
    assert ketemu == harapan


@pytest.mark.parametrize(
    "q, uraian",
    [
        ("plat 8mm", "Plat baja 8 mm"),
        ("plat 8 mm", "Plat baja 8mm"),
        ("pipa sch40", "Pipa sch 40"),
        ("pipa sch 40", "Pipa sch40"),
    ],
)
def test_ukuran_berspasi_atau_tidak_tetap_ketemu(q, uraian):
    _baris("KMP. A", uraian, 100_000, satuan="kg")
    _baris("KMP. B", uraian.replace("8", "18").replace("40", "140"), 100_000, satuan="kg")
    ((d,),) = [k["docking"] for k in svc.harga_wajar(q)["kelompok"]]
    assert [b["uraian"] for b in d["baris"]] == [uraian]


def test_kata_kunci_yang_dicari_dikembalikan_utuh():
    """Layar menyebut apa yang dicari -- 3/4 harus terbaca 3/4, bukan hilang."""
    assert svc.harga_wajar('elbow 3/4" sch40')["kata"] == ["elbow", "3/4", "sch40"]


def test_kotak_cari_katalog_tidak_berubah():
    """Mode ketat tidak boleh bocor ke pencarian katalog yang sudah dipakai sehari-hari."""
    assert pencarian.pecah("pipa 2 inch") == ["pipa", "inch"]
    assert pencarian.pecah('elbow 3/4"') == ["elbow"]


def test_teks_kategori_tidak_ikut_dicari():
    """Semua baris di fixture berkategori PENGECATAN. Kalau kategori ikut dicari, Elbow ikut."""
    _baris("KMP. A", "Elbow sch40 3 inch", 1_050_000, satuan="pcs")
    assert svc.harga_wajar("pengecatan")["kelompok"] == []


def test_format_rapi_vol_sat_tidak_jatuh_ke_tanpa_satuan():
    """Format Rapi dengan kolom Vol/Sat (tanpa kolom Satuan): satuannya cuma ada di `satuan`."""
    _baris("KMP. A", "Pengecatan lambung", 60_000, satuan=None, sat_baru="m2")

    k = _satu("pengecatan")
    assert k["satuan"] == "m²"
    assert k["ejaan"] == ["m2"]


def test_volume_satuan_menang_kalau_dua_kolom_beda():
    """`bulk_patch()` menyunting `volume_satuan`, bukan `satuan` -- yang lama lebih baru."""
    _baris("KMP. A", "Pengecatan lambung", 60_000, satuan="m2", sat_baru="kg")
    assert _satu("pengecatan")["satuan"] == "m²"


def test_satuan_belum_dikenal_tetap_tampil_dengan_namanya():
    _baris("KMP. A", "Pipa baru", 500_000, satuan="m'")

    k = _satu("pipa")
    assert k["satuan"] == "m'"
    assert k["dikenali"] is False
    assert k["borongan"] is False, "cuma Ls/Lot/Paket yang borongan, bukan semua yang belum dikenal"


def test_tanpa_satuan_jadi_kelompok_sendiri_paling_bawah_tanpa_median():
    for kapal in ("KMP. A", "KMP. B", "KMP. C"):
        _baris(kapal, "Pengecatan lambung", 60_000)
        _baris(kapal, "Pengecatan lambung", 9_000_000, satuan=None)

    k_m2, k_kosong = svc.harga_wajar("pengecatan")["kelompok"]
    assert k_m2["satuan"] == "m²" and k_m2["tampilkan_ringkas"] is True
    assert k_kosong["satuan"] is None
    assert k_kosong["alasan"] == "tanpa_satuan"
    assert k_kosong["ringkas"] is None
    assert k_kosong["borongan"] is False
    assert k_kosong["ejaan"] == [], "'-' bukan ejaan satuan"


def test_borongan_ditandai():
    _baris("KMP. A", "Docking dan undocking", 25_000_000, satuan="LS")
    k = _satu("undocking")
    assert k["satuan"] == "Ls"
    assert k["borongan"] is True and k["dikenali"] is True


@pytest.mark.parametrize(
    "tertulis, borongan",
    [("Lot", True), ("Paket", True), ("LUMPSUM", True), ("Hari", False), ("Kali", False)],
)
def test_hanya_ls_lot_paket_yang_borongan(tertulis, borongan):
    """Keputusan 22 Oktober 2026. Dicek ujung ke ujung, bukan dibandingkan ke konstanta seed-nya."""
    _baris("KMP. A", "Pelayanan umum", 1_000_000, satuan=tertulis)
    assert _satu("pelayanan")["borongan"] is borongan


def test_addendum_ikut_dengan_label():
    _baris("KMP. A", "Pengecatan lambung", 60_000, tipe="Induk")
    _baris("KMP. A", "Pengecatan lambung", 80_000, tipe="Addendum")

    (d,) = _satu("pengecatan")["docking"]
    assert d["tipe"] == ["Addendum", "Induk"]
    assert {b["tipe_perjanjian"] for b in d["baris"]} == {"Induk", "Addendum"}


def test_klien_induk_dipakai():
    _baris("KMP. SINDU DWITAMA", "Pengecatan lambung", 60_000, pt="PT. AGUNG TRANSINA RAYA")
    (d,) = _satu("pengecatan")["docking"]
    assert d["klien"] == ["PT. AGUNG TAMA RAYA"]


def test_harga_nol_tidak_ikut():
    _baris("KMP. A", "Pengecatan lambung", 0)
    assert svc.harga_wajar("pengecatan")["kelompok"] == []


def test_docking_terbaru_di_atas_lalu_nama_kapal():
    _baris("KMP. B", "Replating", 30_000, satuan="kg", tahun="2025")
    _baris("KMP. C", "Replating", 30_000, satuan="kg", tahun="2026")
    _baris("KMP. A", "Replating", 30_000, satuan="kg", tahun="2026")

    urutan = [(d["tahun"], d["nama_kapal"]) for d in _satu("replating")["docking"]]
    assert urutan == [("2026", "KMP. A"), ("2026", "KMP. C"), ("2025", "KMP. B")]


def test_terlalu_banyak_baris_tidak_dihitung_dari_potongan(monkeypatch):
    monkeypatch.setattr(svc, "BATAS_BARIS", 2)
    for kapal in ("KMP. A", "KMP. B", "KMP. C"):
        _baris(kapal, "Pengecatan lambung", 60_000)

    hasil = svc.harga_wajar("pengecatan")
    assert hasil["terlalu_banyak"] is True
    assert hasil["kelompok"] == []
    assert hasil["total_cocok"] is None, "yang terbaca cuma potongan LIMIT, bukan jumlah asli"

    # Tepat di batas masih dihitung -- yang ditolak cuma yang MELEBIHI batas.
    monkeypatch.setattr(svc, "BATAS_BARIS", 3)
    hasil = svc.harga_wajar("pengecatan")
    assert hasil["terlalu_banyak"] is False
    assert hasil["total_cocok"] == 3
    assert len(hasil["kelompok"]) == 1


def test_kata_kunci_kosong_tidak_menjalankan_apa_pun():
    _baris("KMP. A", "Pengecatan lambung", 60_000)
    for q in (None, "", "   "):
        hasil = svc.harga_wajar(q)
        assert hasil["kelompok"] == [] and hasil["total_cocok"] == 0


def test_tidak_menulis_ke_tabel_katalog():
    _baris("KMP. A", "Pengecatan lambung", 60_000)
    with engine.connect() as c:
        sebelum = c.execute(text("SELECT * FROM tabel_katalog_harga ORDER BY id")).all()
    svc.harga_wajar("pengecatan")
    with engine.connect() as c:
        sesudah = c.execute(text("SELECT * FROM tabel_katalog_harga ORDER BY id")).all()
    assert sebelum == sesudah


def test_endpoint_butuh_login_dan_mengirim_aturan():
    client = TestClient(app)
    assert client.get("/analitik/harga-wajar", params={"q": "cat"}).status_code in (401, 403)

    token = jwt.encode(
        {"sub": "tes@contoh.com", "role": "user", "exp": int(time.time()) + 600},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    r = client.get(
        "/analitik/harga-wajar",
        params={"q": "pengecatan"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["aturan"] == {"min_kapal": svc.MIN_KAPAL, "rasio_sebar": svc.RASIO_SEBAR}


def test_harga_docking_adalah_nilai_tengah_barisnya():
    """Bukan baris pertama, bukan yang termahal, bukan rata-rata."""
    _baris("KMP. A", "Sandblasting lambung", 400_000)  # sengaja dulu: id terkecil
    _baris("KMP. A", "Sandblasting lambung", 60_000)
    _baris("KMP. A", "Sandblasting lambung", 65_000)
    _baris("KMP. B", "Sandblasting lambung", 62_000)
    _baris("KMP. C", "Sandblasting lambung", 66_000)

    k = _satu("sandblasting")
    (a,) = [d for d in k["docking"] if d["nama_kapal"] == "KMP. A"]
    assert (a["harga"], a["harga_min"], a["harga_max"]) == (65_000, 60_000, 400_000)
    assert k["ringkas"] == {"median": 65_000, "bawah": 63_500, "atas": 65_500}
    assert k["tampilkan_ringkas"] is True


@pytest.mark.parametrize(
    "harga, menyebar",
    [
        # Kuartil inklusif [100, 100, 300]: bawah 100.000, atas 200.000 -> tepat 2,0x.
        ((100_000, 100_000, 300_000), True),
        # [100, 100, 280]: atas 190.000 -> 1,9x, masih dianggap rapat.
        ((100_000, 100_000, 280_000), False),
    ],
)
def test_batas_menyebar_tepat_dua_kali(harga, menyebar):
    for kapal, h in zip(("KMP. A", "KMP. B", "KMP. C"), harga):
        _baris(kapal, "Pengecatan lambung", h)
    k = _satu("pengecatan")
    assert (k["alasan"] == "menyebar") is menyebar
    assert k["tampilkan_ringkas"] is not menyebar


def test_kelompok_yang_kapalnya_paling_banyak_di_atas():
    """Satu Ls yang lebih baru tidak boleh menggeser kelompok m² yang bisa dibandingkan."""
    _baris("KMP. Z", "Sandblasting lambung", 25_000_000, satuan="Ls", tahun="2026")
    for kapal in ("KMP. A", "KMP. B", "KMP. C"):
        _baris(kapal, "Sandblasting lambung", 120_000, tahun="2025")
    _baris("KMP. Y", "Sandblasting lambung", 3_000, satuan="kg", tahun="2025")

    urutan = [k["satuan"] for k in svc.harga_wajar("sandblasting")["kelompok"]]
    # m² (3 kapal) dulu; Ls dan kg sama-sama 1 kapal 1 baris -> urut nama satuan.
    assert urutan == ["m²", "Ls", "kg"]


def test_ukuran_desimal_tidak_cocok_dengan_ukuran_lain():
    _baris("KMP. A", "Elbow 1,5 inch", 300_000, satuan="pcs")
    _baris("KMP. B", "Elbow 150A", 2_000_000, satuan="pcs")
    _baris("KMP. C", "Elbow 15 inch", 2_500_000, satuan="pcs")

    (k,) = svc.harga_wajar("elbow 1,5")["kelompok"]
    assert [d["nama_kapal"] for d in k["docking"]] == ["KMP. A"]
