import { useState } from "react";
import { api, formatRp, type DockingImportPreview } from "../lib/api";

type Props = {
  token: string;
  onImported: () => void;
};

type EditRow = {
  key: string;
  kategori: string;
  uraian: string;
  volume_satuan: string;
  harga: number;
};

let counter = 0;
function newKey() {
  counter += 1;
  return `new-${Date.now()}-${counter}`;
}

function fromParsed(items: DockingImportPreview["induk"]): EditRow[] {
  return items.map((it) => ({
    key: `p-${it.row}`,
    kategori: it.kategori || "-",
    uraian: it.uraian,
    volume_satuan: it.volume_satuan,
    harga: it.harga,
  }));
}

const emptyRow = (): EditRow => ({ key: newKey(), kategori: "-", uraian: "", volume_satuan: "-", harga: 0 });

export default function DockingImportPanel({ token, onImported }: Props) {
  const [sheetName, setSheetName] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [header, setHeader] = useState({ nama_perusahaan: "", nama_kapal: "", tahun: "" });
  const [induk, setInduk] = useState<EditRow[] | null>(null);
  const [addendum, setAddendum] = useState<EditRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [resultMsg, setResultMsg] = useState("");

  async function handleFile(file: File) {
    setLoading(true);
    setError("");
    setResultMsg("");
    setInduk(null);
    setAddendum(null);
    try {
      const p = await api.dockingPreview(token, file);
      setSheetName(p.sheet_name);
      setWarnings(p.warnings);
      setHeader({
        nama_perusahaan: p.detected_nama_perusahaan,
        nama_kapal: p.detected_nama_kapal,
        tahun: p.detected_tahun,
      });
      setInduk(fromParsed(p.induk));
      setAddendum(fromParsed(p.addendum));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal membaca file");
    } finally {
      setLoading(false);
    }
  }

  function updateRow(list: "induk" | "addendum", key: string, field: keyof EditRow, value: string | number) {
    const setter = list === "induk" ? setInduk : setAddendum;
    setter((prev) => (prev ? prev.map((r) => (r.key === key ? { ...r, [field]: value } : r)) : prev));
  }

  function deleteRow(list: "induk" | "addendum", key: string) {
    const setter = list === "induk" ? setInduk : setAddendum;
    setter((prev) => (prev ? prev.filter((r) => r.key !== key) : prev));
  }

  function addRow(list: "induk" | "addendum") {
    const setter = list === "induk" ? setInduk : setAddendum;
    setter((prev) => [...(prev ?? []), emptyRow()]);
  }

  function moveRow(from: "induk" | "addendum", key: string) {
    const to = from === "induk" ? "addendum" : "induk";
    const fromSetter = from === "induk" ? setInduk : setAddendum;
    const toSetter = to === "induk" ? setInduk : setAddendum;
    let moved: EditRow | undefined;
    fromSetter((prev) => {
      if (!prev) return prev;
      moved = prev.find((r) => r.key === key);
      return prev.filter((r) => r.key !== key);
    });
    if (moved) {
      const m = moved;
      toSetter((prev) => [...(prev ?? []), m]);
    }
  }

  async function commit() {
    if (!induk || !addendum) return;
    if (!header.nama_kapal.trim() || !header.tahun.trim()) {
      setError("Nama Kapal dan Tahun wajib diisi sebelum simpan");
      return;
    }
    const invalidInduk = induk.some((r) => !r.uraian.trim() || !(r.harga > 0));
    const invalidAddendum = addendum.some((r) => !r.uraian.trim() || !(r.harga > 0));
    if (invalidInduk || invalidAddendum) {
      setError("Masih ada baris dengan Uraian kosong atau Harga 0 - benerin dulu di tabel di bawah sebelum konfirmasi.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const toItems = (rows: EditRow[]) =>
        rows.map((r) => ({
          kategori_pekerjaan: r.kategori || "-",
          uraian_pekerjaan: r.uraian,
          volume_satuan: r.volume_satuan,
          harga_satuan: r.harga,
        }));
      const res = await api.dockingCommit(token, {
        nama_perusahaan: header.nama_perusahaan,
        nama_kapal: header.nama_kapal,
        tahun: header.tahun,
        induk_items: toItems(induk),
        addendum_items: toItems(addendum),
      });
      setResultMsg(`Berhasil simpan ${res.saved} baris (${induk.length} Induk, ${addendum.length} Addendum).`);
      setInduk(null);
      setAddendum(null);
      onImported();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal menyimpan");
    } finally {
      setLoading(false);
    }
  }

  const showPreview = induk !== null && addendum !== null;

  return (
    <div>
      <input
        type="file"
        accept=".xlsx,.xls"
        className="block w-full text-sm"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void handleFile(f);
        }}
      />
      {loading && <p className="mt-3 text-sm text-slate-500">Memproses...</p>}
      {error && <p className="mt-3 text-sm font-medium text-red-600">{error}</p>}
      {resultMsg && <p className="mt-3 text-sm text-green-700">{resultMsg}</p>}

      {showPreview && (
        <div className="mt-5">
          <p className="mb-2 text-xs text-slate-500">Sheet terbaca: {sheetName}</p>

          <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <label className="block text-xs font-medium text-slate-600">
              Perusahaan
              <input
                className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm"
                value={header.nama_perusahaan}
                onChange={(e) => setHeader((h) => ({ ...h, nama_perusahaan: e.target.value }))}
              />
            </label>
            <label className="block text-xs font-medium text-slate-600">
              Kapal *
              <input
                className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm"
                value={header.nama_kapal}
                onChange={(e) => setHeader((h) => ({ ...h, nama_kapal: e.target.value }))}
              />
            </label>
            <label className="block text-xs font-medium text-slate-600">
              Tahun *
              <input
                className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm"
                value={header.tahun}
                onChange={(e) => setHeader((h) => ({ ...h, tahun: e.target.value }))}
              />
            </label>
          </div>

          {warnings.length > 0 && (
            <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 p-3">
              <p className="mb-1 text-xs font-bold text-amber-800">
                {warnings.length} hal yang di-flag parser waktu baca file (nomor baris merujuk ke file Excel asli):
              </p>
              <ul className="max-h-32 list-disc overflow-auto pl-5 text-xs text-amber-800">
                {warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          <p className="mb-4 rounded-lg border border-blue-200 bg-blue-50 p-3 text-xs text-slate-700">
            Cek tabel di bawah dulu. Kalau ada yang salah (harga, kategori, salah masuk Induk/Addendum, dll), edit
            langsung di sini - hapus baris, pindahin ke tabel sebelah, atau tambah baris manual. Baru klik{" "}
            <strong>Konfirmasi & Simpan</strong> kalau semuanya udah bener.
          </p>

          <EditTable
            title="Induk"
            rows={induk}
            onUpdate={(key, field, val) => updateRow("induk", key, field, val)}
            onDelete={(key) => deleteRow("induk", key)}
            onMove={(key) => moveRow("induk", key)}
            onAdd={() => addRow("induk")}
            moveLabel="Pindah ke Addendum"
            color="border-blue-200"
          />
          <div className="mt-5" />
          <EditTable
            title="Addendum"
            rows={addendum}
            onUpdate={(key, field, val) => updateRow("addendum", key, field, val)}
            onDelete={(key) => deleteRow("addendum", key)}
            onMove={(key) => moveRow("addendum", key)}
            onAdd={() => addRow("addendum")}
            moveLabel="Pindah ke Induk"
            color="border-purple-200"
          />

          <button
            type="button"
            disabled={loading}
            onClick={commit}
            className="mt-5 rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-bold text-white hover:bg-blue-500 disabled:opacity-50"
          >
            Konfirmasi & Simpan ({induk.length + addendum.length} baris)
          </button>
        </div>
      )}
    </div>
  );
}

function EditTable({
  title,
  rows,
  onUpdate,
  onDelete,
  onMove,
  onAdd,
  moveLabel,
  color,
}: {
  title: string;
  rows: EditRow[];
  onUpdate: (key: string, field: keyof EditRow, value: string | number) => void;
  onDelete: (key: string) => void;
  onMove: (key: string) => void;
  onAdd: () => void;
  moveLabel: string;
  color: string;
}) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <p className="text-sm font-bold text-slate-800">
          {title} ({rows.length} baris)
        </p>
        <button type="button" onClick={onAdd} className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs font-bold text-slate-700 hover:bg-slate-50">
          + Tambah Baris Manual
        </button>
      </div>
      {rows.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-300 p-4 text-center text-xs text-slate-400">
          Tidak ada baris.
        </p>
      ) : (
        <div className={`max-h-80 overflow-auto rounded-lg border ${color} bg-white`}>
          <table className="min-w-full text-left text-xs">
            <thead className="sticky top-0 bg-slate-50 uppercase text-slate-500">
              <tr>
                <th className="px-2 py-2">Kategori</th>
                <th className="px-2 py-2">Uraian</th>
                <th className="px-2 py-2">Volume</th>
                <th className="px-2 py-2 text-right">Harga</th>
                <th className="px-2 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key} className="border-t border-slate-100">
                  <td className="px-1 py-1">
                    <input className="cell-input" value={r.kategori} onChange={(e) => onUpdate(r.key, "kategori", e.target.value)} />
                  </td>
                  <td className="px-1 py-1">
                    <input className="cell-input" value={r.uraian} onChange={(e) => onUpdate(r.key, "uraian", e.target.value)} />
                  </td>
                  <td className="px-1 py-1">
                    <input className="cell-input" value={r.volume_satuan} onChange={(e) => onUpdate(r.key, "volume_satuan", e.target.value)} />
                  </td>
                  <td className="px-1 py-1">
                    <input
                      type="number"
                      className="cell-input text-right"
                      value={r.harga}
                      onChange={(e) => onUpdate(r.key, "harga", Number(e.target.value) || 0)}
                    />
                    {r.harga <= 0 && <span className="block text-[10px] text-red-500">harga wajib &gt; 0</span>}
                  </td>
                  <td className="whitespace-nowrap px-1 py-1">
                    <button type="button" onClick={() => onMove(r.key)} className="mr-1 rounded border border-slate-300 px-1.5 py-1 text-[10px] font-semibold text-slate-700 hover:bg-slate-100">
                      {moveLabel}
                    </button>
                    <button type="button" onClick={() => onDelete(r.key)} className="rounded border border-red-300 px-1.5 py-1 text-[10px] font-semibold text-red-600 hover:bg-red-50">
                      Hapus
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="border-t border-slate-100 px-2 py-2 text-right text-xs font-semibold text-slate-600">
            Total: {formatRp(rows.reduce((s, r) => s + (r.harga || 0), 0))}
          </p>
        </div>
      )}
    </div>
  );
}
