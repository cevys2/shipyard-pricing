"""Master kategori pekerjaan, buat mengisi dropdown.

Sengaja terpisah dari `/analitik/tren-jasa/kategori`, yang kelihatannya mirip tapi menjawab
pertanyaan lain: yang di analitik adalah "kategori mana yang punya cukup data untuk
digambar grafiknya", jadi isinya lebih sedikit dan ikut berubah kalau `min_sampel` berubah.
Yang di sini adalah daftar pilihan yang sah untuk diisi orang -- kategori yang belum punya
satu baris data pun tetap harus bisa dipilih, kalau tidak tidak akan pernah ada barisnya.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.auth import get_current_user
from app.database import engine

router = APIRouter(prefix="/kategori", tags=["kategori"])


@router.get("")
def daftar_kategori(_: Annotated[dict, Depends(get_current_user)]):
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, nama FROM kategori WHERE aktif ORDER BY urutan, nama")
        ).mappings().all()
    return [dict(r) for r in rows]
