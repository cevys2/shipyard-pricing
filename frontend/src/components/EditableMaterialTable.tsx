import { lazy, Suspense, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, ClipboardPaste, Copy, LineChart, Pencil, Plus, Save, Trash2, X } from "lucide-react";
import {
  api,
  formatMoney,
  labelTahun,
  pakaiKolomPembelian,
  pakaiSpesifikasi,
  DASAR_PENETAPAN,
  JENIS_DOKUMEN_BELI,
  type Currency,
  type JenisSumberDaya,
  type MaterialItemInput,
  type MaterialRow,
  type PastePreview,
  type PastePreviewRow,
} from "../lib/api";
import { angkaTempel, parseTsv } from "../lib/tsv";
import NumberInput from "./NumberInput";
import MaterialGridForm from "./MaterialGridForm";
// Ikut di-lazy bareng tab Analitik -- drawer ini juga pakai recharts dan cuma tampil
// setelah user klik "Riwayat".
const PriceHistoryDrawer = lazy(() => import("./PriceHistoryDrawer"));

const PAGE_SIZE = 50;

type Props = {
  token: string;
  jenis: JenisSumberDaya;
  rows: MaterialRow[];
  loading: boolean;
  onChanged: () => void; // call after any successful save/delete/add to refresh parent data
};

const CURRENCIES: Currency[] = ["IDR", "EUR", "USD"];
const CURRENT_YEAR = new Date().getFullYear();

/** Susunan kolom paste/edit massal, diturunkan dari jenisnya. Kolom yang tidak berlaku
 * benar-benar hilang dari susunan -- bukan cuma disembunyikan tampilannya -- supaya orang
 * tidak perlu menyisipkan kolom kosong di Excel sebelum menempel.
 *
 * `cellsToDraft()` membaca susunan yang SAMA, jadi menambah atau membuang kolom di sini
 * otomatis ikut menggeser pembacaan tempelan. Tidak ada lagi indeks yang dihitung tangan. */
function kolomOrder(jenis: JenisSumberDaya): (keyof MaterialItemInput)[] {
  const k: (keyof MaterialItemInput)[] = ["nama"];
  if (pakaiSpesifikasi(jenis)) k.push("spesifikasi");
  k.push("satuan", "harga_satuan", "mata_uang", "tahun_pembelian");
  if (pakaiKolomPembelian(jenis)) k.push("supplier_nama", "nama_kapal");
  k.push("berlaku_dari");
  return k;
}

function kolomLabel(jenis: JenisSumberDaya): string[] {
  const l = ["Nama"];
  if (pakaiSpesifikasi(jenis)) l.push("Spesifikasi");
  l.push("Satuan", "Harga", "Mata Uang", labelTahun(jenis));
  if (pakaiKolomPembelian(jenis)) l.push("Supplier", "Kapal");
  l.push("Berlaku Dari");
  return l;
}

/** Kata yang dipakai di pesan ke pengguna. "Hapus 3 material terpilih" salah kalau yang
 * dihapus baris tarif tukang. */
const ISTILAH: Record<JenisSumberDaya, string> = {
  BAHAN: "material",
  UPAH: "tarif upah",
  ALAT: "tarif alat",
  KONSUMABEL: "konsumabel",
};

const emptyDraft: MaterialItemInput = {
  nama: "",
  spesifikasi: "",
  satuan: "",
  harga_satuan: 0,
  mata_uang: "IDR",
  tahun_pembelian: CURRENT_YEAR,
  supplier_nama: "",
  nama_kapal: "",
  berlaku_dari: "",
  sumber: "",
  no_dokumen: "",
  catatan: "",
};

function normalizeCurrency(raw: string): Currency {
  const upper = raw.trim().toUpperCase();
  return (CURRENCIES as string[]).includes(upper) ? (upper as Currency) : "IDR";
}

// Kalau orang natural nulis harga "EUR 45.10" dalam SATU sel (bukan misahin Harga |
// Mata Uang ke 2 kolom kayak yang kita minta), kolom-kolom sesudahnya bakal geser semua
// kalau dipaksa parse 9-kolom kaku. Deteksi pola ini dan toleransi -- anggap Mata Uang
// udah ke-cover di sel yang sama, jadi sisa kolom dihitung sebagai 8-kolom.
const INLINE_CURRENCY_RE = /^(IDR|EUR|USD)\s*([\d.,]+)$/i;

function cellsToDraft(cells: string[], jenis: JenisSumberDaya = "BAHAN"): MaterialItemInput {
  const d: MaterialItemInput = { ...emptyDraft, berlaku_dari: null };
  let i = 0;
  let mataUangIkutHarga = false;

  for (const kolom of kolomOrder(jenis)) {
    // Kalau mata uang digabung di sel harga ("EUR 45.10"), kolom Mata Uang tidak memakan
    // sel sendiri -- jadi penunjuk selnya sengaja tidak maju di sini.
    if (kolom === "mata_uang" && mataUangIkutHarga) continue;
    const sel = (cells[i] ?? "").trim();
    i++;

    switch (kolom) {
      case "harga_satuan": {
        const cocok = sel.match(INLINE_CURRENCY_RE);
        if (cocok) {
          mataUangIkutHarga = true;
          d.mata_uang = normalizeCurrency(cocok[1]);
          d.harga_satuan = angkaTempel(cocok[2]).nilai;
        } else {
          d.harga_satuan = angkaTempel(sel).nilai;
        }
        break;
      }
      case "mata_uang":
        d.mata_uang = normalizeCurrency(sel);
        break;
      case "tahun_pembelian":
        // Sengaja TIDAK di-default diam-diam ke tahun sekarang kalau kosong/invalid --
        // itu masalah yang sama kayak dibuat_pada yang mau dihindari (data lama/backfill
        // kepaksa dapet tahun yang salah tanpa ketauan). Baris nol/invalid ditolak &
        // di-warning di parsePasteFull.
        d.tahun_pembelian = Number(sel.replace(/[^\d]/g, "")) || 0;
        break;
      case "berlaku_dari":
        d.berlaku_dari = sel || null;
        break;
      default:
        d[kolom] = sel as never;
    }
  }
  return d;
}

function draftToRow(d: MaterialItemInput, jenis: JenisSumberDaya): string[] {
  return kolomOrder(jenis).map((k) => String(d[k] ?? ""));
}

export default function EditableMaterialTable({ token, jenis, rows, loading, onChanged }: Props) {
  const adaPembelian = pakaiKolomPembelian(jenis);
  const adaSpesifikasi = pakaiSpesifikasi(jenis);
  const COLUMN_ORDER = useMemo(() => kolomOrder(jenis), [jenis]);
  const COLUMN_LABELS = useMemo(() => kolomLabel(jenis), [jenis]);

  const [historyFor, setHistoryFor] = useState<MaterialRow | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState<MaterialItemInput>(emptyDraft);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const [showAdd, setShowAdd] = useState(false);
  const [pasteText, setPasteText] = useState("");
  const [pastePreview, setPastePreview] = useState<MaterialItemInput[]>([]);
  const [pasteWarnings, setPasteWarnings] = useState<string[]>([]);
  const [dampak, setDampak] = useState<PastePreview | null>(null);
  const [cekBusy, setCekBusy] = useState(false);
  const [showGrid, setShowGrid] = useState(false);
  const [pasteSumber, setPasteSumber] = useState(
    pakaiKolomPembelian(jenis) ? "Quotation" : "SK Manajemen",
  );
  const [pasteNoDok, setPasteNoDok] = useState("");

  const [bulkEditOpen, setBulkEditOpen] = useState(false);
  const [bulkEditRows, setBulkEditRows] = useState<{ id: number; data: MaterialItemInput }[]>([]);

  const [page, setPage] = useState(0);
  const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const pagedRows = useMemo(
    () => rows.slice(currentPage * PAGE_SIZE, currentPage * PAGE_SIZE + PAGE_SIZE),
    [rows, currentPage],
  );
  const pageIds = useMemo(() => pagedRows.map((r) => r.id), [pagedRows]);
  const allIds = useMemo(() => rows.map((r) => r.id), [rows]);
  const allFilteredSelected = allIds.length > 0 && allIds.every((id) => selected.has(id));
  const somePageSelected = pageIds.length > 0 && pageIds.some((id) => selected.has(id));

  function toggleSelectAllFiltered() {
    setSelected(allFilteredSelected ? new Set() : new Set(allIds));
  }

  function startEdit(row: MaterialRow) {
    setEditingId(row.id);
    setDraft({
      nama: row.nama,
      spesifikasi: row.spesifikasi,
      satuan: row.satuan,
      harga_satuan: row.harga_satuan ?? 0,
      mata_uang: normalizeCurrency(row.mata_uang ?? "IDR"),
      tahun_pembelian: row.tahun_pembelian ?? CURRENT_YEAR,
      supplier_nama: row.supplier_nama ?? "",
      nama_kapal: row.nama_kapal ?? "",
      berlaku_dari: row.berlaku_dari,
      sumber: "",
      no_dokumen: "",
      catatan: "",
    });
    setError("");
  }

  function cancelEdit() {
    setEditingId(null);
    setError("");
  }

  async function saveEdit() {
    if (!editingId) return;
    setBusy(true);
    setError("");
    try {
      await api.materialPatch(token, { updates: [{ id: editingId, data: draft }] });
      setEditingId(null);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal menyimpan perubahan");
    } finally {
      setBusy(false);
    }
  }

  function toggleSelect(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function deleteSelected() {
    if (selected.size === 0) return;
    if (!confirm(`Hapus ${selected.size} ${ISTILAH[jenis]} terpilih? Tindakan ini tidak bisa dibatalkan.`)) return;
    setBusy(true);
    setError("");
    try {
      await api.materialPatch(token, { delete_ids: Array.from(selected) });
      setSelected(new Set());
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal menghapus material");
    } finally {
      setBusy(false);
    }
  }

  // ---- paste-from-Excel bulk add: 9 kolom (Harga & Mata Uang boleh digabung 1 sel, mis. "EUR 45.10") ----
  function parsePasteFull() {
    setError("");
    const parsedRows = parseTsv(pasteText);
    const warnings: string[] = [];
    const drafts: MaterialItemInput[] = [];
    parsedRows.forEach((cells, i) => {
      // Satu paste = satu dokumen. Nomor quotation/PO ditanyakan sekali di atas, bukan
      // diulang di tiap baris -- itu sifat dokumennya, bukan sifat tiap barang. Sebelum ini
      // kolom paste tidak punya tempat untuk nomor dokumen sama sekali, sehingga asal-usul
      // 29 dari 46 titik harga di produksi tidak tercatat.
      const d = {
        ...cellsToDraft(cells, jenis),
        sumber: pasteSumber,
        no_dokumen: pasteNoDok.trim(),
      };
      if (!d.nama || !d.satuan || d.harga_satuan <= 0) {
        warnings.push(`Baris ${i + 1}: Nama/Satuan/Harga wajib diisi (harga > 0), dilewati`);
        return;
      }
      if (d.tahun_pembelian < 1990 || d.tahun_pembelian > 2100) {
        warnings.push(
          `Baris ${i + 1}: ${labelTahun(jenis)} tidak valid, dilewati -- cek urutan kolomnya (Harga dan Mata Uang ` +
            `boleh digabung 1 sel spt "EUR 45.10", tapi kalau dipisah harus tetap 2 kolom terpisah)`,
        );
        return;
      }
      drafts.push(d);
    });
    setPastePreview(drafts);
    setPasteWarnings(warnings);
    setDampak(null);
    if (drafts.length > 0) void cekDampak(drafts);
  }

  /** Tanya backend apa yang akan terjadi sebelum apa pun disimpan.
   *
   * Sebelum ini antarmuka diam soal itu, sehingga orang yang teliti menyangka aplikasinya
   * akan bikin material kembar lalu memilih memasukkan datanya manual satu per satu --
   * padahal titik harga baru untuk part number yang sudah ada memang sudah ditangani.
   * Endpoint pratinjaunya memakai fungsi keputusan yang sama dengan jalur simpan. */
  async function cekDampak(drafts: MaterialItemInput[]) {
    setCekBusy(true);
    try {
      setDampak(await api.materialBulkPreview(token, drafts, jenis));
    } catch (e) {
      // Pratinjau gagal bukan alasan memblokir penyimpanan -- yang menentukan tetap backend
      // saat simpan. Cukup beri tahu bahwa ringkasannya tidak tersedia.
      setDampak(null);
      setError(
        (e instanceof Error ? e.message : "Pratinjau gagal") +
          " — ringkasan dampak tidak tersedia, penyimpanan tetap bisa dilanjutkan.",
      );
    } finally {
      setCekBusy(false);
    }
  }

  /** Pratinjau paste dulu cuma bisa dibaca, jadi satu sel yang meleset memaksa mengulang
   * paste dari Excel. Sekarang bisa dibetulkan di tempat. Tiap perubahan membatalkan
   * ringkasan dampak yang lama supaya tidak menampilkan kesimpulan dari data usang. */
  function ubahBarisPaste(idx: number, field: keyof MaterialItemInput, nilai: unknown) {
    setPastePreview((rows2) =>
      rows2.map((r, i) => (i === idx ? { ...r, [field]: nilai } : r)),
    );
    setDampak(null);
  }

  /** Supplier, kapal, tanggal, dan tahun biasanya sama untuk seluruh isi satu quotation --
   * membetulkannya sekali lalu menurunkannya jauh lebih cepat daripada 25 kali. */
  function isiKeBawahPaste(idx: number, field: keyof MaterialItemInput) {
    setPastePreview((rows2) =>
      rows2.map((r, i) => (i > idx ? { ...r, [field]: rows2[idx][field] } : r)),
    );
    setDampak(null);
  }

  function duplikatBarisPaste(idx: number) {
    setPastePreview((rows2) => [
      ...rows2.slice(0, idx + 1),
      { ...rows2[idx] },
      ...rows2.slice(idx + 1),
    ]);
    setDampak(null);
  }

  function removePasteRow(idx: number) {
    setPastePreview((rows2) => {
      const next = rows2.filter((_, i) => i !== idx);
      setDampak(null);
      if (next.length > 0) void cekDampak(next);
      return next;
    });
  }

  async function submitPasteAdd() {
    if (pastePreview.length === 0) return;
    setBusy(true);
    setError("");
    try {
      const res = await api.materialBulkCreate(token, pastePreview, jenis);
      setPasteText("");
      setPastePreview([]);
      setPasteWarnings([]);
      setDampak(null);
      setShowAdd(false);
      onChanged();
      alert(
        res.dilewati > 0
          ? `Tersimpan ${res.saved} titik harga. ${res.dilewati} baris dilewati karena ` +
            `harganya sudah persis sama dengan yang tercatat (bukan perubahan harga).`
          : `Berhasil menambah ${res.saved} titik harga.`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal menyimpan material hasil paste");
    } finally {
      setBusy(false);
    }
  }

  // ---- single-row add form ----
  const [addDraft, setAddDraft] = useState<MaterialItemInput>(emptyDraft);

  async function submitAdd() {
    if (!addDraft.nama.trim() || !addDraft.satuan.trim() || addDraft.harga_satuan <= 0) {
      setError("Nama, Satuan, dan Harga (> 0) wajib diisi");
      return;
    }
    if (addDraft.tahun_pembelian < 1990 || addDraft.tahun_pembelian > 2100) {
      setError(`${labelTahun(jenis)} tidak valid`);
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api.materialBulkCreate(token, [addDraft], jenis);
      setAddDraft(emptyDraft);
      setShowAdd(false);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal menambah material");
    } finally {
      setBusy(false);
    }
  }

  // ---- bulk edit selected rows ----
  function openBulkEdit() {
    const chosen = rows.filter((r) => selected.has(r.id));
    setBulkEditRows(
      chosen.map((r) => ({
        id: r.id,
        data: {
          nama: r.nama,
          spesifikasi: r.spesifikasi,
          satuan: r.satuan,
          harga_satuan: r.harga_satuan ?? 0,
          mata_uang: normalizeCurrency(r.mata_uang ?? "IDR"),
          tahun_pembelian: r.tahun_pembelian ?? CURRENT_YEAR,
          supplier_nama: r.supplier_nama ?? "",
          nama_kapal: r.nama_kapal ?? "",
          berlaku_dari: r.berlaku_dari,
          sumber: "",
          no_dokumen: "",
          catatan: "",
        },
      })),
    );
    setBulkEditOpen(true);
    setError("");
  }

  function copyBulkEditToClipboard() {
    const tsv = bulkEditRows.map((r) => draftToRow(r.data, jenis).join("\t")).join("\n");
    navigator.clipboard.writeText(tsv).catch(() => setError("Gagal menyalin ke clipboard"));
  }

  function pasteBulkEditFromText(text: string) {
    const parsedRows = parseTsv(text);
    setBulkEditRows((prev) =>
      prev.map((r, i) =>
        parsedRows[i] ? { id: r.id, data: cellsToDraft(parsedRows[i], jenis) } : r,
      ),
    );
  }

  function updateBulkEditCell(rowIdx: number, field: keyof MaterialItemInput, value: string | number) {
    setBulkEditRows((prev) => prev.map((r, i) => (i === rowIdx ? { ...r, data: { ...r.data, [field]: value } } : r)));
  }

  async function submitBulkEdit() {
    setBusy(true);
    setError("");
    try {
      await api.materialPatch(token, { updates: bulkEditRows });
      setBulkEditOpen(false);
      setSelected(new Set());
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal menyimpan perubahan massal");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => {
            setEditMode((m) => !m);
            setEditingId(null);
            setSelected(new Set());
            setBulkEditOpen(false);
            setError("");
          }}
          className={`btn btn-md ${editMode ? "btn-primary" : "btn-secondary"}`}
        >
          <Pencil size={14} />
          {editMode ? "Selesai Edit" : "Mode Edit"}
        </button>
        {editMode && (
          <>
            <button
              type="button"
              onClick={() => {
                setShowGrid((s) => !s);
                setShowAdd(false);
                setBulkEditOpen(false);
              }}
              className="btn btn-primary btn-md"
            >
              <Plus size={14} />
              Input Beberapa Baris
            </button>
            <button
              type="button"
              onClick={() => {
                setShowAdd((s) => !s);
                setShowGrid(false);
                setBulkEditOpen(false);
              }}
              className="btn btn-secondary btn-md"
            >
              <ClipboardPaste size={14} />
              Paste / 1 Baris
            </button>
            <button
              type="button"
              disabled={selected.size === 0 || busy}
              onClick={openBulkEdit}
              className="btn btn-accent btn-md"
            >
              <ClipboardPaste size={14} />
              Edit Massal ({selected.size})
            </button>
            <button
              type="button"
              disabled={selected.size === 0 || busy}
              onClick={deleteSelected}
              className="btn btn-danger-solid btn-md"
            >
              <Trash2 size={14} />
              {busy ? "Menghapus..." : `Hapus Terpilih (${selected.size})`}
            </button>
          </>
        )}
      </div>

      {error && <p className="mb-3 text-sm text-red-600">{error}</p>}

      {editMode && showGrid && (
        <MaterialGridForm
          token={token}
          jenis={jenis}
          onSaved={onChanged}
          onClose={() => setShowGrid(false)}
        />
      )}

      {editMode && showAdd && (
        <div className="mb-4 rounded-xl border border-blue-200 bg-blue-50 p-4">
          <p className="mb-3 text-xs font-bold text-slate-700">1 Baris Manual</p>
          <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
            <LabeledInput label="Nama *" value={addDraft.nama} onChange={(v) => setAddDraft((d) => ({ ...d, nama: v }))} />
            {adaSpesifikasi && (
              <LabeledInput label="Spesifikasi" value={addDraft.spesifikasi} onChange={(v) => setAddDraft((d) => ({ ...d, spesifikasi: v }))} />
            )}
            <LabeledInput label="Satuan *" value={addDraft.satuan} onChange={(v) => setAddDraft((d) => ({ ...d, satuan: v }))} />
            <label className="block text-xs font-medium text-slate-600">
              Harga *
              <NumberInput
                className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm"
                value={addDraft.harga_satuan}
                onChange={(n) => setAddDraft((d) => ({ ...d, harga_satuan: n }))}
              />
            </label>
            <label className="block text-xs font-medium text-slate-600">
              Mata Uang
              <select
                className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm"
                value={addDraft.mata_uang}
                onChange={(e) => setAddDraft((d) => ({ ...d, mata_uang: e.target.value as Currency }))}
              >
                {CURRENCIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-xs font-medium text-slate-600">
              {labelTahun(jenis)} *
              <NumberInput
                integer
                className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm"
                value={addDraft.tahun_pembelian}
                onChange={(n) => setAddDraft((d) => ({ ...d, tahun_pembelian: n }))}
              />
            </label>
            {adaPembelian && (
              <>
                <LabeledInput label="Supplier" value={addDraft.supplier_nama} onChange={(v) => setAddDraft((d) => ({ ...d, supplier_nama: v }))} />
                <LabeledInput label="Kapal" value={addDraft.nama_kapal} onChange={(v) => setAddDraft((d) => ({ ...d, nama_kapal: v }))} />
              </>
            )}
            <LabeledInput
              label="Berlaku Dari"
              type="date"
              value={addDraft.berlaku_dari ?? ""}
              onChange={(v) => setAddDraft((d) => ({ ...d, berlaku_dari: v || null }))}
            />
          </div>
          <div className="mt-3 flex gap-2">
            <button type="button" disabled={busy} onClick={submitAdd} className="btn btn-primary btn-md">
              <Save size={13} />
              {busy ? "Menyimpan..." : "Simpan Material"}
            </button>
            <button
              type="button"
              onClick={() => {
                setShowAdd(false);
                setAddDraft(emptyDraft);
              }}
              className="btn btn-secondary btn-md"
            >
              Batal
            </button>
          </div>

          <div className="my-4 border-t border-blue-200" />

          <p className="mb-2 text-xs font-bold text-slate-700">Tempel dari Excel (banyak baris sekaligus)</p>
          <p className="mb-2 text-xs text-slate-600">
            Urutkan kolom di Excel: <strong>{COLUMN_LABELS.join(" | ")}</strong>{" "}
            ({adaSpesifikasi ? "Spesifikasi/" : ""}Mata Uang/{adaPembelian ? "Supplier/Kapal/" : ""}Berlaku Dari boleh kosong -- Mata Uang
            kosong/tidak dikenali otomatis jadi IDR. Boleh juga gabung Harga+Mata Uang dalam 1 sel, mis.{" "}
            <strong>"EUR 45.10"</strong> -- kolom Mata Uang terpisah nggak usah diisi kalau begini. Tahun Pembelian
            WAJIB diisi angka tahun yang valid -- ini acuan analitik, jadi sengaja nggak di-tebak otomatis kayak
            dibuat_pada). Select semua sel, Ctrl+C, lalu paste di kotak bawah.
            {!adaPembelian && (
              <>
                {" "}
                <strong>Tanpa kolom Supplier dan Kapal</strong> -- tarif {jenis === "UPAH" ? "tenaga kerja" : "alat"}{" "}
                milik sendiri tidak dibeli dari supplier.
              </>
            )}
          </p>
          <div className="mb-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <label className="block text-xs font-medium text-slate-600">
              {adaPembelian ? "Jenis Dokumen" : "Dasar Penetapan"}
              <select
                className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm"
                value={pasteSumber}
                onChange={(e) => setPasteSumber(e.target.value)}
              >
                {(adaPembelian ? JENIS_DOKUMEN_BELI : DASAR_PENETAPAN).map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-xs font-medium text-slate-600 sm:col-span-2">
              {adaPembelian ? "Nomor Dokumen" : "Nomor SK / Memo"}
              <input
                className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm"
                placeholder={adaPembelian ? "mis. 2410-1547/MAN-SQ" : "mis. SK-012/DR/2026"}
                value={pasteNoDok}
                onChange={(e) => setPasteNoDok(e.target.value)}
              />
            </label>
          </div>
          <p className="mb-2 text-xs text-slate-500">
            Dua isian di atas berlaku untuk seluruh baris paste ini, karena satu quotation adalah
            satu dokumen. Dari situlah asal-usul tiap harga bisa ditelusuri balik ke berkas
            aslinya — biarkan kosong kalau memang tidak ada dokumennya.
          </p>
          <textarea
            className="h-32 w-full rounded-lg border border-slate-300 p-2 font-mono text-xs"
            placeholder="Paste hasil copy dari Excel di sini..."
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
          />
          <div className="mt-2 flex gap-2">
            <button type="button" onClick={parsePasteFull} className="btn btn-secondary btn-sm">
              Preview
            </button>
          </div>

          {pasteWarnings.length > 0 && (
            <ul className="mt-2 list-disc pl-5 text-xs text-amber-700">
              {pasteWarnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          )}

          {pastePreview.length > 0 && (
            <>
              {cekBusy && (
                <p className="mt-2 text-xs text-slate-500">Memeriksa dampak paste ini...</p>
              )}
              {dampak && (
                <div className="mt-3 rounded-lg border border-slate-200 bg-white p-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Yang akan terjadi kalau disimpan
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs">
                    <span className="rounded bg-emerald-50 px-2 py-1 font-medium text-emerald-800">
                      {dampak.ringkas.material_baru} material baru
                    </span>
                    <span className="rounded bg-blue-50 px-2 py-1 font-medium text-blue-800">
                      {dampak.ringkas.harga_baru} titik harga baru
                    </span>
                    <span className="rounded bg-slate-100 px-2 py-1 font-medium text-slate-700">
                      {dampak.ringkas.dilewati} dilewati
                    </span>
                    {dampak.ringkas.peringatan > 0 && (
                      <span className="rounded bg-amber-100 px-2 py-1 font-medium text-amber-800">
                        {dampak.ringkas.peringatan} perlu diperiksa
                      </span>
                    )}
                  </div>
                  {dampak.ringkas.dilewati > 0 && (
                    <p className="mt-2 text-xs text-slate-500">
                      Baris yang dilewati harganya sudah persis sama dengan yang tercatat — itu
                      input berulang, bukan perubahan harga, jadi tidak dijadikan titik baru.
                    </p>
                  )}
                  {dampak.baris.some((b) => b.peringatan) && (
                    <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-amber-800">
                      {dampak.baris
                        .map((b, i) => ({ b, i }))
                        .filter(({ b }) => b.peringatan)
                        .map(({ b, i }) => (
                          <li key={i}>
                            <span className="font-medium">
                              {b.nama}
                              {b.spesifikasi ? ` (${b.spesifikasi})` : ""}
                            </span>
                            : {b.peringatan}
                          </li>
                        ))}
                    </ul>
                  )}
                </div>
              )}

              <div className="mt-3 overflow-auto rounded-lg border border-slate-200 bg-white">
              <table className="min-w-full text-left text-xs">
                <thead className="bg-slate-50 uppercase text-slate-500">
                  <tr>
                    <th className="px-2 py-2">Dampak</th>
                    {COLUMN_LABELS.map((l) => (
                      <th key={l} className="px-2 py-2">{l}</th>
                    ))}
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {pastePreview.map((d, i) => (
                    <tr key={i} className="border-t border-slate-100">
                      <td className="whitespace-nowrap px-2 py-1">
                        <StatusDampak row={dampak?.baris[i]} />
                      </td>
                      {COLUMN_ORDER.map((field) => (
                        <td key={field} className="px-2 py-1">
                          <div className="flex items-center gap-0.5">
                            {field === "harga_satuan" || field === "tahun_pembelian" ? (
                              <NumberInput
                                integer={field === "tahun_pembelian"}
                                ariaLabel={`${field} baris ${i + 1}`}
                                className="w-24 rounded border border-slate-200 px-1 py-0.5 text-right"
                                value={Number(d[field] ?? 0)}
                                onChange={(n) => ubahBarisPaste(i, field, n)}
                              />
                            ) : field === "mata_uang" ? (
                              <select
                                aria-label={`Mata uang baris ${i + 1}`}
                                className="rounded border border-slate-200 px-1 py-0.5"
                                value={d.mata_uang}
                                onChange={(e) => ubahBarisPaste(i, field, e.target.value as Currency)}
                              >
                                {CURRENCIES.map((c) => (
                                  <option key={c} value={c}>{c}</option>
                                ))}
                              </select>
                            ) : (
                              <input
                                aria-label={`${field} baris ${i + 1}`}
                                type={field === "berlaku_dari" ? "date" : "text"}
                                className="w-full min-w-24 rounded border border-slate-200 px-1 py-0.5"
                                value={String(d[field] ?? "")}
                                onChange={(e) => ubahBarisPaste(i, field, e.target.value)}
                              />
                            )}
                            {i < pastePreview.length - 1 && (
                              <button
                                type="button"
                                title="Isi nilai ini ke semua baris di bawah"
                                onClick={() => isiKeBawahPaste(i, field)}
                                className="shrink-0 rounded px-0.5 text-slate-300 hover:text-slate-800"
                              >
                                ↓
                              </button>
                            )}
                          </div>
                        </td>
                      ))}
                      <td className="whitespace-nowrap px-2 py-1">
                        <button
                          type="button"
                          title="Duplikat baris ini"
                          onClick={() => duplikatBarisPaste(i)}
                          className="rounded p-1 text-slate-400 hover:text-slate-800"
                        >
                          <Copy size={13} />
                        </button>
                        <button type="button" onClick={() => removePasteRow(i)} className="rounded p-1 text-slate-400 hover:text-red-700" title="Hapus baris ini">
                          <Trash2 size={13} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="flex items-center justify-between p-2">
                <p className="text-xs text-slate-500">
                  {busy
                    ? "Menyimpan, mohon tunggu..."
                    : dampak
                      ? `${pastePreview.length} baris — ${dampak.ringkas.material_baru} material baru, ` +
                        `${dampak.ringkas.harga_baru} titik harga baru, ${dampak.ringkas.dilewati} dilewati`
                      : `${pastePreview.length} baris siap disimpan`}
                </p>
                <button type="button" disabled={busy} onClick={submitPasteAdd} className="btn btn-primary btn-md">
                  <Save size={13} />
                  {busy ? "Menyimpan..." : `Simpan ${pastePreview.length} Baris`}
                </button>
              </div>
              </div>
            </>
          )}
        </div>
      )}

      {editMode && bulkEditOpen && (
        <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-bold text-slate-800">
              Edit massal ({bulkEditRows.length} {ISTILAH[jenis]})
            </p>
            <div className="flex gap-2">
              <button type="button" onClick={copyBulkEditToClipboard} className="btn btn-secondary btn-sm">
                <ClipboardPaste size={13} />
                Salin ke Excel
              </button>
              <button type="button" onClick={() => setBulkEditOpen(false)} className="btn btn-secondary btn-sm">
                <X size={13} />
                Tutup
              </button>
            </div>
          </div>
          <p className="mb-2 text-xs text-slate-600">
            Klik "Salin ke Excel" untuk copy baris terpilih, edit di Excel, lalu paste hasilnya di kotak bawah (urutan baris harus sama). Atau edit langsung di
            tabel kecil di bawah. Setiap simpan mencatat harga baru sebagai riwayat, bukan menimpa histori lama.
          </p>
          <textarea
            className="h-20 w-full rounded-lg border border-slate-300 p-2 font-mono text-xs"
            placeholder="Paste hasil edit dari Excel di sini (menimpa tabel di bawah, urutan baris harus sama)..."
            onChange={(e) => pasteBulkEditFromText(e.target.value)}
          />
          <div className="mt-3 overflow-auto rounded-lg border border-slate-200 bg-white">
            <table className="min-w-full text-left text-xs">
              <thead className="bg-slate-50 uppercase text-slate-500">
                <tr>
                  {COLUMN_LABELS.map((l) => (
                    <th key={l} className="px-2 py-2">{l}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {bulkEditRows.map((r, i) => (
                  <tr key={r.id} className="border-t border-slate-100">
                    {COLUMN_ORDER.map((field) =>
                      field === "mata_uang" ? (
                        <td key={field} className="px-1 py-1">
                          <select
                            className="cell-input"
                            value={r.data.mata_uang}
                            onChange={(e) => updateBulkEditCell(i, "mata_uang", e.target.value)}
                          >
                            {CURRENCIES.map((c) => (
                              <option key={c} value={c}>
                                {c}
                              </option>
                            ))}
                          </select>
                        </td>
                      ) : (
                        <td key={field} className="px-1 py-1">
                          {field === "harga_satuan" || field === "tahun_pembelian" ? (
                            <NumberInput
                              integer={field === "tahun_pembelian"}
                              ariaLabel={field}
                              className="cell-input"
                              value={Number(r.data[field] ?? 0)}
                              onChange={(n) => updateBulkEditCell(i, field, n)}
                            />
                          ) : (
                            <input
                              className="cell-input"
                              type={field === "berlaku_dari" ? "date" : "text"}
                              value={r.data[field] ?? ""}
                              onChange={(e) => updateBulkEditCell(i, field, e.target.value)}
                            />
                          )}
                        </td>
                      ),
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3">
            <button type="button" disabled={busy} onClick={submitBulkEdit} className="btn btn-accent btn-md">
              <Save size={14} />
              {busy ? "Menyimpan..." : "Simpan Semua Perubahan"}
            </button>
          </div>
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        {loading ? (
          <p className="p-8 text-center text-slate-500">Memuat data...</p>
        ) : rows.length === 0 ? (
          <p className="p-8 text-center text-sm text-slate-400">
            Belum ada {ISTILAH[jenis]} yang cocok dengan filter ini.
          </p>
        ) : (
          <div className="max-h-[560px] overflow-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="sticky top-0 bg-slate-50 text-xs uppercase text-slate-500">
                <tr>
                  {editMode && (
                    <th className="px-3 py-3">
                      <input
                        type="checkbox"
                        checked={allFilteredSelected}
                        ref={(el) => {
                          if (el) el.indeterminate = !allFilteredSelected && somePageSelected;
                        }}
                        onChange={toggleSelectAllFiltered}
                        title="Pilih semua hasil filter ini"
                      />
                    </th>
                  )}
                  <th className="px-4 py-3">Nama</th>
                  {adaSpesifikasi && <th className="px-4 py-3">Spesifikasi</th>}
                  <th className="px-4 py-3">Satuan</th>
                  <th className="px-4 py-3 text-right">Harga Terkini</th>
                  <th className="px-4 py-3">{labelTahun(jenis)}</th>
                  {adaPembelian && <th className="px-4 py-3">Supplier</th>}
                  {adaPembelian && <th className="px-4 py-3">Kapal</th>}
                  <th className="px-4 py-3">Berlaku Dari</th>
                  <th className="px-4 py-3"></th>
                  {editMode && <th className="px-4 py-3"></th>}
                </tr>
              </thead>
              <tbody>
                {pagedRows.map((r) => {
                  const isEditing = editingId === r.id;
                  return (
                    <tr key={r.id} className="border-t border-slate-100 hover:bg-slate-50">
                      {editMode && (
                        <td className="px-3 py-2">
                          <input type="checkbox" checked={selected.has(r.id)} onChange={() => toggleSelect(r.id)} disabled={isEditing} />
                        </td>
                      )}
                      {isEditing ? (
                        <>
                          <Cell><input className="cell-input" value={draft.nama} onChange={(e) => setDraft((d) => ({ ...d, nama: e.target.value }))} /></Cell>
                          {adaSpesifikasi && (
                            <Cell><input className="cell-input" value={draft.spesifikasi} onChange={(e) => setDraft((d) => ({ ...d, spesifikasi: e.target.value }))} /></Cell>
                          )}
                          <Cell><input className="cell-input" value={draft.satuan} onChange={(e) => setDraft((d) => ({ ...d, satuan: e.target.value }))} /></Cell>
                          <Cell align="right">
                            <div className="flex items-center gap-1">
                              <NumberInput
                                ariaLabel="Harga satuan"
                                className="cell-input text-right"
                                value={draft.harga_satuan}
                                onChange={(n) => setDraft((d) => ({ ...d, harga_satuan: n }))}
                              />
                              <select
                                className="cell-input"
                                value={draft.mata_uang}
                                onChange={(e) => setDraft((d) => ({ ...d, mata_uang: e.target.value as Currency }))}
                              >
                                {CURRENCIES.map((c) => (
                                  <option key={c} value={c}>
                                    {c}
                                  </option>
                                ))}
                              </select>
                            </div>
                          </Cell>
                          <Cell>
                            <NumberInput
                              integer
                              ariaLabel="Tahun pembelian"
                              className="cell-input"
                              value={draft.tahun_pembelian}
                              onChange={(n) => setDraft((d) => ({ ...d, tahun_pembelian: n }))}
                            />
                          </Cell>
                          {adaPembelian && (
                            <>
                              <Cell><input className="cell-input" value={draft.supplier_nama} onChange={(e) => setDraft((d) => ({ ...d, supplier_nama: e.target.value }))} /></Cell>
                              <Cell><input className="cell-input" value={draft.nama_kapal} onChange={(e) => setDraft((d) => ({ ...d, nama_kapal: e.target.value }))} /></Cell>
                            </>
                          )}
                          <Cell><input type="date" className="cell-input" value={draft.berlaku_dari ?? ""} onChange={(e) => setDraft((d) => ({ ...d, berlaku_dari: e.target.value || null }))} /></Cell>
                          <td className="px-4 py-2"></td>
                          <td className="whitespace-nowrap px-4 py-2">
                            <button type="button" disabled={busy} onClick={saveEdit} className="btn btn-primary btn-sm mr-1.5">
                              <Save size={12} />
                              {busy ? "..." : "Simpan"}
                            </button>
                            <button type="button" onClick={cancelEdit} className="btn btn-secondary btn-sm">
                              <X size={12} />
                              Batal
                            </button>
                          </td>
                        </>
                      ) : (
                        <>
                          <td className="px-4 py-2">{r.nama}</td>
                          {adaSpesifikasi && <td className="px-4 py-2">{r.spesifikasi || "-"}</td>}
                          <td className="px-4 py-2">{r.satuan}</td>
                          <td className="px-4 py-2 text-right font-medium">
                            {r.harga_satuan != null ? formatMoney(r.harga_satuan, r.mata_uang ?? "IDR") : "-"}
                          </td>
                          <td className="px-4 py-2">{r.tahun_pembelian ?? "-"}</td>
                          {adaPembelian && <td className="px-4 py-2">{r.supplier_nama ?? "-"}</td>}
                          {adaPembelian && <td className="px-4 py-2">{r.nama_kapal ?? "-"}</td>}
                          <td className="px-4 py-2">{r.berlaku_dari ?? "-"}</td>
                          <td className="px-4 py-2">
                            <button
                              type="button"
                              onClick={() => setHistoryFor(r)}
                              className="btn btn-secondary btn-sm"
                              title="Lihat & tambah riwayat harga"
                            >
                              <LineChart size={12} />
                              Riwayat
                            </button>
                          </td>
                          {editMode && (
                            <td className="px-4 py-2">
                              <button type="button" onClick={() => startEdit(r)} className="btn btn-secondary btn-sm">
                                <Pencil size={12} />
                                Edit
                              </button>
                            </td>
                          )}
                        </>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {rows.length > 0 && (
          <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3 text-xs text-slate-500">
            <span>
              Menampilkan {currentPage * PAGE_SIZE + 1}-{Math.min(rows.length, (currentPage + 1) * PAGE_SIZE)} dari{" "}
              {rows.length} {ISTILAH[jenis]}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={currentPage === 0}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                className="btn btn-secondary btn-sm"
              >
                <ChevronLeft size={13} />
                Sebelumnya
              </button>
              <span className="font-medium text-slate-600">
                Halaman {currentPage + 1} / {pageCount}
              </span>
              <button
                type="button"
                disabled={currentPage >= pageCount - 1}
                onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
                className="btn btn-secondary btn-sm"
              >
                Selanjutnya
                <ChevronRight size={13} />
              </button>
            </div>
          </div>
        )}
      </div>

      {historyFor && (
        <Suspense fallback={null}>
          <PriceHistoryDrawer
            token={token}
            material={historyFor}
            onClose={() => setHistoryFor(null)}
            onChanged={onChanged}
          />
        </Suspense>
      )}
    </div>
  );
}

function Cell({ children, align }: { children: React.ReactNode; align?: "right" }) {
  return <td className={`px-2 py-1 ${align === "right" ? "text-right" : ""}`}>{children}</td>;
}

function LabeledInput({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
}) {
  return (
    <label className="block text-xs font-medium text-slate-600">
      {label}
      <input type={type} className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm" value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

/** Label dampak per baris paste. Ditampilkan sebelum menyimpan supaya jelas mana yang
 * membuat material baru dan mana yang cuma menambah titik harga ke material yang sudah ada
 * -- pembedaan itu sudah dilakukan backend sejak lama, tapi dulu tidak pernah diberitahukan
 * sehingga orang mengira harus memisahkan pastenya sendiri. */
function StatusDampak({ row }: { row?: PastePreviewRow }) {
  if (!row) return <span className="text-slate-400">-</span>;

  const gaya = {
    material_baru: "bg-emerald-50 text-emerald-800",
    harga_baru: "bg-blue-50 text-blue-800",
    dilewati: "bg-slate-100 text-slate-600",
  }[row.status];

  const label = {
    material_baru: "Material baru",
    harga_baru: "Titik harga baru",
    dilewati: "Dilewati",
  }[row.status];

  return (
    <span className="flex flex-col items-start gap-0.5">
      <span className={`rounded px-1.5 py-0.5 font-medium ${gaya}`}>{label}</span>
      {row.perubahan_persen != null && row.harga_lama != null && (
        <span
          className={`tabular-nums ${
            row.perubahan_persen > 0
              ? "text-red-700"
              : row.perubahan_persen < 0
                ? "text-emerald-700"
                : "text-slate-500"
          }`}
        >
          {row.perubahan_persen > 0 ? "+" : ""}
          {row.perubahan_persen.toFixed(2)}% dari {formatMoney(row.harga_lama, row.mata_uang)}
        </span>
      )}
      {row.peringatan && <span className="text-amber-700">perlu diperiksa</span>}
    </span>
  );
}
