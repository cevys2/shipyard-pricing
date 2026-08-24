"""
Parser khusus untuk file "REALISASI BIAYA DOCKING" (format laporan, bukan tabel flat).
Aturan ekstraksi (ditetapkan bareng user):
  1. Baris masuk Addendum kalau kolom Keterangan mengandung kata "tambahan".
  2. Baris masuk Induk kalau kolom Harga Utama > 0 - berlaku juga untuk status
     "pengembangan", "batal", "included", atau kosong.
  3. Uraian Pekerjaan digabung dari kolom setelah NO. sampai sebelum kolom Qty/Volume.
  3b. Qty dan Sat ikut dikeluarkan sebagai `volume` + `satuan` (angka dan teks terpisah),
     selain tetap mengisi `volume_satuan` yang lama apa adanya.
  4. Kategori Pekerjaan diambil dari baris header section (bertanda angka romawi di
     kolom NO.), dengan prefix angka romawi dibuang dari teksnya.
  5. Hanya baris dengan harga > 0 (bukan blank/"-") yang diekstrak.

Posisi kolom (Keterangan, Harga, dst) di-scan ulang tiap file karena tidak tetap.
"""
import io
import re

import openpyxl

ROMAN_TOKEN_RE = re.compile(r'^M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$', re.IGNORECASE)
YEAR_RE = re.compile(r'\b(20\d{2})\b')

# Label baris yang bukan pekerjaan. Empat yang terakhir label blok tanda tangan, dan
# ketiadaannya sempat mahal: di baris "Diketahui dan Disetujui oleh :" ada sel tanggal di
# kolom harga satuan, dan xlrd mengembalikannya sebagai NOMOR SERI Excel, bukan tanggal.
# Jadi tiap berkas docking menyumbang satu baris katalog palsu seharga 46.197 -- angka yang
# cukup masuk akal sebagai harga sehingga tidak pernah ada yang curiga. ('di t.tangani oleh'
# sudah lebih dulu ada di sini persis karena alasan yang sama.)
#
# Sengaja TIDAK diganti "berhenti membaca begitu ketemu TOTAL": kalau suatu saat ada berkas
# yang punya baris Total per seksi di tengah tabel, aturan itu akan memotong sisa berkasnya
# diam-diam -- kegagalan yang jauh lebih mahal daripada satu baris sampah.
# Pemisah rantai baris induk. Didefinisikan di sini, bukan di repair_list_parser,
# karena modul itu sudah mengimpor dari sini -- kalau arahnya dibalik, keduanya saling
# impor dan aplikasi gagal start di baris import, jauh sebelum ada berkas yang dibaca.
PEMISAH_INDUK = " › "


NOISE_EXACT = {
    'realisasi', 'mulai', 'selesai', 'keterangan', 'kontrak induk', 'catatan',
    'total', 'tanda tangan', 'jabatan', 'nomor', 'tanggal', 'perihal', 'lampiran',
    'di t.tangani oleh', 'diketahui', 'disetujui', 'mengetahui', 'dibuat oleh',
}


def is_roman(s: str) -> bool:
    return bool(s) and bool(ROMAN_TOKEN_RE.match(s))


def norm(s) -> str:
    if s is None:
        return ""
    return str(s).strip().lower().rstrip(':').strip()


def norm_nospace(s) -> str:
    return re.sub(r'\s+', '', norm(s))


def strip_roman_prefix(text: str) -> str:
    m = re.match(r'^([IVXLCDM]+)([.\s]+)(.*)$', text.strip(), re.IGNORECASE)
    if m and is_roman(m.group(1)):
        return m.group(3).strip()
    return text.strip()


# Sebutan kolom uraian yang dipakai di berbagai template laporan. "nama barang" muncul di
# Lampiran Perjanjian KMP. Portlink II 2026; tanpa dia, seluruh berkas terbaca nol baris.
JUDUL_URAIAN = ('uraian', 'namabarang', 'namapekerjaan', 'deskripsi', 'description')


def find_header_idx(values):
    for i, row in enumerate(values):
        texts = [norm_nospace(c) for c in row if c]
        joined = ' '.join(texts)
        if any(u in joined for u in JUDUL_URAIAN) and any(
            k in joined for k in ('volume', 'qty', 'harga')
        ):
            return i
    return None


def build_group_labels(header_row):
    labels = {}
    last = None
    for ci, val in enumerate(header_row):
        if val is not None and str(val).strip():
            last = str(val).strip()
        if last:
            labels[ci] = last
    return labels


def find_group_start(group_labels, must_have, must_not_have=(), after=None):
    for ci in sorted(group_labels.keys()):
        if after is not None and ci <= after:
            continue
        lbl = group_labels[ci].lower()
        if all(k in lbl for k in must_have) and not any(k in lbl for k in must_not_have):
            return ci
    return None


def find_harga_group_start(group_labels, must_have, must_not_have=(), after=None):
    candidates = []
    for ci in sorted(group_labels.keys()):
        if after is not None and ci <= after:
            continue
        lbl = group_labels[ci].lower()
        if all(k in lbl for k in must_have) and not any(k in lbl for k in must_not_have):
            candidates.append(ci)
    if not candidates:
        return None
    for ci in candidates:
        if 'rp' in group_labels[ci].lower():
            return ci
    return candidates[0]


def group_range(group_labels, group_start_col):
    if group_start_col is None:
        return None, None
    starts = sorted(set(group_labels.keys()))
    boundaries = []
    prev_label = None
    for ci in starts:
        if group_labels[ci] != prev_label:
            boundaries.append(ci)
            prev_label = group_labels[ci]
    boundaries.append(max(starts) + 1)
    for i, b in enumerate(boundaries):
        if b == group_start_col:
            return b, boundaries[i + 1]
    return group_start_col, group_start_col + 2


def max_num_in_range(row, start, end):
    best = None
    for ci in range(start, min(end, len(row))):
        v = row[ci]
        if v is None or (isinstance(v, str) and v.strip() in ('', '-')):
            continue
        try:
            n = float(v)
        except (TypeError, ValueError):
            continue
        if best is None or n > best:
            best = n
    return best


def col_for_sub(group_labels, sub_labels, group_start_col, want_sub):
    if group_start_col is None:
        return None
    target_label = group_labels[group_start_col]
    cols = [ci for ci, lbl in group_labels.items() if lbl == target_label]
    for ci in cols:
        if (sub_labels.get(ci) or '').strip().lower() == want_sub:
            return ci
    return cols[-1] if cols else None


def find_label_value(values, label_keys, max_row=25, max_scan=8):
    """Cari sel yang mengandung salah satu label (mis. 'nama kapal'), lalu ambil
    sel non-kosong pertama di sebelah kanannya (skip tanda ':').

    Sel angka dibulatkan dulu kalau isinya bilangan bulat. Tahun docking di berkas ini
    tersimpan sebagai angka, jadi tanpa pembulatan `str(2026.0)` -> "2026.0", dan nilai
    itu mengisi kolom Tahun di form impor (DockingImportPanel) lalu ikut jadi prefix ID
    baris: KMP._MISHIMA-2026.0-001. Sama persis dengan yang terjadi di
    `catalog.parse_spreadsheet`, cuma di sini sumbernya openpyxl/xlrd, bukan pandas.
    """
    for row in values[:max_row]:
        for ci, cell in enumerate(row):
            if cell is None:
                continue
            cell_norm = norm_nospace(cell)
            if any(key in cell_norm for key in label_keys):
                for cj in range(ci + 1, min(ci + max_scan, len(row))):
                    v = row[cj]
                    if v is not None and str(v).strip() not in (':', ''):
                        if isinstance(v, float) and float(v).is_integer():
                            v = int(v)
                        return str(v).strip()
    return ""


# Awalan nama kapal Indonesia. Dipakai kalau berkasnya tidak punya label "NAMA KAPAL"
# sama sekali -- berkas "Lampiran Perjanjian" menaruh namanya di baris `Lokasi`, dan tanpa
# ini seluruh berkas terbaca tanpa kapal lalu barisnya tidak bisa disimpan.
KAPAL_RE = re.compile(
    r"(?<![A-Za-z])((?:KMP|KLM|LCT|MV|MT|TB|KM|KN)\.?\s*[A-Z][A-Za-z0-9.' -]{2,40})"
)
# Nama kapal di baris `Lokasi` biasanya diikuti keterangan tempat: "KMP. Marina Segunda di
# galangan ...". Potong di kata sambungnya, bukan di panjang tetap.
_EKOR_KAPAL = re.compile(r"\s+(?:di|pada|dalam|tahun|thn|milik)(?:\s.*)?$", re.IGNORECASE)


def _bersihkan_nama_kapal(teks: str) -> str:
    teks = _EKOR_KAPAL.sub("", str(teks)).strip(" .,-")
    return re.sub(r"\s+", " ", teks)


def tebak_nama_kapal(values, sheet_name: str, filename: str) -> str:
    """Nama kapal, dicari berlapis dari yang paling dapat dipercaya.

    Label "NAMA KAPAL" dulu; kalau tidak ada, pola nama kapal di kepala berkas; baru
    nama sheet dan nama berkas. Semuanya tetap ditampilkan di layar pratinjau untuk
    diperiksa manusia sebelum disimpan -- ini menebak, dan menebak boleh salah.
    """
    nama = find_label_value(values, ['namakapal'])
    if nama:
        return nama
    for row in values[:20]:
        for cell in row:
            if cell is None:
                continue
            m = KAPAL_RE.search(str(cell))
            if m:
                return _bersihkan_nama_kapal(m.group(1))
    for teks in (sheet_name or "", filename or ""):
        m = KAPAL_RE.search(teks)
        if m:
            return _bersihkan_nama_kapal(m.group(1))
    return ""


def _tahun_sebaris(values, label_keys, max_row=25) -> str:
    """Tahun empat digit di baris yang memuat salah satu label, di sel mana pun."""
    for row in values[:max_row]:
        if not any(
            c is not None and any(k in norm_nospace(c) for k in label_keys) for c in row
        ):
            continue
        for cell in row:
            if cell is None:
                continue
            nilai = int(cell) if isinstance(cell, float) and float(cell).is_integer() else cell
            m = YEAR_RE.search(str(nilai))
            if m:
                return m.group(1)
    return ""


def guess_header(values, filename, sheet_name=""):
    nama_kapal = tebak_nama_kapal(values, sheet_name, filename)
    nama_perusahaan = find_label_value(values, ['pemilik'])
    tahun = find_label_value(values, ['periodedocking', 'dockingtahun', 'tahundocking'])
    # "PERIODE DOCKING : Nopember 2025" kadang ditulis di DUA sel terpisah, dan sel pertama
    # cuma berisi bulannya. Kalau nilai yang terambil tidak memuat tahun sama sekali,
    # sisir sisa baris itu -- angkanya biasanya menempel di sel sebelahnya.
    if tahun and not YEAR_RE.search(tahun):
        sebaris = _tahun_sebaris(values, ['periodedocking', 'dockingtahun', 'tahundocking'])
        tahun = sebaris or tahun
    if not tahun:
        # Berkas perjanjian tidak menyebut periode docking, tapi menyebut tanggal
        # perjanjiannya. Itu lebih dekat ke waktu pekerjaan daripada tahun di nama berkas,
        # yang cuma tahun terbit dokumen.
        tanggal = find_label_value(values, ['tanggal'])
        m = YEAR_RE.search(tanggal or "")
        if m:
            tahun = m.group(1)
    if not tahun:
        m = YEAR_RE.search(sheet_name or "") or YEAR_RE.search(filename)
        if m:
            tahun = m.group(1)
    return nama_kapal, nama_perusahaan, tahun


def parse_sheet(values, sheet_name):
    header_idx = find_header_idx(values)
    if header_idx is None:
        return [], [], [f"Header tabel item tidak ditemukan di sheet '{sheet_name}'"]

    header_row = values[header_idx]
    sub_row = values[header_idx + 1] if header_idx + 1 < len(values) else []
    group_labels = build_group_labels(header_row)
    sub_labels = {ci: (str(v).strip() if v else None) for ci, v in enumerate(sub_row)}

    uraian_col = next(
        (c for u in JUDUL_URAIAN if (c := find_group_start(group_labels, [u])) is not None), None
    )
    if uraian_col is None:
        uraian_col = 1

    volume_col = find_group_start(group_labels, ['volume'])
    if volume_col is None:
        volume_col = find_group_start(group_labels, ['qty'])
    keterangan_col = find_group_start(group_labels, ['keterangan'])

    # Template laporan tidak sepakat menamai kolom harga pokoknya. Yang lazim "HARGA (Rp.)",
    # tapi laporan realisasi (mis. LCT. ARJHUNA 2025) memakai "INDUK (Rp.)" berdampingan
    # dengan BATAL / TAMBAHAN / REALISASI. Tanpa alternatif ini, kolom harganya tidak
    # ketemu sama sekali dan berkasnya terbaca nol baris -- gagal tanpa suara.
    harga_utama_start = None
    for kata in (['harga'], ['induk']):
        harga_utama_start = find_harga_group_start(
            group_labels, kata,
            must_not_have=['batal', 'tambahan', 'realisasi'],
            after=volume_col or uraian_col,
        )
        if harga_utama_start is not None:
            break
    tambahan_start = find_harga_group_start(group_labels, ['tambahan'])

    harga_utama_satuan_col = col_for_sub(group_labels, sub_labels, harga_utama_start, 'satuan')
    harga_utama_jumlah_col = col_for_sub(group_labels, sub_labels, harga_utama_start, 'jumlah')
    harga_tambahan_satuan_col = col_for_sub(group_labels, sub_labels, tambahan_start, 'satuan')
    harga_tambahan_jumlah_col = col_for_sub(group_labels, sub_labels, tambahan_start, 'jumlah')

    if volume_col is not None and group_labels.get(volume_col, '').strip().lower() == 'qty':
        qty_col = volume_col
        _, next_boundary = group_range(group_labels, volume_col)
        sat_col = next_boundary if group_labels.get(next_boundary, '').lower().startswith('sat') else None
    else:
        qty_col = col_for_sub(group_labels, sub_labels, volume_col, 'qty')
        sat_col = col_for_sub(group_labels, sub_labels, volume_col, 'sat')

    data_start = header_idx + 2
    end_col = volume_col if volume_col is not None else len(header_row)

    induk, addendum, warnings = [], [], []
    current_category = None
    # Rantai baris induk yang sedang berlaku, dikunci per kedalaman. Lihat _kedalaman_kolom().
    induk_konteks: dict[int, str] = {}
    seen_uraian_price_rows = {}

    for ri in range(data_start, len(values)):
        row = values[ri]
        if not any(c is not None for c in row):
            continue
        col_a = row[0]
        col_a_str = str(col_a).strip() if col_a is not None else ""

        if col_a_str and is_roman(col_a_str):
            cat_text = str(row[uraian_col]).strip() if len(row) > uraian_col and row[uraian_col] else ""
            cat_text = strip_roman_prefix(cat_text) or cat_text
            current_category = cat_text or current_category
            induk_konteks = {}
            continue

        first_text = None
        for ci in range(0, min(uraian_col + 1, len(row))):
            if row[ci] is not None and str(row[ci]).strip():
                first_text = norm(row[ci])
                break
        if first_text and (first_text in NOISE_EXACT or any(first_text.startswith(k) for k in NOISE_EXACT)):
            continue

        # Kolom mana saja yang benar-benar berisi teks. Penanda '-' sengaja dilewati --
        # di berkas ini tanda hubung menempati SEL TERSENDIRI di kolom sebelum teksnya,
        # jadi dia bagian dari tata letak, bukan bagian dari uraian.
        kolom_isi = [
            ci for ci in range(uraian_col, end_col)
            if ci < len(row) and row[ci] is not None and str(row[ci]).strip() not in ('', '-')
        ]
        uraian_text = ' '.join(str(row[ci]).strip() for ci in kolom_isi).strip()
        if not uraian_text:
            continue

        # Kedalaman baris dibaca dari KOLOM tempat teksnya mulai, bukan dari tanda baca.
        # Berkas docking menggeser teks satu kolom ke kanan tiap turun satu tingkat:
        #
        #     kol 1: Pipa isap BBM (material pipa Blacksteel sch 40)
        #     kol 1: '-'   kol 2: Pipa Sch. 40 uk 1,5"
        #     kol 1: '-'   kol 2: Elbow
        #
        # Tanpa ini, "Elbow" tersimpan tanpa jejak apa pun bahwa dia bagian dari pipa isap
        # BBM di kamar mesin kanan. Di KMP. GILIMANUK 2026 ada 15 baris berbunyi persis
        # "Elbow" dengan harga Rp 300.000 sampai Rp 2.100.000, dan katalog tidak punya cara
        # membedakannya.
        kedalaman = kolom_isi[0] * 2 + (0 if col_a_str else 1)
        for lebih_dalam in [k for k in induk_konteks if k >= kedalaman]:
            del induk_konteks[lebih_dalam]
        rantai_induk = PEMISAH_INDUK.join(induk_konteks[k] for k in sorted(induk_konteks))
        induk_konteks[kedalaman] = uraian_text

        def get_num(ci):
            if ci is None or ci >= len(row):
                return None
            v = row[ci]
            if v is None or (isinstance(v, str) and v.strip() in ('', '-')):
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        qty_numeric = get_num(qty_col)

        def unit_price(satuan_col, jumlah_col):
            sat = get_num(satuan_col)
            if sat and sat > 0:
                return sat
            jml = get_num(jumlah_col)
            if jml and jml > 0:
                if qty_numeric and qty_numeric > 0:
                    return jml / qty_numeric
                return jml
            return None

        harga_utama_val = unit_price(harga_utama_satuan_col, harga_utama_jumlah_col)
        harga_tambahan_val = unit_price(harga_tambahan_satuan_col, harga_tambahan_jumlah_col)
        sat_val = row[sat_col] if sat_col is not None and sat_col < len(row) else None
        volume_satuan = str(sat_val).strip() if sat_val is not None and str(sat_val).strip() else "-"

        keterangan_val = ""
        if keterangan_col is not None and keterangan_col < len(row) and row[keterangan_col]:
            keterangan_val = str(row[keterangan_col]).strip()

        is_tambahan = 'tambahan' in keterangan_val.lower()

        item = {
            'row': ri + 1,
            'kategori': current_category,
            'uraian': uraian_text,
            'volume_satuan': volume_satuan,
            'keterangan': keterangan_val,
            # Qty-nya SUDAH dibaca di atas -- selama ini cuma dipakai membagi kolom Jumlah
            # jadi harga satuan, lalu dibuang. Sejak ada kolom `volume`, angkanya ikut
            # disimpan: tanpa dia, "berapa nilai pekerjaan pengecatan untuk kapal ini"
            # tidak bisa dijawab, dan membandingkan harga antar kapal jadi menyesatkan --
            # Rp 200.000/m2 di kapal yang 269 m2 dan yang 230 m2 terlihat sama persis.
            # Diverifikasi di dua berkas docking yang ada di repo: 414 baris punya Qty
            # DAN kolom Jumlah, dan qty x harga = Jumlah di keempat-ratus-empat-belasnya.
            'induk_uraian': rantai_induk or None,
            'volume': qty_numeric,
            # `volume_satuan` memang sudah berisi satuannya saja ("Ls", "Hari", "Kali") --
            # bukan "269 m2" seperti yang sering diduga; kuantitasnya tidak pernah ikut
            # tersimpan sama sekali. Kolom baru ini kembarannya yang memakai NULL, bukan
            # "-", supaya kolom baru cuma punya satu cara mengatakan "tidak tahu".
            'satuan': volume_satuan if volume_satuan != "-" else None,
        }

        if is_tambahan:
            if harga_tambahan_val and harga_tambahan_val > 0:
                item['harga'] = harga_tambahan_val
                addendum.append(item)
            elif harga_utama_val and harga_utama_val > 0:
                item['harga'] = harga_utama_val
                warnings.append(
                    f"Baris {ri+1}: keterangan 'tambahan' tapi harga cuma ada di kolom Harga Utama "
                    f"- masuk Addendum pakai harga utama, cek manual"
                )
                addendum.append(item)
        else:
            if harga_utama_val and harga_utama_val > 0:
                item['harga'] = harga_utama_val
                induk.append(item)
                seen_uraian_price_rows.setdefault(uraian_text, []).append(ri + 1)

    for uraian_text, rows_ in seen_uraian_price_rows.items():
        if len(rows_) > 1:
            warnings.append(
                f"Uraian '{uraian_text[:60]}' punya harga valid di lebih dari 1 baris: {rows_} "
                f"- cek manual, mungkin duplikat/baris lanjutan"
            )

    return induk, addendum, warnings


def _load_values(file_bytes: bytes, filename: str):
    name = filename.lower()
    if name.endswith('.xls'):
        import xlrd
        wb = xlrd.open_workbook(file_contents=file_bytes)
        sheetname = wb.sheet_names()[-1]
        sheet = wb.sheet_by_name(sheetname)
        values = [sheet.row_values(r) for r in range(min(sheet.nrows, 5000))]
        values = [[(c if c != '' else None) for c in row] for row in values]
        return values, sheetname
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
    sheetname = wb.sheetnames[-1]
    ws = wb[sheetname]
    values = list(ws.iter_rows(min_row=1, max_row=5000, max_col=40, values_only=True))
    return values, sheetname


def parse_docking_file(file_bytes: bytes, filename: str) -> dict:
    values, sheetname = _load_values(file_bytes, filename)
    induk, addendum, warnings = parse_sheet(values, sheetname)
    nama_kapal, nama_perusahaan, tahun = guess_header(values, filename, sheetname)
    return {
        "sheet_name": sheetname,
        "detected_nama_kapal": nama_kapal,
        "detected_nama_perusahaan": nama_perusahaan,
        "detected_tahun": tahun,
        "induk": induk,
        "addendum": addendum,
        "warnings": warnings,
    }
