"""Impor repair list dari ujung ke ujung: berkas Excel -> pratinjau -> database.

Yang diuji di sini bukan lagi pembacaan berkasnya (itu di `test_repair_list_parser.py`),
melainkan bahwa angka yang sudah benar itu benar-benar MENDARAT dan tidak hilang lagi
sesudahnya. Dua hal yang paling mahal kalau meleset, dan keduanya tidak menimbulkan error:

1. Kolom baru tidak ikut tersimpan -- impor kelihatan sukses, tapi `volume` NULL semua dan
   palang rekonsiliasi jadi mustahil dipasang untuk selamanya.
2. Kolom baru tersimpan lalu TERTIMPA waktu barisnya disunting dari layar katalog, yang
   cuma mengirim delapan kolom lama.
"""

import io
import time

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from openpyxl import Workbook
from sqlalchemy import text

from app.config import settings
from app.database import engine, ensure_katalog_kolom_rincian
from app.main import app
from app.schemas.catalog import BulkCatalogCreate, CatalogItemBase, TipePerjanjian
from app.services.catalog import bulk_create, list_catalog

KAPAL = "KN SAR TES 001"
TAHUN = "2026"
JUMLAH = 1232


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def token():
    return jwt.encode(
        {"sub": "tes@contoh.com", "role": "admin", "exp": int(time.time()) + 600},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


@pytest.fixture
def berkas():
    """Repair list mini yang JUMLAH-nya 1.232 -- bentuk yang sama dipakai tes parser."""
    from tests.test_repair_list_parser import _berkas

    return _berkas()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _unggah(client, token, isi: bytes):
    return client.post(
        "/catalog/import/repair-list-preview",
        files={"file": ("repair-list.xlsx", isi, "application/vnd.ms-excel")},
        headers=_auth(token),
    )


def _baris_db(id_: str) -> dict:
    with engine.connect() as c:
        return dict(
            c.execute(
                text(
                    "SELECT volume, satuan, induk_uraian, keterangan, volume_satuan, "
                    "harga_satuan, tipe_perjanjian, uraian_pekerjaan "
                    "FROM tabel_katalog_harga WHERE id = :id"
                ),
                {"id": id_},
            ).mappings().first()
        )


# --- DDL --------------------------------------------------------------------------------

def test_keempat_kolom_ada_dan_semuanya_nullable():
    with engine.connect() as c:
        kolom = dict(
            c.execute(
                text(
                    "SELECT column_name, is_nullable FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = ANY(:k)"
                ),
                {"t": settings.catalog_table, "k": ["volume", "satuan", "induk_uraian", "keterangan"]},
            ).all()
        )

    assert set(kolom) == {"volume", "satuan", "induk_uraian", "keterangan"}
    assert set(kolom.values()) == {"YES"}, "kolom baru wajib nullable -- 6.673 baris lama tidak punya isinya"


def test_ensure_idempoten():
    """Dijalankan tiap app start, jadi panggilan kedua tidak boleh error atau mengubah apa pun."""
    ensure_katalog_kolom_rincian()
    ensure_katalog_kolom_rincian()

    with engine.connect() as c:
        assert c.execute(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = 'volume'"
            ),
            {"t": settings.catalog_table},
        ).scalar() == 1


def test_kolom_lama_tidak_ikut_berubah():
    """Aturan tabel ini: menambah kolom nullable boleh, mengubah kolom lama tidak."""
    with engine.connect() as c:
        lama = dict(
            c.execute(
                text(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = ANY(:k)"
                ),
                {
                    "t": settings.catalog_table,
                    "k": ["id", "nama_kapal", "volume_satuan", "harga_satuan", "kategori_pekerjaan"],
                },
            ).all()
        )

    assert lama == {
        "id": "text",
        "nama_kapal": "text",
        "volume_satuan": "text",
        "harga_satuan": "double precision",
        "kategori_pekerjaan": "text",
    }


# --- simpan & baca ----------------------------------------------------------------------

def _simpan_satu(**tambahan) -> str:
    item = CatalogItemBase(
        kategori_pekerjaan="PERMESINAN",
        uraian_pekerjaan="Excentric P/N 51.06501-0339",
        volume_satuan="Pcs",
        harga_satuan=12_500_000,
        **tambahan,
    )
    bulk_create(
        BulkCatalogCreate(
            nama_perusahaan="BASARNAS",
            nama_kapal=KAPAL,
            tahun=TAHUN,
            tipe_perjanjian=TipePerjanjian.induk,
            items=[item],
        ),
        aktor="tes",
    )
    return f"{KAPAL.replace(' ', '_').upper()}-{TAHUN}-001"


def test_keempat_kolom_benar_benar_tersimpan():
    id_ = _simpan_satu(
        volume=1,
        satuan="Pcs",
        induk_uraian="Perawatan Mesin Induk › Penggantian Part Main Engine Tengah",
        keterangan="harga negosiasi terakhir",
    )

    baris = _baris_db(id_)
    assert float(baris["volume"]) == 1
    assert baris["satuan"] == "Pcs"
    assert baris["induk_uraian"].endswith("Penggantian Part Main Engine Tengah")
    assert baris["keterangan"] == "harga negosiasi terakhir"


def test_kolom_baru_ikut_terbaca_lewat_list_catalog():
    _simpan_satu(volume=3, satuan="unit", induk_uraian="Sistem Propulsi", keterangan="ket")

    (baris,) = [r for r in list_catalog(kapal=KAPAL) if r.uraian_pekerjaan.startswith("Excentric")]

    assert baris.volume == 3
    assert baris.satuan == "unit"
    assert baris.induk_uraian == "Sistem Propulsi"
    assert baris.keterangan == "ket"


def test_baris_tanpa_isi_baru_tetap_null_bukan_strip():
    """6.673 baris lama memang tidak punya nilainya. NULL mengatakan itu; "-" mengarang."""
    id_ = _simpan_satu()

    baris = _baris_db(id_)
    assert baris["volume"] is None
    assert baris["satuan"] is None
    assert baris["induk_uraian"] is None
    assert baris["keterangan"] is None
    assert baris["volume_satuan"] == "Pcs", "kolom lama tetap memakai isinya sendiri"


@pytest.mark.parametrize("kosong", ["", "   ", "-"])
def test_teks_kosong_dan_strip_disimpan_sebagai_null(kosong):
    """Supaya kolom baru cuma punya SATU cara mengatakan "tidak tahu"."""
    id_ = _simpan_satu(satuan=kosong, induk_uraian=kosong, keterangan=kosong)

    baris = _baris_db(id_)
    assert baris["satuan"] is None
    assert baris["induk_uraian"] is None
    assert baris["keterangan"] is None


def test_menyunting_baris_tidak_menghapus_kolom_impor(client, token):
    """Layar edit katalog cuma mengirim delapan kolom lama.

    Kalau keempat kolom baru ikut di-UPDATE, satu suntingan sepele -- membetulkan typo di
    uraian -- akan menimpanya jadi NULL. Tidak ada error, tidak ada yang merah; data
    provenance impornya hilang begitu saja.
    """
    id_ = _simpan_satu(volume=1, satuan="Pcs", induk_uraian="M/E Kiri", keterangan="dari repair list")

    resp = client.patch(
        "/catalog",
        json={
            "updates": [
                {
                    "id": id_,
                    "data": {
                        "nama_perusahaan": "BASARNAS",
                        "nama_kapal": KAPAL,
                        "tipe_perjanjian": "Induk",
                        "tahun": TAHUN,
                        "kategori_pekerjaan": "PERMESINAN",
                        "uraian_pekerjaan": "Excentric P/N 51.06501-0339 (typo dibetulkan)",
                        "volume_satuan": "Pcs",
                        "harga_satuan": 12_500_000,
                    },
                }
            ]
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text

    baris = _baris_db(id_)
    assert baris["uraian_pekerjaan"].endswith("(typo dibetulkan)"), "suntingannya harus tetap berlaku"
    assert float(baris["volume"]) == 1, "volume ikut terhapus waktu barisnya disunting"
    assert baris["satuan"] == "Pcs"
    assert baris["induk_uraian"] == "M/E Kiri"
    assert baris["keterangan"] == "dari repair list"


# --- endpoint ---------------------------------------------------------------------------

def test_pratinjau_mengembalikan_rekonsiliasi_yang_cocok(client, token, berkas):
    resp = _unggah(client, token, berkas)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["items"]) == 11
    assert body["rekonsiliasi"] == {
        "jumlah_dokumen": JUMLAH,
        "ppn_dokumen": 135.52,
        "total_dokumen": 1367.52,
        "jumlah_terbaca": JUMLAH,
        "selisih": 0,
        "cocok": True,
    }
    assert body["warnings"] == []
    assert body["detected_tahun"] == ""


def test_pratinjau_berkas_rusak_jadi_400_bukan_500(client, token):
    resp = client.post(
        "/catalog/import/repair-list-preview",
        files={"file": ("rusak.xlsx", b"ini bukan xlsx", "application/vnd.ms-excel")},
        headers=_auth(token),
    )

    assert resp.status_code == 400
    assert "Gagal membaca file" in resp.json()["detail"]


def test_pratinjau_wajib_login(client, berkas):
    resp = client.post(
        "/catalog/import/repair-list-preview",
        files={"file": ("x.xlsx", berkas, "application/vnd.ms-excel")},
    )
    assert resp.status_code in (401, 403)


def test_simpan_dari_pratinjau_mendarat_utuh_dan_masih_rekonsiliasi(client, token, berkas):
    """Perjalanan penuh: berkas -> pratinjau -> simpan -> jumlah di DB = JUMLAH di dokumen.

    Ini palang yang selama ini tidak ada. Sebelumnya jumlah baris di katalog cuma bisa
    dibandingkan dengan nilai dokumen kalau orangnya menghitung manual di luar aplikasi.
    """
    pratinjau = _unggah(client, token, berkas).json()

    simpan = client.post(
        "/catalog/import/repair-list-commit",
        json={
            "nama_perusahaan": pratinjau["detected_nama_perusahaan"],
            "nama_kapal": pratinjau["detected_nama_kapal"],
            "tahun": TAHUN,
            "items": [
                {
                    "kategori_pekerjaan": it["kategori"] or "-",
                    "uraian_pekerjaan": it["uraian"],
                    "volume_satuan": it["satuan"] or "-",
                    "harga_satuan": it["harga"],
                    "volume": it["volume"],
                    "satuan": it["satuan"],
                    "induk_uraian": it["induk_uraian"],
                    "keterangan": it["keterangan"],
                }
                for it in pratinjau["items"]
            ],
        },
        headers=_auth(token),
    )

    assert simpan.status_code == 200, simpan.text
    assert simpan.json()["saved"] == 11

    with engine.connect() as c:
        nilai = c.execute(
            text(
                "SELECT sum(coalesce(volume, 1) * harga_satuan) FROM tabel_katalog_harga "
                "WHERE nama_kapal = :k"
            ),
            {"k": KAPAL.upper()},
        ).scalar()
    assert float(nilai) == JUMLAH, "nilai yang tersimpan tidak sama dengan JUMLAH di dokumen"


def test_baris_repair_list_masuk_sebagai_induk(client, token, berkas):
    pratinjau = _unggah(client, token, berkas).json()
    client.post(
        "/catalog/import/repair-list-commit",
        json={
            "nama_perusahaan": "BASARNAS",
            "nama_kapal": KAPAL,
            "tahun": TAHUN,
            "items": [
                {"uraian_pekerjaan": it["uraian"], "harga_satuan": it["harga"]}
                for it in pratinjau["items"]
            ],
        },
        headers=_auth(token),
    )

    with engine.connect() as c:
        tipe = c.execute(
            text("SELECT DISTINCT tipe_perjanjian FROM tabel_katalog_harga WHERE nama_kapal = :k"),
            {"k": KAPAL.upper()},
        ).scalars().all()
    assert tipe == ["Induk"]


def test_asal_impor_terekam_di_audit_log(client, token, berkas):
    """Repair list dan laporan realisasi sama-sama jadi "Induk", jadi yang membedakan
    keduanya cuma jejak ini. Tanpa `sumber`, harga kesepakatan awal dan harga realisasi
    akhir tidak bisa dipisahkan lagi setelah tersimpan."""
    pratinjau = _unggah(client, token, berkas).json()
    client.post(
        "/catalog/import/repair-list-commit",
        json={
            "nama_perusahaan": "BASARNAS",
            "nama_kapal": KAPAL,
            "tahun": TAHUN,
            "items": [
                {"uraian_pekerjaan": it["uraian"], "harga_satuan": it["harga"]}
                for it in pratinjau["items"]
            ],
        },
        headers=_auth(token),
    )

    with engine.connect() as c:
        detail = c.execute(
            text("SELECT detail FROM audit_log WHERE entitas = 'katalog_harga' ORDER BY id DESC")
        ).scalars().first()
    assert detail["sumber"] == "import-repair-list"
    assert detail["nama_kapal"] == KAPAL.upper()


def test_simpan_tanpa_baris_ditolak(client, token):
    resp = client.post(
        "/catalog/import/repair-list-commit",
        json={"nama_perusahaan": "BASARNAS", "nama_kapal": KAPAL, "tahun": TAHUN, "items": []},
        headers=_auth(token),
    )
    assert resp.status_code == 422


def test_uraian_kembar_tersimpan_terpisah_dengan_induk_yang_berbeda(client, token, berkas):
    """Dua baris "Excentric" dengan harga beda harus tetap bisa dibedakan di katalog."""
    pratinjau = _unggah(client, token, berkas).json()
    excentric = [it for it in pratinjau["items"] if "Excentric" in it["uraian"]]
    client.post(
        "/catalog/import/repair-list-commit",
        json={
            "nama_perusahaan": "BASARNAS",
            "nama_kapal": KAPAL,
            "tahun": TAHUN,
            "items": [
                {
                    "uraian_pekerjaan": it["uraian"],
                    "harga_satuan": it["harga"],
                    "induk_uraian": it["induk_uraian"],
                }
                for it in excentric
            ],
        },
        headers=_auth(token),
    )

    with engine.connect() as c:
        baris = c.execute(
            text(
                "SELECT induk_uraian, harga_satuan FROM tabel_katalog_harga "
                "WHERE nama_kapal = :k ORDER BY harga_satuan"
            ),
            {"k": KAPAL.upper()},
        ).all()

    assert [h for _, h in baris] == [12, 15]
    assert len({i for i, _ in baris}) == 2, "kedua baris kehilangan pembedanya"


# --- berkas .xls lama -------------------------------------------------------------------

def test_berkas_bukan_excel_ditolak_dengan_pesan(client, token):
    wb = Workbook()
    wb.active.append(["cuma satu sel"])
    buf = io.BytesIO()
    wb.save(buf)

    resp = _unggah(client, token, buf.getvalue())

    assert resp.status_code == 400
    assert "judul tabel" in resp.json()["detail"]
