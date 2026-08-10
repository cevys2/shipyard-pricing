"""Kategori pekerjaan kanonik: seed, normalisasi, dan resolver.

Yang paling dijaga di sini bukan "apakah kodenya jalan", tapi satu hal yang kalau meleset
TIDAK menimbulkan error sama sekali: ekspresi normalisasi di aplikasi harus persis sama
dengan bentuk alias yang tersimpan di database. Kalau beda satu karakter, resolver cuma
tidak menemukan pasangan, `kategori_id` tinggal NULL, dan analitik diam-diam kehilangan
baris. Tidak ada yang merah, hasilnya saja yang salah.
"""

import json
from pathlib import Path

import pytest
from sqlalchemy import text

from app.database import (
    ensure_ahsp_tables,
    ensure_kategori_table,
    ensure_material_tables,
    engine,
    kategori_norm_sql,
    selaraskan_kategori,
)
from app.seed_kategori import PETA, baris_alias

FINAL_PETA = Path(__file__).resolve().parents[2] / "docs" / "final_peta.json"


@pytest.fixture(scope="module", autouse=True)
def kategori_siap():
    # ahsp_komponen punya foreign key ke sumber_daya, jadi tabel material harus ada dulu.
    ensure_material_tables()
    ensure_kategori_table()


def _kategori_ahsp(ahsp_id: int) -> str | None:
    with engine.connect() as c:
        return c.execute(
            text(
                "SELECT k.nama FROM ahsp a LEFT JOIN kategori k ON k.id = a.kategori_id "
                "WHERE a.id = :id"
            ),
            {"id": ahsp_id},
        ).scalar()


def _tulis(rows: list[dict[str, str]]) -> None:
    """Simpan baris katalog dan COMMIT -- resolver membuka koneksinya sendiri."""
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO tabel_katalog_harga "
                "(id, nama_kapal, tahun, uraian_pekerjaan, kategori_pekerjaan, harga_satuan) "
                "VALUES (:id, 'KMP. TES', '2025', 'tes', :kategori, 1)"
            ),
            rows,
        )


def _kategori_dari(id_: str) -> str | None:
    with engine.connect() as c:
        return c.execute(
            text(
                "SELECT k.nama FROM tabel_katalog_harga t "
                "LEFT JOIN kategori k ON k.id = t.kategori_id WHERE t.id = :id"
            ),
            {"id": id_},
        ).scalar()


def test_peta_python_sama_dengan_final_peta_json():
    """Sumber yang dijalankan (Python) dan catatan yang disepakati (JSON) tidak boleh berpisah.

    Peta di `app/seed_kategori.py` adalah yang benar-benar dieksekusi; `docs/final_peta.json`
    adalah hasil analisis yang disetujui VP marketing. Keduanya gampang diedit sendiri-sendiri.
    """
    if not FINAL_PETA.exists():
        pytest.skip("docs/final_peta.json tidak ada")
    catatan = json.loads(FINAL_PETA.read_text(encoding="utf-8"))
    assert {k: list(v) for k, v in PETA.items()} == catatan


def test_jumlah_kategori_dan_alias():
    assert len(PETA) == 11
    assert len(baris_alias()) == 83


def test_alias_tersimpan_dalam_bentuk_hasil_normalisasi():
    """Ini penjaga risiko terbesar bundel kategori.

    Resolver mencocokkan `norm(kategori_pekerjaan) = alias`. Jadi alias yang tersimpan wajib
    sudah berupa hasil normalisasi -- kalau ada satu saja yang belum (huruf kecil, spasi
    ganda, nbsp), alias itu tidak akan pernah cocok dengan apa pun, tanpa error.
    """
    with engine.connect() as c:
        meleset = c.execute(
            text(
                f"SELECT alias FROM kategori_alias "
                f"WHERE {kategori_norm_sql('alias')} IS DISTINCT FROM alias"
            )
        ).scalars().all()
    assert meleset == []


def test_seed_idempoten():
    """Dijalankan ulang tiap app start, jadi run kedua tidak boleh menggandakan apa pun."""
    ensure_kategori_table()
    ensure_kategori_table()
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM kategori")).scalar() == 11
        assert c.execute(text("SELECT count(*) FROM kategori_alias")).scalar() == 83
        assert c.execute(
            text("SELECT count(DISTINCT urutan) FROM kategori")
        ).scalar() == 11


def test_resolver_memetakan_sebutan_yang_berbeda_ke_satu_kategori():
    _tulis(
        [
            {"id": "T1", "kategori": "PIPA - PIPA"},
            {"id": "T2", "kategori": "Pipa-Pipa"},
            {"id": "T3", "kategori": "  piping  "},
            {"id": "T4", "kategori": "PEKERJAAN PIPA"},
        ]
    )
    selaraskan_kategori()
    for id_ in ("T1", "T2", "T3", "T4"):
        assert _kategori_dari(id_) == "PIPA - PIPA", id_


def test_normalisasi_memaafkan_nbsp_dan_spasi_beruntun():
    """Sel Excel sering membawa non-breaking space dan newline yang tidak kelihatan."""
    _tulis(
        [
            {"id": "N1", "kategori": "DOCKING\n  dan UNDOCKING"},
            {"id": "N2", "kategori": "docking dan undocking "},
        ]
    )
    selaraskan_kategori()
    assert _kategori_dari("N1") == "DOCKING & UNDOCKING"
    assert _kategori_dari("N2") == "DOCKING & UNDOCKING"


def test_teks_kategori_asli_tidak_pernah_ditimpa():
    """Keputusan K-6: `kategori_pekerjaan` adalah catatan laporan asli, bukan data kerja."""
    _tulis([{"id": "A1", "kategori": "Pipa-Pipa"}])
    selaraskan_kategori()
    with engine.connect() as c:
        asli = c.execute(
            text("SELECT kategori_pekerjaan FROM tabel_katalog_harga WHERE id = 'A1'")
        ).scalar()
    assert asli == "Pipa-Pipa"


def test_kategori_tak_dikenal_tetap_null():
    """Bukan ditebak, bukan dilempar ke LAIN-LAIN -- dibiarkan NULL supaya kelihatan."""
    _tulis([{"id": "X1", "kategori": "PEKERJAAN YANG BELUM PERNAH ADA"}])
    selaraskan_kategori()
    assert _kategori_dari("X1") is None


def test_resolver_tidak_menyentuh_baris_bertanda_manual():
    """Dua baris berteks kategori sama; satu dikoreksi manusia, satu tidak.

    Yang manual harus kebal sementara tetangganya tetap ikut resolver -- kalau tidak,
    setiap koreksi manusia akan terhapus diam-diam pada deploy berikutnya.
    """
    _tulis([{"id": "M1", "kategori": "Pipa-Pipa"}, {"id": "M2", "kategori": "Pipa-Pipa"}])
    selaraskan_kategori()
    assert _kategori_dari("M1") == "PIPA - PIPA"

    with engine.begin() as c:
        c.execute(
            text(
                "UPDATE tabel_katalog_harga SET kategori_sumber = 'manual', "
                "kategori_id = (SELECT id FROM kategori WHERE nama = 'LAIN-LAIN') "
                "WHERE id = 'M1'"
            )
        )

    selaraskan_kategori()
    selaraskan_kategori()
    assert _kategori_dari("M1") == "LAIN-LAIN"
    assert _kategori_dari("M2") == "PIPA - PIPA"


def test_resolver_idempoten():
    """Panggilan kedua harus nol baris, bukan menulis ulang isi yang sama."""
    _tulis([{"id": "I1", "kategori": "REPLATING"}, {"id": "I2", "kategori": "Konstruksi"}])
    assert selaraskan_kategori() == 2
    assert selaraskan_kategori() == 0
    assert _kategori_dari("I1") == "REPLATING"
    assert _kategori_dari("I2") == "KONSTRUKSI"


def test_semua_83_alias_benar_benar_terpetakan():
    """Setiap alias di seed dimasukkan sebagai baris katalog, lalu dicek mendarat di kategorinya.

    Ini pengganti lokal untuk verifikasi produksi "nol baris tanpa kategori_id". Yang bisa
    dibuktikan di sini: tidak ada alias yang mati. Yang TIDAK bisa dibuktikan di sini: apakah
    83 alias ini menutup semua teks kategori yang benar-benar ada di produksi -- itu hanya
    ketahuan dengan menghitung di database produksi.
    """
    baris = [
        {"id": f"S{i}", "kategori": r["alias"]} for i, r in enumerate(baris_alias())
    ]
    _tulis(baris)
    selaraskan_kategori()

    with engine.connect() as c:
        gantung = c.execute(
            text(
                "SELECT kategori_pekerjaan FROM tabel_katalog_harga "
                "WHERE id LIKE 'S%' AND kategori_id IS NULL"
            )
        ).scalars().all()
        per_kategori = dict(
            c.execute(
                text(
                    "SELECT k.nama, count(*) FROM tabel_katalog_harga t "
                    "JOIN kategori k ON k.id = t.kategori_id "
                    "WHERE t.id LIKE 'S%' GROUP BY k.nama"
                )
            ).all()
        )

    assert gantung == []
    assert per_kategori == {nama: len(alias) for nama, alias in PETA.items()}


def test_kategori_sumber_hanya_menerima_alias_atau_manual():
    _tulis([{"id": "C1", "kategori": "REPLATING"}])
    with pytest.raises(Exception):
        with engine.begin() as c:
            c.execute(
                text("UPDATE tabel_katalog_harga SET kategori_sumber = 'entah' WHERE id = 'C1'")
            )


def test_kategori_norm_sql_menolak_yang_bukan_nama_kolom():
    """Argumennya masuk ke SQL sebagai identifier, jadi bentuknya dijaga di pintu masuk."""
    assert kategori_norm_sql() == kategori_norm_sql("kategori_pekerjaan")
    assert "t.kategori_pekerjaan" in kategori_norm_sql("t.kategori_pekerjaan")
    for jahat in ("kategori_pekerjaan); DROP TABLE kategori; --", "a b", "", "1kolom"):
        with pytest.raises(ValueError):
            kategori_norm_sql(jahat)


def test_ahsp_menerjemahkan_kategori_teks_jadi_kategori_id():
    """Dropdown mengirim nama kanonik; teks lama yang berantakan juga harus tetap kena."""
    from app.schemas.ahsp import AhspCreate
    from app.services import ahsp as ahsp_service

    ensure_ahsp_tables()
    with engine.begin() as c:
        c.execute(text("TRUNCATE ahsp CASCADE"))

    id_rapi = ahsp_service.create_ahsp(
        AhspCreate(uraian="Sandblasting SA 2.5", satuan="m2", kategori="PERAWATAN LAMBUNG"),
        aktor="tes",
    )
    id_lama = ahsp_service.create_ahsp(
        AhspCreate(uraian="Ganti pipa dinas", satuan="m", kategori="pipa-pipa"),
        aktor="tes",
    )
    id_kosong = ahsp_service.create_ahsp(
        AhspCreate(uraian="Tanpa kategori", satuan="ls"), aktor="tes"
    )

    assert _kategori_ahsp(id_rapi) == "PERAWATAN LAMBUNG"
    assert _kategori_ahsp(id_lama) == "PIPA - PIPA"
    assert _kategori_ahsp(id_kosong) is None


def test_ahsp_kategori_id_ikut_berubah_saat_kategori_diperbarui():
    """Kalau teksnya berubah tapi id-nya tidak, analitik membaca kategori lama tanpa error."""
    from app.schemas.ahsp import AhspCreate, AhspUpdate
    from app.services import ahsp as ahsp_service

    ensure_ahsp_tables()
    with engine.begin() as c:
        c.execute(text("TRUNCATE ahsp CASCADE"))

    ahsp_id = ahsp_service.create_ahsp(
        AhspCreate(uraian="Pindah kategori", satuan="ls", kategori="KONSTRUKSI"), aktor="tes"
    )
    assert _kategori_ahsp(ahsp_id) == "KONSTRUKSI"

    ahsp_service.update_ahsp(ahsp_id, AhspUpdate(kategori="REPLATING"), aktor="tes")
    assert _kategori_ahsp(ahsp_id) == "REPLATING"

    # Mengubah kolom lain tidak boleh menyentuh kategorinya.
    ahsp_service.update_ahsp(ahsp_id, AhspUpdate(satuan="kg"), aktor="tes")
    assert _kategori_ahsp(ahsp_id) == "REPLATING"


def test_backfill_ahsp_tidak_menimpa_pilihan_yang_sudah_ada():
    """Sesudah dropdown ada, pilihan pengguna bisa beda dari teks lamanya.

    Backfill yang jalan tiap app start dan mengisi ulang dari teks akan menarik pilihan itu
    balik -- diam-diam, tiap deploy. Karena itu backfill hanya menyentuh yang masih NULL.
    """
    from app.schemas.ahsp import AhspCreate
    from app.services import ahsp as ahsp_service

    ensure_ahsp_tables()
    with engine.begin() as c:
        c.execute(text("TRUNCATE ahsp CASCADE"))

    ahsp_id = ahsp_service.create_ahsp(
        AhspCreate(uraian="Beda teks dan pilihan", satuan="ls", kategori="KONSTRUKSI"),
        aktor="tes",
    )
    with engine.begin() as c:
        c.execute(
            text(
                "UPDATE ahsp SET kategori_id = (SELECT id FROM kategori WHERE nama = 'TANGKI') "
                "WHERE id = :id"
            ),
            {"id": ahsp_id},
        )

    ensure_ahsp_tables()
    ensure_ahsp_tables()
    assert _kategori_ahsp(ahsp_id) == "TANGKI"


def test_endpoint_kategori_terpasang_dan_urut():
    """Dropdown di frontend mati diam-diam kalau router-nya lupa di-include di main.py."""
    import time

    from fastapi.testclient import TestClient
    from jose import jwt

    from app.config import settings
    from app.main import app

    token = jwt.encode(
        {"sub": "tes@contoh.com", "role": "admin", "exp": int(time.time()) + 600},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with TestClient(app) as klien:
        resp = klien.get("/kategori", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    nama = [r["nama"] for r in resp.json()]
    assert nama == list(PETA), "urutannya harus ikut kolom `urutan`, bukan abjad"


def test_bentuk_ekspresi_normalisasi_dipaku():
    """Ekspresinya dipaku ke bentuk literal, bukan sekadar "ada".

    83 alias di database sudah tersimpan sebagai hasil normalisasi ini. Merapikan
    ekspresinya -- menambah `lower()`, mengganti `btrim` jadi `trim`, apa pun -- akan
    membuat sebagian alias berhenti cocok, dan tidak ada yang error: `kategori_id` cuma
    jadi NULL dan barisnya raib dari analitik. Jadi kalau tes ini merah, jawabannya
    hampir pasti bukan "perbarui ekspektasinya".
    """
    assert kategori_norm_sql() == (
        "upper(btrim(regexp_replace(replace(kategori_pekerjaan, chr(160), ' '), "
        "'\\s+', ' ', 'g')))"
    )
