"""Pustaka pembaca Excel tidak boleh ikut dimuat saat backend menyala.

Memori yang terpakai terus selama service menyala adalah 97% tagihan Railway (23 Oktober
2026). pandas (~30 MB) dan openpyxl (~20 MB) cuma dipakai waktu impor, jadi di-import di dalam
fungsi yang memakainya. Satu `import pandas as pd` yang dikembalikan ke atas berkas mana pun
akan membuatnya menetap lagi tanpa ada yang terlihat salah -- tes ini yang berbunyi.

Dijalankan di proses Python terpisah: proses pytest ini sendiri sudah memuat openpyxl lewat
tes lain, jadi `sys.modules` di sini tidak bisa dipercaya.
"""

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def test_start_backend_tidak_memuat_pustaka_excel():
    kode = (
        "import sys, app.main; "
        "berat = [m for m in ('pandas', 'openpyxl', 'xlrd') if m in sys.modules]; "
        "print(','.join(berat))"
    )
    hasil = subprocess.run(
        [sys.executable, "-c", kode],
        cwd=BACKEND,
        env={**os.environ, "PYTHONPATH": str(BACKEND)},
        capture_output=True,
        text=True,
        check=True,
    )
    assert hasil.stdout.strip() == "", f"ikut dimuat saat start: {hasil.stdout.strip()}"
