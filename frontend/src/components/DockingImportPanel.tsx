import { useState } from "react";
import { api, formatRp, type DockingImportPreview, type DockingParsedItem } from "../lib/api";

type Props = {
  token: string;
  onImported: () => void;
};

export default function DockingImportPanel({ token, onImported }: Props) {
  const [preview, setPreview] = useState<DockingImportPreview | null>(null);
  const [header, setHeader] = useState({ nama_perusahaan: "", nama_kapal: "", tahun: "" });
  const [excludedInduk, setExcludedInduk] = useState<Set<number>>(new Set());
  const [excludedAddendum, setExcludedAddendum] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [resultMsg, setResultMsg] = useState("");

  async function handleFile(file: File) {
    setLoading(true);
    setError("");
    setResultMsg("");
    setPreview(null);
    try {
      const p = await api.dockingPreview(token, file);
      setPreview(p);
      setHeader({
        nama_perusahaan: p.detected_nama_perusahaan,
        nama_kapal: p.detected_nama_kapal,
        tahun: p.detected_tahun,
      });
      setExcludedInduk(new Set());
      setExcludedAddendum(new Set());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal membaca file");
    } finally {
      setLoading(false);
    }
  }

  function toggleExclude(set: Set<number>, setFn: (s: Set<number>) => void, row: number) {
    const next = new Set(set);
    if (next.has(row)) next.delete(row);
    else next.add(row);
    setFn(next);
  }

  async function commit() {
    if (!preview) return;
    if (!header.nama_kapal.trim() || !header.tahun.trim()) {
      setError("Nama Kapal dan Tahun wajib diisi sebelum simpan");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const induk_items = preview.induk
        .filter((it) => !excludedInduk.has(it.row))
        .map((it) => ({
          kategori_pekerjaan: it.kategori || "-",
          uraian_pekerjaan: it.uraian,
          volume_satuan: it.volume_satuan,
          harga_satuan: it.harga,
        }));
      const addendum_items = preview.addendum
        .filter((it) => !excludedAddendum.has(it.row))
        .map((it) => ({
          kategori_pekerjaan: it.kategori || "-",
          uraian_pekerjaan: it.uraian,
          volume_satuan: it.volume_satuan,
          harga_satuan: it.harga,
        }));
      const res = await api.dockingCommit(token, {
        nama_perusahaan: header.nama_perusahaan,
        nama_kapal: header.nama_kapal,
        tahun: header.tahun,
        induk_items,
        addendum_items,
      });
      setResultMsg(`Berhasil simpan ${res.saved} baris (${induk_items.length} Induk, ${addendum_items.length} Addendum).`);
      setPreview(null);
      onImported();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal menyimpan");
    } finally {
      setLoading(false);
    }
  }

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
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      {resultMsg && <p className="mt-3 text-sm text-green-700">{resultMsg}</p>}

      {preview && (
        <div className="mt-5">
          <p className="mb-2 text-xs text-slate-500">Sheet terbaca: {preview.sheet_name}</p>

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
          <p className="mb-4 text-xs text-slate-500">
            Nama kapal/perusahaan/tahun ini dideteksi otomatis dari blok "DATA-DATA KAPAL" - cek dulu sebelum simpan.
          </p>

          {preview.warnings.length > 0 && (
            <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 p-3">
              <p className="mb-1 text-xs font-bold text-amber-800">
                {preview.warnings.length} hal perlu dicek manual:
              </p>
              <ul className="max-h-32 list-disc overflow-auto pl-5 text-xs text-amber-800">
                {preview.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          <ItemTable
            title={`Induk (${preview.induk.length - excludedInduk.size}/${preview.induk.length} dipilih)`}
            items={preview.induk}
            excluded={excludedInduk}
            onToggle={(row) => toggleExclude(excludedInduk, setExcludedInduk, row)}
            color="border-blue-200"
          />
          <div className="mt-4" />
          <ItemTable
            title={`Addendum (${preview.addendum.length - excludedAddendum.size}/${preview.addendum.length} dipilih)`}
            items={preview.addendum}
            excluded={excludedAddendum}
            onToggle={(row) => toggleExclude(excludedAddendum, setExcludedAddendum, row)}
            color="border-purple-200"
          />

          <button
            type="button"
            disabled={loading}
            onClick={commit}
            className="mt-4 rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-bold text-white hover:bg-blue-500 disabled:opacity-50"
          >
            Simpan yang Dipilih
          </button>
        </div>
      )}
    </div>
  );
}

function ItemTable({
  title,
  items,
  excluded,
  onToggle,
  color,
}: {
  title: string;
  items: DockingParsedItem[];
  excluded: Set<number>;
  onToggle: (row: number) => void;
  color: string;
}) {
  if (items.length === 0) {
    return (
      <div>
        <p className="mb-1 text-sm font-bold text-slate-800">{title}</p>
        <p className="text-xs text-slate-400">Tidak ada baris terdeteksi.</p>
      </div>
    );
  }
  return (
    <div>
      <p className="mb-1 text-sm font-bold text-slate-800">{title}</p>
      <div className={`max-h-72 overflow-auto rounded-lg border ${color} bg-white`}>
        <table className="min-w-full text-left text-xs">
          <thead className="sticky top-0 bg-slate-50 uppercase text-slate-500">
            <tr>
              <th className="px-2 py-2"></th>
              <th className="px-2 py-2">Baris</th>
              <th className="px-2 py-2">Kategori</th>
              <th className="px-2 py-2">Uraian</th>
              <th className="px-2 py-2">Volume</th>
              <th className="px-2 py-2 text-right">Harga</th>
              <th className="px-2 py-2">Keterangan</th>
            </tr>
          </thead>
          <tbody>
            {items.map((it) => (
              <tr key={it.row} className={`border-t border-slate-100 ${excluded.has(it.row) ? "opacity-40" : ""}`}>
                <td className="px-2 py-1">
                  <input type="checkbox" checked={!excluded.has(it.row)} onChange={() => onToggle(it.row)} />
                </td>
                <td className="px-2 py-1">{it.row}</td>
                <td className="px-2 py-1">{it.kategori || "-"}</td>
                <td className="px-2 py-1">{it.uraian}</td>
                <td className="px-2 py-1">{it.volume_satuan}</td>
                <td className="px-2 py-1 text-right">{formatRp(it.harga)}</td>
                <td className="px-2 py-1">{it.keterangan}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
