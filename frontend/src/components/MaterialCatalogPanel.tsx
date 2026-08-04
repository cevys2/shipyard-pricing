import { useCallback, useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import {
  api,
  pakaiKolomPembelian,
  JENIS_SUMBER_DAYA,
  type AuthUser,
  type JenisSumberDaya,
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

const JUDUL: Record<JenisSumberDaya, string> = {
  BAHAN: "Katalog Material",
  UPAH: "Katalog Upah",
  ALAT: "Katalog Alat",
  KONSUMABEL: "Katalog Konsumabel",
};

export default function MaterialCatalogPanel({ auth }: Props) {
  const [jenis, setJenis] = useState<JenisSumberDaya>("BAHAN");
  const [filters, setFilters] = useState(emptyFilters);
  const [filterOpts, setFilterOpts] = useState<MaterialFilterOptions | null>(null);
  const [rows, setRows] = useState<MaterialRow[]>([]);
  const [stats, setStats] = useState<MaterialStats | null>(null);
  const [loading, setLoading] = useState(true);

  const adaPembelian = pakaiKolomPembelian(jenis);

  const queryParams = useMemo(
    () => ({
      jenis,
      supplier: filters.supplier,
      satuan: filters.satuan,
      kapal: filters.kapal,
      tahun: filters.tahun,
      search: filters.search || undefined,
    }),
    [jenis, filters],
  );

  /** Filter lama tidak boleh terbawa ke jenis lain -- supplier "PT MAN" itu milik bahan,
   * dan membiarkannya aktif waktu pindah ke Upah bikin tabel kosong tanpa sebab yang jelas. */
  function gantiJenis(baru: JenisSumberDaya) {
    if (baru === jenis) return;
    setJenis(baru);
    setFilters(emptyFilters);
    setFilterOpts(null);
  }

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
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-lg font-bold text-slate-900">{JUDUL[jenis]}</h2>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex rounded-lg border border-slate-300 bg-white p-0.5">
            {JENIS_SUMBER_DAYA.map((j) => (
              <button
                key={j.nilai}
                type="button"
                onClick={() => gantiJenis(j.nilai)}
                aria-pressed={jenis === j.nilai}
                className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
                  jenis === j.nilai ? "text-white" : "text-slate-600 hover:text-slate-900"
                }`}
                style={jenis === j.nilai ? { background: "var(--marine)" } : undefined}
              >
                {j.label}
              </button>
            ))}
          </div>
          <div className="relative w-72">
            <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              placeholder="Cari nama/spesifikasi..."
              className="w-full rounded-lg border border-slate-300 py-2 pl-9 pr-3 text-sm outline-none focus:border-slate-400 focus:ring-2 focus:ring-blue-100"
              value={filters.search}
              onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
            />
          </div>
        </div>
      </div>

      {jenis !== "BAHAN" && (
        <p className="mb-4 text-xs text-slate-500">
          {jenis === "UPAH"
            ? "Tarif tenaga kerja sendiri, satuan OH (Orang-Hari, 8 jam kerja)."
            : jenis === "ALAT"
              ? "Tarif internal alat milik sendiri -- sudah termasuk bahan bakar dan penyusutan."
              : "Bahan habis pakai: oksigen, elektroda, dan sejenisnya."}{" "}
          Baris di sini tidak muncul di tab Bahan, dan tidak ikut grafik tren harga material.
        </p>
      )}

      {stats && (
        <div
          className={`mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 ${adaPembelian ? "xl:grid-cols-4" : "xl:grid-cols-2"}`}
        >
          <KpiCard title={`Total ${JUDUL[jenis].replace("Katalog ", "")}`} value={String(stats.total_material)} accent />
          {adaPembelian && <KpiCard title="Total Supplier" value={String(stats.total_supplier)} />}
          {adaPembelian && <KpiCard title="Total Kapal" value={String(stats.total_kapal)} />}
          <KpiCard title="Update Harga Terakhir" value={stats.update_terakhir ?? "-"} />
        </div>
      )}

      {filterOpts && (
        <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-5">
          {adaPembelian && (
            <FilterSelect
              label="Supplier"
              value={filters.supplier}
              options={filterOpts.supplier}
              onChange={(v) => setFilters((f) => ({ ...f, supplier: v }))}
            />
          )}
          <FilterSelect
            label="Satuan"
            value={filters.satuan}
            options={filterOpts.satuan}
            onChange={(v) => setFilters((f) => ({ ...f, satuan: v }))}
          />
          {adaPembelian && (
            <FilterSelect
              label="Kapal"
              value={filters.kapal}
              options={filterOpts.kapal}
              onChange={(v) => setFilters((f) => ({ ...f, kapal: v }))}
            />
          )}
          <FilterSelect
            label="Tahun"
            value={filters.tahun}
            options={filterOpts.tahun}
            onChange={(v) => setFilters((f) => ({ ...f, tahun: v }))}
          />
        </div>
      )}

      {/* key={jenis} sengaja: ganti jenis harus mereset halaman, seleksi baris, mode edit,
          dan draf paste yang masih menempel dari jenis sebelumnya. Melewatkannya lewat prop
          berarti empat state itu harus dibersihkan satu per satu dan gampang ada yang lupa. */}
      <EditableMaterialTable
        key={jenis}
        token={auth.token}
        jenis={jenis}
        rows={rows}
        loading={loading}
        onChanged={refresh}
      />
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
