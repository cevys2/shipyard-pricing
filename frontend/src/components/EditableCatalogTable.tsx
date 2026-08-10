import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, ClipboardPaste, Pencil, Plus, Save, Trash2, X } from "lucide-react";
import {
  api,
  formatMoneyRingkas,
  formatRp,
  type CatalogRow,
  type CatalogRowInput,
  type FilterOptions,
} from "../lib/api";
import { bacaAngkaUang, parseTsv } from "../lib/tsv";

const PAGE_SIZE = 50;

type Props = {
  token: string;
  rows: CatalogRow[];
  filterOpts: FilterOptions;
  loading: boolean;
  onChanged: () => void; // call after any successful save/delete/add to refresh parent data
};

const COLUMN_ORDER: (keyof CatalogRowInput)[] = [
  "nama_perusahaan",
  "nama_kapal",
  "tipe_perjanjian",
  "tahun",
  "kategori_pekerjaan",
  "uraian_pekerjaan",
  "volume_satuan",
  "harga_satuan",
];
const COLUMN_LABELS = ["Perusahaan", "Kapal", "Tipe", "Tahun", "Kategori", "Uraian", "Satuan", "Harga"];

const emptyDraft: CatalogRowInput = {
  nama_perusahaan: "",
  nama_kapal: "",
  tipe_perjanjian: "Induk",
  tahun: "",
  kategori_pekerjaan: "-",
  uraian_pekerjaan: "",
  volume_satuan: "-",
  harga_satuan: 0,
};

/** Hasil baca satu baris tempelan: draftnya, plus bagaimana kolom Harga dibaca.
 *
 * Angkanya saja tidak cukup. Kolom Harga dulu dibaca dengan membuang semua karakter
 * selain angka dan titik, jadi "150.000" tersimpan sebagai 150 -- salah 1000x, tapi
 * angkanya tetap masuk akal sekilas dan lolos tanpa jejak. Sekarang pembacaannya benar,
 * tapi yang membuatnya aman bukan cuma itu: sel mentahnya ikut dibawa keluar supaya
 * pemanggil bisa menunjukkan penafsirannya sebelum apa pun disimpan. */
type HasilBarisTempel = {
  draft: CatalogRowInput;
  harga: { mentah: string; ditafsirkan: boolean; dikenali: boolean };
};

function cellsToDraft(cells: string[]): HasilBarisTempel {
  const get = (i: number) => (cells[i] ?? "").trim();
  const tipeRaw = get(2);
  const hargaMentah = get(7);
  const harga = bacaAngkaUang(hargaMentah);
  return {
    draft: {
      nama_perusahaan: get(0),
      nama_kapal: get(1),
      tipe_perjanjian: tipeRaw === "Addendum" ? "Addendum" : "Induk",
      tahun: get(3),
      kategori_pekerjaan: get(4) || "-",
      uraian_pekerjaan: get(5),
      volume_satuan: get(6) || "-",
      harga_satuan: harga.nilai,
    },
    harga: { mentah: hargaMentah, ditafsirkan: harga.ditafsirkan, dikenali: harga.dikenali },
  };
}

function draftToRow(d: CatalogRowInput): string[] {
  return COLUMN_ORDER.map((k) => String(d[k]));
}

export default function EditableCatalogTable({ token, rows, loading, onChanged }: Props) {
  const [editMode, setEditMode] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<CatalogRowInput>(emptyDraft);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const [showAdd, setShowAdd] = useState(false);
  const [addTab, setAddTab] = useState<"form" | "pasteUraian" | "pasteFull">("pasteUraian");
  const [addDraft, setAddDraft] = useState<CatalogRowInput>(emptyDraft);
  const [pasteText, setPasteText] = useState("");
  const [pastePreview, setPastePreview] = useState<CatalogRowInput[]>([]);
  const [pasteWarnings, setPasteWarnings] = useState<string[]>([]);

  function switchAddTab(tab: "form" | "pasteUraian" | "pasteFull") {
    setAddTab(tab);
    setPasteText("");
    setPastePreview([]);
    setPasteWarnings([]);
    setError("");
  }

  const [bulkEditOpen, setBulkEditOpen] = useState(false);
  const [bulkEditRows, setBulkEditRows] = useState<{ id: string; data: CatalogRowInput }[]>([]);

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

  function startEdit(row: CatalogRow) {
    setEditingId(row.id);
    setDraft({
      nama_perusahaan: row.nama_perusahaan,
      nama_kapal: row.nama_kapal,
      tipe_perjanjian: row.tipe_perjanjian === "Addendum" ? "Addendum" : "Induk",
      tahun: row.tahun,
      kategori_pekerjaan: row.kategori_pekerjaan,
      uraian_pekerjaan: row.uraian_pekerjaan,
      volume_satuan: row.volume_satuan,
      harga_satuan: row.harga_satuan,
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
      await api.patchCatalog(token, { updates: [{ id: editingId, data: draft }] });
      setEditingId(null);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal menyimpan perubahan");
    } finally {
      setBusy(false);
    }
  }

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function deleteSelected() {
    if (selected.size === 0) return;
    if (!confirm(`Hapus ${selected.size} baris terpilih? Tindakan ini tidak bisa dibatalkan.`)) return;
    setBusy(true);
    setError("");
    try {
      await api.patchCatalog(token, { delete_ids: Array.from(selected) });
      setSelected(new Set());
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal menghapus baris");
    } finally {
      setBusy(false);
    }
  }

  // ---- single-row add form ----
  async function submitAdd() {
    if (!addDraft.nama_kapal.trim() || !addDraft.tahun.trim() || !addDraft.uraian_pekerjaan.trim()) {
      setError("Nama Kapal, Tahun, dan Uraian Pekerjaan wajib diisi");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const { uraian_pekerjaan, kategori_pekerjaan, volume_satuan, harga_satuan, ...header } = addDraft;
      await api.addRow(token, header, { uraian_pekerjaan, kategori_pekerjaan, volume_satuan, harga_satuan });
      setAddDraft(emptyDraft);
      setShowAdd(false);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal menambah baris");
    } finally {
      setBusy(false);
    }
  }

  // ---- paste-from-Excel bulk add: full 8 kolom ----
  function parsePasteFull() {
    setError("");
    const parsedRows = parseTsv(pasteText);
    const warnings: string[] = [];
    const drafts: CatalogRowInput[] = [];
    parsedRows.forEach((cells, i) => {
      const { draft: d, harga } = cellsToDraft(cells);
      if (!d.nama_kapal || !d.tahun || !d.uraian_pekerjaan) {
        warnings.push(`Baris ${i + 1}: Kapal/Tahun/Uraian kosong, dilewati`);
        return;
      }
      // Sel harga yang terisi tapi tidak terbaca beda dari sel harga yang kosong.
      // Menyimpannya sebagai 0 berarti memasukkan angka yang tidak pernah ditulis
      // siapa pun ke katalog, jadi barisnya dilewati seperti baris yang datanya kurang.
      if (harga.mentah !== "" && !harga.dikenali) {
        warnings.push(`Baris ${i + 1}: harga "${harga.mentah}" tidak terbaca sebagai angka, dilewati`);
        return;
      }
      if (harga.ditafsirkan) {
        warnings.push(`Baris ${i + 1}: "${harga.mentah}" dibaca sebagai ${formatMoneyRingkas(d.harga_satuan, "IDR")}`);
      }
      drafts.push(d);
    });
    setPastePreview(drafts);
    setPasteWarnings(warnings);
  }

  // ---- paste hanya kolom Uraian (drag-fill Excel), header/default dari addDraft ----
  function parsePasteUraian() {
    setError("");
    if (!addDraft.nama_kapal.trim() || !addDraft.tahun.trim()) {
      setError("Isi dulu Kapal dan Tahun di atas sebelum paste kolom Uraian");
      return;
    }
    const lines = pasteText
      .replace(/\r\n/g, "\n")
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l !== "");
    const drafts: CatalogRowInput[] = lines.map((line) => ({
      ...addDraft,
      uraian_pekerjaan: line,
    }));
    setPastePreview(drafts);
    setPasteWarnings([]);
  }

  function removePasteRow(idx: number) {
    setPastePreview((rows2) => rows2.filter((_, i) => i !== idx));
  }

  async function submitPasteAdd() {
    if (pastePreview.length === 0) return;
    setBusy(true);
    setError("");
    try {
      const groups = new Map<
        string,
        { header: { nama_perusahaan: string; nama_kapal: string; tahun: string; tipe_perjanjian: "Induk" | "Addendum" }; items: CatalogRowInput[] }
      >();
      for (const d of pastePreview) {
        const key = `${d.nama_perusahaan}|${d.nama_kapal}|${d.tahun}|${d.tipe_perjanjian}`;
        if (!groups.has(key)) {
          groups.set(key, {
            header: { nama_perusahaan: d.nama_perusahaan, nama_kapal: d.nama_kapal, tahun: d.tahun, tipe_perjanjian: d.tipe_perjanjian },
            items: [],
          });
        }
        groups.get(key)!.items.push(d);
      }
      let total = 0;
      for (const { header, items } of groups.values()) {
        const res = await api.bulkCreateMany(
          token,
          header,
          items.map(({ kategori_pekerjaan, uraian_pekerjaan, volume_satuan, harga_satuan }) => ({
            kategori_pekerjaan,
            uraian_pekerjaan,
            volume_satuan,
            harga_satuan,
          })),
        );
        total += res.saved;
      }
      setPasteText("");
      setPastePreview([]);
      setPasteWarnings([]);
      setShowAdd(false);
      onChanged();
      alert(`Berhasil menambah ${total} baris.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal menyimpan baris hasil paste");
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
          nama_perusahaan: r.nama_perusahaan,
          nama_kapal: r.nama_kapal,
          tipe_perjanjian: r.tipe_perjanjian === "Addendum" ? "Addendum" : "Induk",
          tahun: r.tahun,
          kategori_pekerjaan: r.kategori_pekerjaan,
          uraian_pekerjaan: r.uraian_pekerjaan,
          volume_satuan: r.volume_satuan,
          harga_satuan: r.harga_satuan,
        },
      })),
    );
    setBulkEditOpen(true);
    setError("");
  }

  function copyBulkEditToClipboard() {
    const tsv = bulkEditRows.map((r) => draftToRow(r.data).join("\t")).join("\n");
    navigator.clipboard.writeText(tsv).catch(() => setError("Gagal menyalin ke clipboard"));
  }

  function pasteBulkEditFromText(text: string) {
    const parsedRows = parseTsv(text);
    setBulkEditRows((prev) =>
      prev.map((r, i) => (parsedRows[i] ? { id: r.id, data: cellsToDraft(parsedRows[i]).draft } : r)),
    );
  }

  function updateBulkEditCell(rowIdx: number, field: keyof CatalogRowInput, value: string | number) {
    setBulkEditRows((prev) => prev.map((r, i) => (i === rowIdx ? { ...r, data: { ...r.data, [field]: value } } : r)));
  }

  async function submitBulkEdit() {
    setBusy(true);
    setError("");
    try {
      await api.patchCatalog(token, { updates: bulkEditRows });
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
                setShowAdd((s) => !s);
                setBulkEditOpen(false);
              }}
              className="btn btn-primary btn-md"
            >
              <Plus size={14} />
              Tambah Baris
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
              Hapus Terpilih ({selected.size})
            </button>
          </>
        )}
      </div>

      {error && <p className="mb-3 text-sm text-red-600">{error}</p>}

      {editMode && showAdd && (
        <div className="mb-4 rounded-xl border border-blue-200 bg-blue-50 p-4">
          <p className="mb-2 text-xs font-bold text-slate-700">Kapal & default (dipakai di semua mode di bawah)</p>
          <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
            <LabeledInput label="Perusahaan" value={addDraft.nama_perusahaan} onChange={(v) => setAddDraft((d) => ({ ...d, nama_perusahaan: v }))} />
            <LabeledInput label="Kapal *" value={addDraft.nama_kapal} onChange={(v) => setAddDraft((d) => ({ ...d, nama_kapal: v }))} />
            <LabeledInput label="Tahun *" value={addDraft.tahun} onChange={(v) => setAddDraft((d) => ({ ...d, tahun: v }))} />
            <label className="block text-xs font-medium text-slate-600">
              Tipe
              <select
                className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm"
                value={addDraft.tipe_perjanjian}
                onChange={(e) => setAddDraft((d) => ({ ...d, tipe_perjanjian: e.target.value as "Induk" | "Addendum" }))}
              >
                <option value="Induk">Induk</option>
                <option value="Addendum">Addendum</option>
              </select>
            </label>
            <LabeledInput label="Kategori default" value={addDraft.kategori_pekerjaan} onChange={(v) => setAddDraft((d) => ({ ...d, kategori_pekerjaan: v }))} />
            <LabeledInput label="Satuan default" value={addDraft.volume_satuan} onChange={(v) => setAddDraft((d) => ({ ...d, volume_satuan: v }))} />
            <LabeledInput
              label="Harga default"
              type="number"
              value={String(addDraft.harga_satuan)}
              onChange={(v) => setAddDraft((d) => ({ ...d, harga_satuan: Number(v) || 0 }))}
            />
          </div>
          <p className="mb-3 text-xs text-slate-500">
            Kategori/Satuan/Harga default ini dipakai buat semua baris hasil paste kolom Uraian - kalau ada yang beda-beda,
            perbaiki belakangan lewat Mode Edit / Edit Massal setelah disimpan.
          </p>

          <div className="mb-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => switchAddTab("pasteUraian")}
              className={`btn btn-sm ${addTab === "pasteUraian" ? "btn-primary" : "btn-secondary"}`}
            >
              Tempel Kolom Uraian (drag-fill Excel)
            </button>
            <button
              type="button"
              onClick={() => switchAddTab("form")}
              className={`btn btn-sm ${addTab === "form" ? "btn-primary" : "btn-secondary"}`}
            >
              1 Baris Manual
            </button>
            <button
              type="button"
              onClick={() => switchAddTab("pasteFull")}
              className={`btn btn-sm ${addTab === "pasteFull" ? "btn-primary" : "btn-secondary"}`}
            >
              Tempel Lengkap (8 kolom)
            </button>
          </div>

          {addTab === "form" && (
            <>
              <label className="block text-xs font-medium text-slate-600">
                Uraian Pekerjaan *
                <input
                  className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm"
                  value={addDraft.uraian_pekerjaan}
                  onChange={(e) => setAddDraft((d) => ({ ...d, uraian_pekerjaan: e.target.value }))}
                />
              </label>
              <div className="mt-3 flex gap-2">
                <button type="button" disabled={busy} onClick={submitAdd} className="btn btn-primary btn-md">
                  <Save size={13} />
                  Simpan Baris
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
            </>
          )}

          {addTab === "pasteUraian" && (
            <>
              <p className="mb-2 text-xs text-slate-600">
                Di Excel, drag-fill/tarik ke bawah kolom <strong>Uraian Pekerjaan</strong> aja (satu uraian per baris),
                select, Ctrl+C, paste di kotak bawah. Kategori/Satuan/Harga dari default di atas akan dipakai buat semua baris -
                edit satu-satu belakangan kalau perlu.
              </p>
              <textarea
                className="h-32 w-full rounded-lg border border-slate-300 p-2 font-mono text-xs"
                placeholder={"Pelayanan mooring boat\nPembersihan lambung kapal\nPengecatan anti fouling\n..."}
                value={pasteText}
                onChange={(e) => setPasteText(e.target.value)}
              />
              <div className="mt-2 flex gap-2">
                <button type="button" onClick={parsePasteUraian} className="btn btn-secondary btn-sm">
                  Preview
                </button>
              </div>
            </>
          )}

          {addTab === "pasteFull" && (
            <>
              <p className="mb-2 text-xs text-slate-600">
                Di Excel, urutkan kolom: <strong>Perusahaan | Kapal | Tipe | Tahun | Kategori | Uraian | Satuan | Harga</strong> (Perusahaan/Kategori/Satuan boleh
                kosong). Select semua sel yang mau ditambah, Ctrl+C, lalu paste di kotak bawah ini. Pakai mode ini kalau tiap baris
                punya kategori/satuan/harga yang beda-beda.
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
            </>
          )}

          {(addTab === "pasteUraian" || addTab === "pasteFull") && (
            <>
              {pasteWarnings.length > 0 && (
                <ul className="mt-2 list-disc pl-5 text-xs text-amber-700">
                  {pasteWarnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              )}

              {pastePreview.length > 0 && (
                <div className="mt-3 overflow-auto rounded-lg border border-slate-200 bg-white">
                  <table className="min-w-full text-left text-xs">
                    <thead className="bg-slate-50 uppercase text-slate-500">
                      <tr>
                        {COLUMN_LABELS.map((l) => (
                          <th key={l} className="px-2 py-2">{l}</th>
                        ))}
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {pastePreview.map((d, i) => (
                        <tr key={i} className="border-t border-slate-100">
                          {draftToRow(d).map((v, j) => (
                            <td key={j} className="px-2 py-1">{v}</td>
                          ))}
                          <td className="px-2 py-1">
                            <button type="button" onClick={() => removePasteRow(i)} className="text-xs font-semibold text-red-600 hover:underline">
                              hapus
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div className="flex items-center justify-between p-2">
                    <p className="text-xs text-slate-500">{pastePreview.length} baris siap disimpan</p>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={submitPasteAdd}
                      className="btn btn-primary btn-md"
                    >
                      <Save size={13} />
                      Simpan {pastePreview.length} Baris
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {editMode && bulkEditOpen && (
        <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-bold text-slate-800">Edit massal ({bulkEditRows.length} baris)</p>
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
            tabel kecil di bawah.
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
                      field === "tipe_perjanjian" ? (
                        <td key={field} className="px-1 py-1">
                          <select
                            className="cell-input"
                            value={r.data.tipe_perjanjian}
                            onChange={(e) => updateBulkEditCell(i, "tipe_perjanjian", e.target.value)}
                          >
                            <option value="Induk">Induk</option>
                            <option value="Addendum">Addendum</option>
                          </select>
                        </td>
                      ) : (
                        <td key={field} className="px-1 py-1">
                          <input
                            className="cell-input"
                            type={field === "harga_satuan" ? "number" : "text"}
                            value={r.data[field]}
                            onChange={(e) =>
                              updateBulkEditCell(i, field, field === "harga_satuan" ? Number(e.target.value) || 0 : e.target.value)
                            }
                          />
                        </td>
                      ),
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3">
            <button
              type="button"
              disabled={busy}
              onClick={submitBulkEdit}
              className="btn btn-accent btn-md"
            >
              <Save size={14} />
              Simpan Semua Perubahan
            </button>
          </div>
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        {loading ? (
          <p className="p-8 text-center text-slate-500">Memuat data...</p>
        ) : rows.length === 0 ? (
          <p className="p-8 text-center text-sm text-slate-400">Tidak ada data yang cocok dengan filter ini.</p>
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
                  <th className="px-4 py-3">Perusahaan</th>
                  <th className="px-4 py-3">Kapal</th>
                  <th className="px-4 py-3">Tipe</th>
                  <th className="px-4 py-3">Tahun</th>
                  <th className="px-4 py-3">Kategori</th>
                  <th className="px-4 py-3">Uraian</th>
                  <th className="px-4 py-3">Satuan</th>
                  <th className="px-4 py-3 text-right">Harga</th>
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
                          <Cell><input className="cell-input" value={draft.nama_perusahaan} onChange={(e) => setDraft((d) => ({ ...d, nama_perusahaan: e.target.value }))} /></Cell>
                          <Cell><input className="cell-input" value={draft.nama_kapal} onChange={(e) => setDraft((d) => ({ ...d, nama_kapal: e.target.value }))} /></Cell>
                          <Cell>
                            <select className="cell-input" value={draft.tipe_perjanjian} onChange={(e) => setDraft((d) => ({ ...d, tipe_perjanjian: e.target.value as "Induk" | "Addendum" }))}>
                              <option value="Induk">Induk</option>
                              <option value="Addendum">Addendum</option>
                            </select>
                          </Cell>
                          <Cell><input className="cell-input" value={draft.tahun} onChange={(e) => setDraft((d) => ({ ...d, tahun: e.target.value }))} /></Cell>
                          <Cell><input className="cell-input" value={draft.kategori_pekerjaan} onChange={(e) => setDraft((d) => ({ ...d, kategori_pekerjaan: e.target.value }))} /></Cell>
                          <Cell><input className="cell-input" value={draft.uraian_pekerjaan} onChange={(e) => setDraft((d) => ({ ...d, uraian_pekerjaan: e.target.value }))} /></Cell>
                          <Cell><input className="cell-input" value={draft.volume_satuan} onChange={(e) => setDraft((d) => ({ ...d, volume_satuan: e.target.value }))} /></Cell>
                          <Cell align="right">
                            <input type="number" className="cell-input text-right" value={draft.harga_satuan} onChange={(e) => setDraft((d) => ({ ...d, harga_satuan: Number(e.target.value) || 0 }))} />
                          </Cell>
                          <td className="whitespace-nowrap px-4 py-2">
                            <button type="button" disabled={busy} onClick={saveEdit} className="btn btn-primary btn-sm mr-1.5">
                              <Save size={12} />
                              Simpan
                            </button>
                            <button type="button" onClick={cancelEdit} className="btn btn-secondary btn-sm">
                              <X size={12} />
                              Batal
                            </button>
                          </td>
                        </>
                      ) : (
                        <>
                          <td className="px-4 py-2">{r.nama_perusahaan}</td>
                          <td className="px-4 py-2">{r.nama_kapal}</td>
                          <td className="px-4 py-2">
                            <span
                              className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                                r.tipe_perjanjian === "Addendum" ? "bg-purple-100 text-purple-700" : "bg-blue-100 text-blue-700"
                              }`}
                            >
                              {r.tipe_perjanjian}
                            </span>
                          </td>
                          <td className="px-4 py-2">{r.tahun}</td>
                          <td className="px-4 py-2">{r.kategori_pekerjaan}</td>
                          <td className="px-4 py-2">{r.uraian_pekerjaan}</td>
                          <td className="px-4 py-2">{r.volume_satuan}</td>
                          <td className="px-4 py-2 text-right font-medium">{formatRp(r.harga_satuan)}</td>
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
              {rows.length} baris
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
