import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  formatRp,
  type AuthUser,
  type CatalogRow,
  type CatalogStats,
  type FilterOptions,
} from "../lib/api";

type Props = { auth: AuthUser; onLogout: () => void };

type Tab = "view" | "import";

const emptyFilters: Record<string, string> = {
  perusahaan: "Semua",
  kapal: "Semua",
  kategori: "Semua",
  tahun: "Semua",
  tipe: "Semua",
  search: "",
};

export default function DashboardPage({ auth, onLogout }: Props) {
  const [tab, setTab] = useState<Tab>("view");
  const [filters, setFilters] = useState(emptyFilters);
  const [filterOpts, setFilterOpts] = useState<FilterOptions | null>(null);
  const [rows, setRows] = useState<CatalogRow[]>([]);
  const [stats, setStats] = useState<CatalogStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [importMsg, setImportMsg] = useState("");

  const queryParams = useMemo(
    () => ({
      perusahaan: filters.perusahaan,
      kapal: filters.kapal,
      kategori: filters.kategori,
      tahun: filters.tahun,
      tipe: filters.tipe,
      search: filters.search || undefined,
    }),
    [filters],
  );

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [data, st] = await Promise.all([
        api.catalog(auth.token, queryParams),
        api.stats(auth.token, queryParams),
      ]);
      setRows(data);
      setStats(st);
    } finally {
      setLoading(false);
    }
  }, [auth.token, queryParams]);

  useEffect(() => {
    api.filters(auth.token).then(setFilterOpts).catch(console.error);
  }, [auth.token]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function onImport(file: File) {
    setImportMsg("");
    try {
      const preview = await api.importFile(auth.token, file, true);
      if (!preview.valid) {
        setImportMsg("File tidak valid");
        return;
      }
      const saved = await api.importFile(auth.token, file, false);
      setImportMsg(`Berhasil import ${saved.saved ?? 0} baris.`);
      await refresh();
    } catch (e) {
      setImportMsg(e instanceof Error ? e.message : "Import gagal");
    }
  }

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-64 flex-col bg-[#1e3a8a] text-white">
        <div className="border-b border-blue-800 px-5 py-6">
          <p className="text-lg font-bold">DUKUH RAYA</p>
          <p className="text-xs text-blue-200">Maintenance Catalog</p>
        </div>
        <nav className="flex-1 space-y-1 p-3 text-sm">
          <button
            type="button"
            onClick={() => setTab("view")}
            className={`w-full rounded-lg px-3 py-2 text-left ${tab === "view" ? "bg-blue-600 font-semibold" : "hover:bg-blue-800"}`}
          >
            Dashboard & Data
          </button>
          <button
            type="button"
            onClick={() => setTab("import")}
            className={`w-full rounded-lg px-3 py-2 text-left ${tab === "import" ? "bg-blue-600 font-semibold" : "hover:bg-blue-800"}`}
          >
            Import Excel
          </button>
        </nav>
        <div className="border-t border-blue-800 p-4 text-xs text-blue-100">
          <p className="font-semibold">{auth.username.toUpperCase()}</p>
          <p className="opacity-80">{auth.role}</p>
          <button
            type="button"
            onClick={onLogout}
            className="mt-3 w-full rounded-lg bg-red-600 py-2 text-xs font-bold hover:bg-red-500"
          >
            Logout
          </button>
        </div>
      </aside>

      <div className="flex flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-4">
          <h2 className="text-xl font-bold text-slate-900">Overview Dashboard</h2>
          <input
            placeholder="Cari uraian pekerjaan..."
            className="w-72 rounded-lg border border-slate-300 px-3 py-2 text-sm"
            value={filters.search}
            onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
          />
        </header>

        <main className="flex-1 p-6">
          {stats && (
            <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <KpiCard title="Total Item" value={String(stats.total_item)} accent="bg-blue-600 text-white" />
              <KpiCard title="Total Klien" value={String(stats.total_klien)} />
              <KpiCard title="Kapal" value={String(stats.total_kapal)} />
              <KpiCard title="Tahun Referensi" value={String(stats.total_tahun)} />
            </div>
          )}

          {filterOpts && tab === "view" && (
            <>
              <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-5">
                <FilterSelect
                  label="Klien"
                  value={filters.perusahaan}
                  options={filterOpts.perusahaan}
                  onChange={(v) => setFilters((f) => ({ ...f, perusahaan: v }))}
                />
                <FilterSelect
                  label="Kapal"
                  value={filters.kapal}
                  options={filterOpts.kapal}
                  onChange={(v) => setFilters((f) => ({ ...f, kapal: v }))}
                />
                <FilterSelect
                  label="Kategori"
                  value={filters.kategori}
                  options={filterOpts.kategori}
                  onChange={(v) => setFilters((f) => ({ ...f, kategori: v }))}
                />
                <FilterSelect
                  label="Tahun"
                  value={filters.tahun}
                  options={filterOpts.tahun}
                  onChange={(v) => setFilters((f) => ({ ...f, tahun: v }))}
                />
                <FilterSelect
                  label="Tipe"
                  value={filters.tipe}
                  options={filterOpts.tipe}
                  onChange={(v) => setFilters((f) => ({ ...f, tipe: v }))}
                />
              </div>

              <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
                {loading ? (
                  <p className="p-8 text-center text-slate-500">Memuat data...</p>
                ) : (
                  <div className="max-h-[560px] overflow-auto">
                    <table className="min-w-full text-left text-sm">
                      <thead className="sticky top-0 bg-slate-50 text-xs uppercase text-slate-500">
                        <tr>
                          <th className="px-4 py-3">Perusahaan</th>
                          <th className="px-4 py-3">Kapal</th>
                          <th className="px-4 py-3">Tipe</th>
                          <th className="px-4 py-3">Tahun</th>
                          <th className="px-4 py-3">Kategori</th>
                          <th className="px-4 py-3">Uraian</th>
                          <th className="px-4 py-3">Satuan</th>
                          <th className="px-4 py-3 text-right">Harga</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((r) => (
                          <tr key={r.id} className="border-t border-slate-100 hover:bg-slate-50">
                            <td className="px-4 py-2">{r.nama_perusahaan}</td>
                            <td className="px-4 py-2">{r.nama_kapal}</td>
                            <td className="px-4 py-2">{r.tipe_perjanjian}</td>
                            <td className="px-4 py-2">{r.tahun}</td>
                            <td className="px-4 py-2">{r.kategori_pekerjaan}</td>
                            <td className="px-4 py-2">{r.uraian_pekerjaan}</td>
                            <td className="px-4 py-2">{r.volume_satuan}</td>
                            <td className="px-4 py-2 text-right font-medium">{formatRp(r.harga_satuan)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          )}

          {tab === "import" && (
            <div className="max-w-xl rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
              <h3 className="text-lg font-bold">Import otomatis dari Excel / CSV</h3>
              <p className="mt-2 text-sm text-slate-600">
                Kolom wajib: <strong>Uraian Pekerjaan</strong>, plus <strong>Nama Kapal</strong> dan{" "}
                <strong>Tahun</strong> (boleh diisi sama di setiap baris). Backend validasi pakai Pydantic
                sebelum simpan ke Supabase.
              </p>
              <input
                type="file"
                accept=".xlsx,.xls,.csv"
                className="mt-6 block w-full text-sm"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) void onImport(f);
                }}
              />
              {importMsg && <p className="mt-4 text-sm text-slate-700">{importMsg}</p>}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function KpiCard({
  title,
  value,
  accent,
}: {
  title: string;
  value: string;
  accent?: string;
}) {
  const highlighted = accent ?? "bg-white";
  return (
    <div className={`rounded-xl border border-slate-200 p-5 shadow-sm ${highlighted}`}>
      <p className={`text-xs font-semibold uppercase tracking-wide ${accent ? "text-blue-100" : "text-slate-500"}`}>
        {title}
      </p>
      <p className={`mt-2 text-3xl font-extrabold ${accent ? "text-white" : "text-slate-900"}`}>{value}</p>
    </div>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="block text-xs font-medium text-slate-600">
      {label}
      <select
        className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </label>
  );
}
