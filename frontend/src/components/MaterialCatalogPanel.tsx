import { useCallback, useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import {
  api,
  type AuthUser,
  type MaterialFilterOptions,
  type MaterialRow,
  type MaterialStats,
} from "../lib/api";
import EditableMaterialTable from "./EditableMaterialTable";

type Props = { auth: AuthUser };

const emptyFilters: Record<string, string> = {
  supplier: "Semua",
  satuan: "Semua",
  kapal: "Semua",
  tahun: "Semua",
  search: "",
};

export default function MaterialCatalogPanel({ auth }: Props) {
  const [filters, setFilters] = useState(emptyFilters);
  const [filterOpts, setFilterOpts] = useState<MaterialFilterOptions | null>(null);
  const [rows, setRows] = useState<MaterialRow[]>([]);
  const [stats, setStats] = useState<MaterialStats | null>(null);
  const [loading, setLoading] = useState(true);

  const queryParams = useMemo(
    () => ({
      supplier: filters.supplier,
      satuan: filters.satuan,
      kapal: filters.kapal,
      tahun: filters.tahun,
      search: filters.search || undefined,
    }),
    [filters],
  );

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [data, st] = await Promise.all([
        api.material(auth.token, queryParams),
        api.materialStats(auth.token, queryParams),
      ]);
      setRows(data);
      setStats(st);
    } finally {
      setLoading(false);
    }
  }, [auth.token, queryParams]);

  useEffect(() => {
    api
      .materialFilters(auth.token, queryParams)
      .then((opts) => {
        setFilterOpts(opts);
        setFilters((prev) => {
          let changed = false;
          const next = { ...prev };
          (Object.keys(opts) as (keyof MaterialFilterOptions)[]).forEach((key) => {
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

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="font-display text-lg font-bold text-slate-900">Katalog Material</h2>
        <div className="relative w-72">
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            placeholder="Cari nama/spesifikasi material..."
            className="w-full rounded-lg border border-slate-300 py-2 pl-9 pr-3 text-sm outline-none focus:border-slate-400 focus:ring-2 focus:ring-blue-100"
            value={filters.search}
            onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
          />
        </div>
      </div>

      {stats && (
        <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard title="Total Material" value={String(stats.total_material)} accent />
          <KpiCard title="Total Supplier" value={String(stats.total_supplier)} />
          <KpiCard title="Total Kapal" value={String(stats.total_kapal)} />
          <KpiCard title="Update Harga Terakhir" value={stats.update_terakhir ?? "-"} />
        </div>
      )}

      {filterOpts && (
        <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-5">
          <FilterSelect
            label="Supplier"
            value={filters.supplier}
            options={filterOpts.supplier}
            onChange={(v) => setFilters((f) => ({ ...f, supplier: v }))}
          />
          <FilterSelect
            label="Satuan"
            value={filters.satuan}
            options={filterOpts.satuan}
            onChange={(v) => setFilters((f) => ({ ...f, satuan: v }))}
          />
          <FilterSelect
            label="Kapal"
            value={filters.kapal}
            options={filterOpts.kapal}
            onChange={(v) => setFilters((f) => ({ ...f, kapal: v }))}
          />
          <FilterSelect
            label="Tahun"
            value={filters.tahun}
            options={filterOpts.tahun}
            onChange={(v) => setFilters((f) => ({ ...f, tahun: v }))}
          />
        </div>
      )}

      <EditableMaterialTable token={auth.token} rows={rows} loading={loading} onChanged={refresh} />
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
