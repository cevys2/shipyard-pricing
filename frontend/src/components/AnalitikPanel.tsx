import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AlertTriangle, Info } from "lucide-react";
import {
  api,
  formatRp,
  type AuthUser,
  type AuditRow,
  type TrenJasa,
  type TrenMaterial,
} from "../lib/api";

/** Urutan tetap, tidak pernah diputar-ulang. Lolos validasi keterbacaan buta warna
 * (deutan/protan/tritan) dan kontras terhadap latar putih. Jangan tambah warna ke-7
 * dengan cara generate -- lebih baik kurangi jumlah seri. */
const WARNA_SERI = ["#2f6fb5", "#b8802c", "#0f9488", "#c0453a", "#7b52c4", "#6f8c1f"];
const MAKS_SERI = 6;

type Props = { auth: AuthUser };

export default function AnalitikPanel({ auth }: Props) {
  const [jasa, setJasa] = useState<TrenJasa | null>(null);
  const [material, setMaterial] = useState<TrenMaterial | null>(null);
  const [kategoriOpts, setKategoriOpts] = useState<string[]>(["Semua"]);
  const [kategori, setKategori] = useState("Semua");
  const [log, setLog] = useState<AuditRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [tj, tm, opts, lg] = await Promise.all([
        api.trenJasa(auth.token, { kategori }),
        api.trenMaterial(auth.token),
        api.trenJasaKategori(auth.token),
        api.auditLog(auth.token, { limit: 25 }),
      ]);
      setJasa(tj);
      setMaterial(tm);
      setKategoriOpts(opts);
      setLog(lg);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal memuat analitik");
    } finally {
      setLoading(false);
    }
  }, [auth.token, kategori]);

  useEffect(() => {
    load();
  }, [load]);

  /** Recharts butuh satu baris per titik sumbu-X dengan tiap seri sebagai kolom.
   * Kategori yang ditampilkan dibatasi MAKS_SERI teratas berdasar jumlah baris data --
   * 77 kategori di satu grafik cuma jadi benang kusut. */
  const { dataChart, seriTampil } = useMemo(() => {
    if (!jasa) return { dataChart: [], seriTampil: [] as string[] };

    const volume = new Map<string, number>();
    jasa.seri.forEach((s) => volume.set(s.kategori, (volume.get(s.kategori) ?? 0) + s.n_baris));
    const terpilih = [...volume.entries()]
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .slice(0, MAKS_SERI)
      .map(([k]) => k);

    const perTahun = new Map<string, Record<string, string | number>>();
    jasa.seri
      .filter((s) => terpilih.includes(s.kategori))
      .forEach((s) => {
        const baris = perTahun.get(s.tahun) ?? { tahun: s.tahun };
        baris[s.kategori] = s.median;
        perTahun.set(s.tahun, baris);
      });

    return {
      seriTampil: terpilih,
      dataChart: [...perTahun.values()].sort((a, b) => String(a.tahun).localeCompare(String(b.tahun))),
    };
  }, [jasa]);

  const kategoriTersembunyi = useMemo(() => {
    if (!jasa) return 0;
    return new Set(jasa.seri.map((s) => s.kategori)).size - seriTampil.length;
  }, [jasa, seriTampil]);

  if (loading) return <p className="p-8 text-center text-slate-500">Memuat analitik...</p>;
  if (error) return <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>;

  return (
    <div className="space-y-10">
      {/* ---------------- Tren harga material ---------------- */}
      <section>
        <h2 className="font-display text-lg font-bold text-slate-900">Tren Harga Material</h2>
        <p className="mt-1 text-sm text-slate-500">
          Grafik tren baru terbentuk untuk material yang punya lebih dari satu titik harga.
        </p>

        {material && (
          <>
            <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
              <Kpi label="Material" value={String(material.ringkas.total_material)} />
              <Kpi label="Total Titik Harga" value={String(material.ringkas.total_titik_harga)} />
              <Kpi
                label="Siap Ditampilkan Tren"
                value={`${material.ringkas.siap_tren} dari ${material.ringkas.total_material}`}
                accent
              />
            </div>

            {material.ringkas.siap_tren === 0 ? (
              <div className="mt-4 rounded-xl border border-dashed border-slate-300 px-5 py-8 text-center">
                <p className="text-sm font-medium text-slate-700">Belum ada tren harga material.</p>
                <p className="mx-auto mt-1 max-w-lg text-sm text-slate-500">
                  Setiap material baru punya satu titik harga, jadi belum ada yang bisa digambar sebagai
                  garis. Buka tab <strong>Katalog Material</strong> → tombol <strong>Riwayat</strong> di
                  baris material → <strong>Tambah Harga</strong> setiap kali ada quotation atau invoice
                  baru. Grafiknya muncul sendiri begitu satu material punya 2 titik.
                </p>
              </div>
            ) : (
              <div className="mt-4 overflow-hidden rounded-xl border border-slate-200">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                    <tr>
                      <th className="px-4 py-2.5">Material</th>
                      <th className="px-4 py-2.5">Spesifikasi</th>
                      <th className="px-4 py-2.5 text-right">Titik Harga</th>
                      <th className="px-4 py-2.5">Rentang</th>
                    </tr>
                  </thead>
                  <tbody>
                    {material.kandidat.map((k) => (
                      <tr key={k.id} className="border-t border-slate-100">
                        <td className="px-4 py-2 font-medium text-slate-800">{k.nama}</td>
                        <td className="px-4 py-2 text-slate-500">{k.spesifikasi || "-"}</td>
                        <td className="px-4 py-2 text-right">{k.n_harga}</td>
                        <td className="px-4 py-2 text-slate-500">
                          {k.dari} → {k.sampai}
                          {k.n_mata_uang > 1 && (
                            <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800">
                              campur mata uang
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </section>

      {/* ---------------- Tren harga jual jasa ---------------- */}
      <section>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="font-display text-lg font-bold text-slate-900">
              Tren Harga Jual Jasa (Realisasi)
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              Median harga satuan per kategori pekerjaan per tahun, dari data realisasi docking.
            </p>
          </div>
          <label className="block text-xs font-medium text-slate-600">
            Kategori
            <select
              className="mt-1 w-72 rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm outline-none focus:border-slate-400 focus:ring-2 focus:ring-blue-100"
              value={kategori}
              onChange={(e) => setKategori(e.target.value)}
            >
              {kategoriOpts.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </label>
        </div>

        <Peringatan>
          <strong>Baca grafik ini dengan hati-hati.</strong> Jumlah kapal per tahun berbeda jauh
          {jasa && (
            <>
              {" ("}
              {jasa.per_tahun.map((t, i) => (
                <span key={t.tahun}>
                  {i > 0 && ", "}
                  {t.tahun}: {t.n_kapal} kapal
                </span>
              ))}
              {")"}
            </>
          )}
          , jadi naik-turunnya garis bisa sekadar efek berubahnya campuran kapal — bukan bukti harga
          naik. Selain itu kategori masih mengandung duplikat penulisan (mis. &ldquo;DOCKING DAN
          UNDOCKING&rdquo; vs &ldquo;DOCKING AND UNDOCKING&rdquo;) karena pemetaan kategori kanonik
          belum dikerjakan.
        </Peringatan>

        {dataChart.length < 2 ? (
          <div className="mt-4 rounded-xl border border-dashed border-slate-300 px-5 py-8 text-center text-sm text-slate-500">
            Data yang lolos filter belum cukup untuk digambar sebagai tren (butuh minimal 2 tahun).
          </div>
        ) : (
          <div className="mt-4 rounded-xl border border-slate-200 p-5">
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={dataChart} margin={{ top: 5, right: 20, bottom: 5, left: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                <XAxis dataKey="tahun" tick={{ fontSize: 12, fill: "#64748b" }} tickMargin={8} />
                <YAxis
                  tick={{ fontSize: 12, fill: "#64748b" }}
                  width={72}
                  tickFormatter={(v: number) =>
                    new Intl.NumberFormat("id-ID", { notation: "compact" }).format(v)
                  }
                />
                <Tooltip
                  formatter={(v) => formatRp(Number(v))}
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }}
                />
                <Legend wrapperStyle={{ fontSize: 12, paddingTop: 12 }} />
                {seriTampil.map((k, i) => (
                  <Line
                    key={k}
                    type="monotone"
                    dataKey={k}
                    name={k}
                    stroke={WARNA_SERI[i]}
                    strokeWidth={2}
                    dot={{ r: 3.5, fill: WARNA_SERI[i] }}
                    activeDot={{ r: 5.5 }}
                    connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>

            {kategoriTersembunyi > 0 && (
              <p className="mt-3 flex items-center gap-1.5 text-xs text-slate-500">
                <Info size={13} />
                Menampilkan {seriTampil.length} kategori dengan data terbanyak; {kategoriTersembunyi}{" "}
                kategori lain disembunyikan. Pilih satu kategori di atas untuk melihatnya sendiri.
              </p>
            )}
          </div>
        )}

        {/* Angka mentahnya tetap bisa dibaca tanpa mengandalkan warna. */}
        {jasa && jasa.seri.length > 0 && (
          <details className="mt-3">
            <summary className="cursor-pointer text-sm font-medium text-slate-600 hover:text-slate-900">
              Lihat angkanya sebagai tabel ({jasa.seri.length} baris)
            </summary>
            <div className="mt-2 max-h-80 overflow-auto rounded-xl border border-slate-200">
              <table className="min-w-full text-left text-sm">
                <thead className="sticky top-0 bg-slate-50 text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-2.5">Kategori</th>
                    <th className="px-4 py-2.5">Tahun</th>
                    <th className="px-4 py-2.5 text-right">Median</th>
                    <th className="px-4 py-2.5 text-right">Baris</th>
                    <th className="px-4 py-2.5 text-right">Kapal</th>
                  </tr>
                </thead>
                <tbody>
                  {jasa.seri.map((s) => (
                    <tr key={`${s.kategori}-${s.tahun}`} className="border-t border-slate-100">
                      <td className="px-4 py-2">{s.kategori}</td>
                      <td className="px-4 py-2">{s.tahun}</td>
                      <td className="px-4 py-2 text-right font-medium">{formatRp(s.median)}</td>
                      <td className="px-4 py-2 text-right text-slate-500">{s.n_baris}</td>
                      <td className="px-4 py-2 text-right text-slate-500">{s.n_kapal}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        )}
      </section>

      {/* ---------------- Log perubahan ---------------- */}
      <section>
        <h2 className="font-display text-lg font-bold text-slate-900">Log Perubahan Data</h2>
        <p className="mt-1 text-sm text-slate-500">
          Siapa menambah, mengubah, atau menghapus data di Katalog Material dan Katalog Harga Jasa.
        </p>
        {log.length === 0 ? (
          <p className="mt-4 rounded-xl border border-dashed border-slate-300 px-5 py-8 text-center text-sm text-slate-500">
            Belum ada perubahan tercatat. Log mulai terisi dari perubahan berikutnya.
          </p>
        ) : (
          <div className="mt-4 overflow-hidden rounded-xl border border-slate-200">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-2.5">Waktu</th>
                  <th className="px-4 py-2.5">Pengguna</th>
                  <th className="px-4 py-2.5">Aksi</th>
                  <th className="px-4 py-2.5">Data</th>
                  <th className="px-4 py-2.5 text-right">Jumlah</th>
                </tr>
              </thead>
              <tbody>
                {log.map((r) => (
                  <tr key={r.id} className="border-t border-slate-100">
                    <td className="whitespace-nowrap px-4 py-2 text-slate-500">
                      {new Date(r.dibuat_pada).toLocaleString("id-ID")}
                    </td>
                    <td className="px-4 py-2 font-medium text-slate-800">{r.aktor}</td>
                    <td className="px-4 py-2">
                      <BadgeAksi aksi={r.aksi} />
                    </td>
                    <td className="px-4 py-2 text-slate-600">{LABEL_ENTITAS[r.entitas] ?? r.entitas}</td>
                    <td className="px-4 py-2 text-right">{r.jumlah}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

const LABEL_ENTITAS: Record<string, string> = {
  material: "Katalog Material",
  material_harga: "Riwayat Harga Material",
  katalog_harga: "Katalog Harga Jasa",
};

const GAYA_AKSI: Record<string, string> = {
  create: "bg-emerald-50 text-emerald-700",
  update: "bg-blue-50 text-blue-700",
  delete: "bg-red-50 text-red-700",
};

function BadgeAksi({ aksi }: { aksi: string }) {
  return (
    <span
      className={`rounded px-2 py-0.5 text-xs font-semibold ${GAYA_AKSI[aksi] ?? "bg-slate-100 text-slate-700"}`}
    >
      {aksi}
    </span>
  );
}

function Kpi({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div
      className="rounded-xl border border-slate-200 p-5 shadow-sm"
      style={accent ? { background: "var(--marine)" } : { background: "white" }}
    >
      <p
        className={`text-xs font-semibold uppercase tracking-wide ${accent ? "text-blue-100" : "text-slate-500"}`}
      >
        {label}
      </p>
      <p className={`mt-2 font-display text-2xl font-bold ${accent ? "text-white" : "text-slate-900"}`}>
        {value}
      </p>
    </div>
  );
}

function Peringatan({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-4 flex gap-2.5 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
      <AlertTriangle size={16} className="mt-0.5 shrink-0" />
      <p>{children}</p>
    </div>
  );
}
