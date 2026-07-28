import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, LayoutGrid, LogOut, Package, Search, Upload } from "lucide-react";
import {
  api,
  PORTAL_URL,
  type AuthUser,
  type CatalogRow,
  type CatalogStats,
  type FilterOptions,
} from "../lib/api";
import EditableCatalogTable from "../components/EditableCatalogTable";
import DockingImportPanel from "../components/DockingImportPanel";
import MaterialCatalogPanel from "../components/MaterialCatalogPanel";
import logoFull from "../assets/logo-full.png";
import logoIcon from "../assets/logo-icon.png";

type Props = { auth: AuthUser; onLogout: () => void };

type Tab = "view" | "material" | "import";

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
  const [importMode, setImportMode] = useState<"docking" | "flat">("docking");

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
    api
      .filters(auth.token, queryParams)
      .then((opts) => {
        setFilterOpts(opts);
        // kalau value yang lagi dipilih sekarang nggak ada lagi di opsi baru (karena filter lain
        // udah mempersempit), reset ke "Semua" - tapi cuma setState kalau BENERAN ada yang berubah,
        // supaya nggak bikin infinite loop (objek baru tiap render -> effect jalan lagi -> ...)
        setFilters((prev) => {
          let changed = false;
          const next = { ...prev };
          (Object.keys(opts) as (keyof FilterOptions)[]).forEach((key) => {
            if (prev[key] !== "Semua" && !opts[key].includes(prev[key])) {
              next[key] = "Semua";
              changed = true;
            }
          });
          return changed ? next : prev;
        });
      })
      .catch(console.error);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth.token, queryParams]);

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

  const navItems: { key: Tab; label: string; icon: typeof LayoutGrid }[] = [
    { key: "view", label: "Dashboard & Data", icon: LayoutGrid },
    { key: "material", label: "Katalog Material", icon: Package },
    { key: "import", label: "Import Excel", icon: Upload },
  ];

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-64 flex-col text-white" style={{ background: "var(--ink)" }}>
        <div className="border-b border-white/10 px-5 py-6">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-white p-1.5">
              <img src={logoIcon} alt="" className="h-full w-full object-contain" />
            </div>
            <div>
              <p className="font-display text-lg font-bold tracking-tight">DUKUH RAYA</p>
              <p className="text-xs text-slate-400">Docking Repair Pricing</p>
            </div>
          </div>
        </div>
        <nav className="flex-1 space-y-1 p-3 text-sm">
          {navItems.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-left transition-colors ${
                tab === key ? "font-semibold text-white" : "text-slate-300 hover:bg-white/5 hover:text-white"
              }`}
              style={tab === key ? { background: "var(--marine)" } : undefined}
            >
              <Icon size={16} />
              {label}
            </button>
          ))}
        </nav>
        <div className="border-t border-white/10 p-4 text-xs text-slate-300">
          <p className="font-semibold text-white">{auth.username.toUpperCase()}</p>
          <p className="opacity-70">{auth.role}</p>
          {/* Pindah app tanpa mengakhiri sesi - beda dari Logout di bawahnya. */}
          <button
            type="button"
            onClick={() => {
              window.location.href = PORTAL_URL;
            }}
            className="btn btn-sm mt-3 w-full justify-center text-slate-300 hover:bg-white/5 hover:text-white"
          >
            <ArrowLeft size={13} />
            Kembali ke Portal
          </button>
          <button type="button" onClick={onLogout} className="btn btn-danger-solid btn-sm mt-1.5 w-full justify-center">
            <LogOut size={13} />
            Logout
          </button>
        </div>
      </aside>

      <div className="flex flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-4">
          <div className="flex items-center gap-3">
            <img src={logoFull} alt="PT Dukuh Raya Shipyard" className="h-9 w-auto" />
            <span className="h-8 w-px bg-slate-200" />
            <h2 className="font-display text-lg font-bold text-slate-900">Overview Dashboard</h2>
          </div>
          <div className="relative w-72">
            <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              placeholder="Cari uraian pekerjaan..."
              className="w-full rounded-lg border border-slate-300 py-2 pl-9 pr-3 text-sm outline-none focus:border-slate-400 focus:ring-2 focus:ring-blue-100"
              value={filters.search}
              onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
            />
          </div>
        </header>

        <main className="flex-1 p-6">
          {stats && tab === "view" && (
            <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <KpiCard title="Total Item" value={String(stats.total_item)} accent />
              <KpiCard title="Total Klien" value={String(stats.total_klien)} />
              <KpiCard title="Total Kapal" value={String(stats.total_kapal)} />
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

              <EditableCatalogTable
                token={auth.token}
                rows={rows}
                filterOpts={filterOpts}
                loading={loading}
                onChanged={refresh}
              />
            </>
          )}

          {tab === "material" && <MaterialCatalogPanel auth={auth} />}

          {tab === "import" && (
            <div className="max-w-3xl rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
              <div className="mb-5 flex gap-2">
                <button
                  type="button"
                  onClick={() => setImportMode("docking")}
                  className={`btn btn-sm ${importMode === "docking" ? "btn-primary" : "btn-secondary"}`}
                >
                  Laporan Docking (otomatis Induk/Addendum)
                </button>
                <button
                  type="button"
                  onClick={() => setImportMode("flat")}
                  className={`btn btn-sm ${importMode === "flat" ? "btn-primary" : "btn-secondary"}`}
                >
                  Format Rapi (kolom sudah bersih)
                </button>
              </div>

              {importMode === "docking" ? (
                <>
                  <h3 className="font-display text-lg font-bold text-slate-900">
                    Import file laporan "REALISASI BIAYA DOCKING"
                  </h3>
                  <p className="mt-2 text-sm text-slate-600">
                    Otomatis pisah baris ke <strong>Induk</strong> vs <strong>Addendum</strong> berdasarkan kata
                    "tambahan" di kolom Keterangan. Preview dulu sebelum simpan - baris yang meragukan ditandai
                    dan bisa diedit manual.
                  </p>
                  <div className="mt-6">
                    <DockingImportPanel token={auth.token} onImported={refresh} />
                  </div>
                </>
              ) : (
                <>
                  <h3 className="font-display text-lg font-bold text-slate-900">
                    Import otomatis dari Excel / CSV (kolom rapi)
                  </h3>
                  <p className="mt-2 text-sm text-slate-600">
                    Kolom wajib: <strong>Uraian Pekerjaan</strong>, plus <strong>Nama Kapal</strong> dan{" "}
                    <strong>Tahun</strong> (boleh diisi sama di setiap baris).
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
                </>
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function KpiCard({ title, value, accent }: { title: string; value: string; accent?: boolean }) {
  return (
    <div
      className="rounded-xl border border-slate-200 p-5 shadow-sm"
      style={accent ? { background: "var(--marine)" } : { background: "white" }}
    >
      <p className={`text-xs font-semibold uppercase tracking-wide ${accent ? "text-blue-100" : "text-slate-500"}`}>
        {title}
      </p>
      <p className={`mt-2 font-display text-3xl font-bold ${accent ? "text-white" : "text-slate-900"}`}>{value}</p>
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
        className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm outline-none focus:border-slate-400 focus:ring-2 focus:ring-blue-100"
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
