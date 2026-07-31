"""Perbaikan 2 -- banyak baris dikirim dalam satu perintah INSERT."""

from sqlalchemy import event, text

from app.database import engine
from app.schemas.catalog import BulkCatalogCreate, CatalogItemBase, TipePerjanjian
from app.services.catalog import bulk_create

KAPAL = "KMP. RHAMA GIRI NUSA"


def _items(n: int, tag: str = "B"):
    return [
        CatalogItemBase(
            kategori_pekerjaan="DOCKING",
            uraian_pekerjaan=f"{tag}-{i}",
            volume_satuan="Ls",
            harga_satuan=1000 + i,
        )
        for i in range(n)
    ]


def _payload(items, tipe=TipePerjanjian.induk, tahun="2025"):
    return BulkCatalogCreate(
        nama_perusahaan="PT TES",
        nama_kapal=KAPAL,
        tahun=tahun,
        tipe_perjanjian=tipe,
        items=items,
    )


class HitungPerintah:
    """Menghitung perintah SQL yang benar-benar dikirim ke Postgres.

    Dipakai supaya klaim '400 perintah jadi 8' dibuktikan, bukan diperkirakan.
    """

    def __enter__(self):
        self.n = 0

        def dengar(conn, cursor, statement, parameters, context, executemany):
            self.n += 1

        self._dengar = dengar
        event.listen(engine, "before_cursor_execute", dengar)
        return self

    def __exit__(self, *a):
        event.remove(engine, "before_cursor_execute", self._dengar)


def test_impor_396_baris_pakai_8_perintah():
    """50 Induk + 346 Addendum, persis seperti kejadian produksi 31 Juli 2026.

    Tiap panggilan bulk_create = kunci penasihat + SELECT penomoran + 1 INSERT + 1 audit
    = 4 perintah. Dua panggilan = 8. Sebelumnya 400.
    """
    with HitungPerintah() as hitung:
        with engine.begin() as conn:
            bulk_create(_payload(_items(50, "I")), aktor="tes", conn=conn)
            bulk_create(
                _payload(_items(346, "A"), TipePerjanjian.addendum), aktor="tes", conn=conn
            )

    assert hitung.n == 8, f"harusnya 8 perintah, dapat {hitung.n}"

    with engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM tabel_katalog_harga")).scalar() == 396


def test_1200_baris_terpecah_500_500_200_tanpa_tertukar():
    """Periksa isi baris di batas antar-potongan -- tempat paling rawan tertukar."""
    with engine.begin() as conn:
        bulk_create(_payload(_items(1200, "C")), aktor="tes", conn=conn)

    with engine.connect() as c:
        rows = dict(
            c.execute(
                text(
                    "SELECT id, uraian_pekerjaan FROM tabel_katalog_harga "
                    "WHERE uraian_pekerjaan LIKE 'C-%'"
                )
            ).all()
        )
    assert len(rows) == 1200

    prefix = "KMP._RHAMA_GIRI_NUSA-2025-"
    for nomor in (1, 500, 501, 1000, 1001, 1200):
        id_ = f"{prefix}{nomor:03d}"
        assert rows[id_] == f"C-{nomor - 1}", (
            f"baris {nomor} tertukar: {id_} berisi {rows[id_]!r}, harusnya 'C-{nomor - 1}'"
        )


def test_harga_dan_uraian_tidak_tergeser_di_batas_potongan():
    with engine.begin() as conn:
        bulk_create(_payload(_items(1200, "D")), aktor="tes", conn=conn)

    with engine.connect() as c:
        rows = c.execute(
            text(
                "SELECT uraian_pekerjaan, harga_satuan FROM tabel_katalog_harga "
                "WHERE uraian_pekerjaan LIKE 'D-%'"
            )
        ).all()
    for uraian, harga in rows:
        ke = int(uraian.split("-")[1])
        assert harga == 1000 + ke, f"{uraian} harganya {harga}, harusnya {1000 + ke}"


def test_jumlah_perintah_naik_sesuai_jumlah_potongan():
    """1.200 baris = 3 potongan, jadi 3 INSERT (total 6 perintah dalam satu panggilan)."""
    with HitungPerintah() as hitung:
        with engine.begin() as conn:
            bulk_create(_payload(_items(1200, "E")), aktor="tes", conn=conn)
    assert hitung.n == 6, f"harusnya 6 perintah (lock + select + 3 insert + audit), dapat {hitung.n}"


def test_id_identik_dengan_perilaku_lama():
    """Format dan urutan ID tidak boleh bergeser gara-gara penggabungan INSERT."""
    with engine.begin() as conn:
        bulk_create(_payload(_items(7, "F")), aktor="tes", conn=conn)

    with engine.connect() as c:
        ids = [
            r[0]
            for r in c.execute(
                text("SELECT id FROM tabel_katalog_harga ORDER BY id")
            ).all()
        ]
    prefix = "KMP._RHAMA_GIRI_NUSA-2025-"
    assert ids == [f"{prefix}{i:03d}" for i in range(1, 8)]


def test_nilai_kosong_tetap_jatuh_ke_strip():
    """kategori dan satuan kosong tetap jadi '-' seperti sebelumnya."""
    with engine.begin() as conn:
        bulk_create(
            _payload(
                [
                    CatalogItemBase(
                        kategori_pekerjaan="",
                        uraian_pekerjaan="tanpa kategori",
                        volume_satuan="",
                        harga_satuan=500,
                    )
                ]
            ),
            aktor="tes",
            conn=conn,
        )

    with engine.connect() as c:
        kat, sat, pt, kpl = c.execute(
            text(
                "SELECT kategori_pekerjaan, volume_satuan, nama_perusahaan, nama_kapal "
                "FROM tabel_katalog_harga LIMIT 1"
            )
        ).first()
    assert kat == "-" and sat == "-"
    assert pt == "PT TES" and kpl == KAPAL.upper()
