import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, ClipboardPaste, Pencil, Plus, Save, Trash2, X } from "lucide-react";
import { api, formatRp, type MaterialItemInput, type MaterialRow } from "../lib/api";
import { parseTsv } from "../lib/tsv";

const PAGE_SIZE = 50;

type Props = {
  token: string;
  rows: MaterialRow[];
  loading: boolean;
  onChanged: () => void; // call after any successful save/delete/add to refresh parent data
};

const COLUMN_ORDER: (keyof MaterialItemInput)[] = [
  "kode",
  "nama",
  "spesifikasi",
  "satuan",
  "harga_satuan",
  "supplier_nama",
  "berlaku_dari",
];
const COLUMN_LABELS = ["Kode", "Nama", "Spesifikasi", "Satuan", "Harga", "Supplier", "Berlaku Dari"];

const emptyDraft: MaterialItemInput = {
  kode: "",
  nama: "",
  spesifikasi: "",
  satuan: "",
  harga_satuan: 0,
  supplier_nama: "",
  berlaku_dari: "",
  sumber: "",
  no_dokumen: "",
  catatan: "",
};

function cellsToDraft(cells: string[]): MaterialItemInput {
  const get = (i: number) => (cells[i] ?? "").trim();
  return {
    kode: get(0) || null,
    nama: get(1),
    spesifikasi: get(2),
    satuan: get(3),
    harga_satuan: Number(get(4).replace(/[^\d.-]/g, "")) || 0,
    supplier_nama: get(5),
    berlaku_dari: get(6) || null,
    sumber: "",
    no_dokumen: "",
    catatan: "",
  };
}

function draftToRow(d: MaterialItemInput): string[] {
  return COLUMN_ORDER.map((k) => String(d[k] ?? ""));
}

export default function EditableMaterialTable({ token, rows, loading, onChanged }: Props) {
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
      kode: row.kode,
      nama: row.nama,
      spesifikasi: row.spesifikasi,
      satuan: row.satuan,
      harga_satuan: row.harga_satuan ?? 0,
      supplier_nama: row.supplier_nama ?? "",
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
    if (!confirm(`Hapus ${selected.size} material terpilih? Tindakan ini tidak bisa dibatalkan.`)) return;
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

  // ---- paste-from-Excel bulk add: 7 kolom ----
  function parsePasteFull() {
    setError("");
    const parsedRows = parseTsv(pasteText);
    const warnings: string[] = [];
    const drafts: MaterialItemInput[] = [];
    parsedRows.forEach((cells, i) => {
      const d = cellsToDraft(cells);
      if (!d.nama || !d.satuan || d.harga_satuan <= 0) {
        warnings.push(`Baris ${i + 1}: Nama/Satuan/Harga wajib diisi (harga > 0), dilewati`);
        return;
      }
      drafts.push(d);
    });
    setPastePreview(drafts);
    setPasteWarnings(warnings);
  }

  function removePasteRow(idx: number) {
    setPastePreview((rows2) => rows2.filter((_, i) => i !== idx));
  }

  async function submitPasteAdd() {
    if (pastePreview.length === 0) return;
    setBusy(true);
    setError("");
    try {
      const res = await api.materialBulkCreate(token, pastePreview);
      setPasteText("");
      setPastePreview([]);
      setPasteWarnings([]);
      setShowAdd(false);
      onChanged();
      alert(`Berhasil menambah ${res.saved} material.`);
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
    setBusy(true);
    setError("");
    try {
      await api.materialBulkCreate(token, [addDraft]);
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
          kode: r.kode,
          nama: r.nama,
          spesifikasi: r.spesifikasi,
          satuan: r.satuan,
          harga_satuan: r.harga_satuan ?? 0,
          supplier_nama: r.supplier_nama ?? "",
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
    const tsv = bulkEditRows.map((r) => draftToRow(r.data).join("\t")).join("\n");
    navigator.clipboard.writeText(tsv).catch(() => setError("Gagal menyalin ke clipboard"));
  }

  function pasteBulkEditFromText(text: string) {
    const parsedRows = parseTsv(text);
    setBulkEditRows((prev) => prev.map((r, i) => (parsedRows[i] ? { id: r.id, data: cellsToDraft(parsedRows[i]) } : r)));
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
                setShowAdd((s) => !s);
                setBulkEditOpen(false);
              }}
              className="btn btn-primary btn-md"
            >
              <Plus size={14} />
              Tambah Material
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

      {editMode && showAdd && (
        <div className="mb-4 rounded-xl border border-blue-200 bg-blue-50 p-4">
          <p className="mb-3 text-xs font-bold text-slate-700">1 Baris Manual</p>
          <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
            <LabeledInput label="Kode" value={addDraft.kode ?? ""} onChange={(v) => setAddDraft((d) => ({ ...d, kode: v }))} />
            <LabeledInput label="Nama *" value={addDraft.nama} onChange={(v) => setAddDraft((d) => ({ ...d, nama: v }))} />
            <LabeledInput label="Spesifikasi" value={addDraft.spesifikasi} onChange={(v) => setAddDraft((d) => ({ ...d, spesifikasi: v }))} />
            <LabeledInput label="Satuan *" value={addDraft.satuan} onChange={(v) => setAddDraft((d) => ({ ...d, satuan: v }))} />
            <LabeledInput
              label="Harga *"
              type="number"
              value={String(addDraft.harga_satuan)}
              onChange={(v) => setAddDraft((d) => ({ ...d, harga_satuan: Number(v) || 0 }))}
            />
            <LabeledInput label="Supplier" value={addDraft.supplier_nama} onChange={(v) => setAddDraft((d) => ({ ...d, supplier_nama: v }))} />
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
            Urutkan kolom di Excel: <strong>Kode | Nama | Spesifikasi | Satuan | Harga | Supplier | Berlaku Dari</strong>{" "}
            (Kode/Spesifikasi/Supplier/Berlaku Dari boleh kosong). Select semua sel, Ctrl+C, lalu paste di kotak bawah.
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
                <p className="text-xs text-slate-500">
                  {busy ? "Menyimpan, mohon tunggu..." : `${pastePreview.length} material siap disimpan`}
                </p>
                <button type="button" disabled={busy} onClick={submitPasteAdd} className="btn btn-primary btn-md">
                  <Save size={13} />
                  {busy ? "Menyimpan..." : `Simpan ${pastePreview.length} Material`}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {editMode && bulkEditOpen && (
        <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-bold text-slate-800">Edit massal ({bulkEditRows.length} material)</p>
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
                    {COLUMN_ORDER.map((field) => (
                      <td key={field} className="px-1 py-1">
                        <input
                          className="cell-input"
                          type={field === "harga_satuan" ? "number" : field === "berlaku_dari" ? "date" : "text"}
                          value={r.data[field] ?? ""}
                          onChange={(e) =>
                            updateBulkEditCell(i, field, field === "harga_satuan" ? Number(e.target.value) || 0 : e.target.value)
                          }
                        />
                      </td>
                    ))}
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
          <p className="p-8 text-center text-sm text-slate-400">Belum ada material yang cocok dengan filter ini.</p>
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
                  <th className="px-4 py-3">Kode</th>
                  <th className="px-4 py-3">Nama</th>
                  <th className="px-4 py-3">Spesifikasi</th>
                  <th className="px-4 py-3">Satuan</th>
                  <th className="px-4 py-3 text-right">Harga Terkini</th>
                  <th className="px-4 py-3">Supplier</th>
                  <th className="px-4 py-3">Berlaku Dari</th>
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
                          <Cell><input className="cell-input" value={draft.kode ?? ""} onChange={(e) => setDraft((d) => ({ ...d, kode: e.target.value }))} /></Cell>
                          <Cell><input className="cell-input" value={draft.nama} onChange={(e) => setDraft((d) => ({ ...d, nama: e.target.value }))} /></Cell>
                          <Cell><input className="cell-input" value={draft.spesifikasi} onChange={(e) => setDraft((d) => ({ ...d, spesifikasi: e.target.value }))} /></Cell>
                          <Cell><input className="cell-input" value={draft.satuan} onChange={(e) => setDraft((d) => ({ ...d, satuan: e.target.value }))} /></Cell>
                          <Cell align="right">
                            <input type="number" className="cell-input text-right" value={draft.harga_satuan} onChange={(e) => setDraft((d) => ({ ...d, harga_satuan: Number(e.target.value) || 0 }))} />
                          </Cell>
                          <Cell><input className="cell-input" value={draft.supplier_nama} onChange={(e) => setDraft((d) => ({ ...d, supplier_nama: e.target.value }))} /></Cell>
                          <Cell><input type="date" className="cell-input" value={draft.berlaku_dari ?? ""} onChange={(e) => setDraft((d) => ({ ...d, berlaku_dari: e.target.value || null }))} /></Cell>
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
                          <td className="px-4 py-2">{r.kode ?? "-"}</td>
                          <td className="px-4 py-2">{r.nama}</td>
                          <td className="px-4 py-2">{r.spesifikasi || "-"}</td>
                          <td className="px-4 py-2">{r.satuan}</td>
                          <td className="px-4 py-2 text-right font-medium">{r.harga_satuan != null ? formatRp(r.harga_satuan) : "-"}</td>
                          <td className="px-4 py-2">{r.supplier_nama ?? "-"}</td>
                          <td className="px-4 py-2">{r.berlaku_dari ?? "-"}</td>
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
              {rows.length} material
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
