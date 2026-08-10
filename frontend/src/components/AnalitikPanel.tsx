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
  formatMoney,
  formatRp,
  type AuthUser,
  type AuditRow,
  type TrenJasa,
  type TrenJasaPoint,
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

  // Penyaringan grafik material dikerjakan di sisi klien: seluruh titik harga kandidat
  // sudah ikut terkirim, jumlahnya kecil, dan ini bikin ganti pilihan terasa seketika
  // tanpa bolak-balik ke server.
  const [supplierMat, setSupplierMat] = useState("Semua");
  /** null = semua material. Set kosong = tidak ada yang dipilih. */
  const [pilihMat, setPilihMat] = useState<Set<number> | null>(null);

  const supplierMatOpts = useMemo(() => {
    const s = new Set<string>();
    material?.titik.forEach((t) => t.supplier_nama && s.add(t.supplier_nama));
    return ["Semua", ...[...s].sort()];
  }, [material]);

  /** Kandidat yang lolos filter supplier DAN dipilih pengguna. Filter supplier bekerja di
   * tingkat material: sebuah material ikut kalau punya minimal satu titik harga dari
   * supplier itu -- kalau disaring per titik, garis tren bisa terpotong separuh dan
   * terlihat seperti harga turun padahal cuma datanya yang disembunyikan. */
  const kandidatTampil = useMemo(() => {
    if (!material) return [];
    const punyaSupplier = new Set(
      material.titik.filter((t) => t.supplier_nama === supplierMat).map((t) => t.sumber_daya_id),
    );
    return material.kandidat.filter(
      (k) =>
        (supplierMat === "Semua" || punyaSupplier.has(k.id)) &&
        (pilihMat === null || pilihMat.has(k.id)),
    );
  }, [material, supplierMat, pilihMat]);

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
   * Kategori yang ditampilkan dibatasi MAKS_SERI teratas berdasar jumlah baris data.
   * Sejak kategori kanonik dipakai, jumlahnya 11 dan bukan lagi 78, jadi batas ini
   * jarang tersentuh -- tetap dipertahankan karena master kategori boleh bertambah. */
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

  /** Satu grafik per mata uang. EUR dan IDR tidak boleh berbagi sumbu Y -- selisihnya
   * ribuan kali dan garisnya jadi tak terbaca, selain memberi kesan angkanya sebanding. */
  const grafikMaterial = useMemo(() => {
    if (!material || kandidatTampil.length === 0) return [];

    const namaPer = new Map(kandidatTampil.map((k) => [k.id, k.nama]));
    const idTampil = new Set(kandidatTampil.map((k) => k.id));
    const perMataUang = new Map<string, Map<string, Record<string, string | number>>>();
    const seriPer = new Map<string, Set<string>>();

    material.titik.forEach((t) => {
      if (!idTampil.has(t.sumber_daya_id)) return;
      if (supplierMat !== "Semua" && t.supplier_nama !== supplierMat) return;
      const nama = namaPer.get(t.sumber_daya_id);
      if (!nama) return;
      if (!perMataUang.has(t.mata_uang)) {
        perMataUang.set(t.mata_uang, new Map());
        seriPer.set(t.mata_uang, new Set());
      }
      const perTanggal = perMataUang.get(t.mata_uang)!;
      const baris = perTanggal.get(t.berlaku_dari) ?? { tanggal: t.berlaku_dari };
      baris[nama] = t.harga_satuan;
      perTanggal.set(t.berlaku_dari, baris);
      seriPer.get(t.mata_uang)!.add(nama);
    });

    return [...perMataUang.entries()].map(([mataUang, perTanggal]) => ({
      mataUang,
      seri: [...seriPer.get(mataUang)!],
      data: [...perTanggal.values()].sort((a, b) =>
        String(a.tanggal).localeCompare(String(b.tanggal)),
      ),
    }));
  }, [material, kandidatTampil, supplierMat]);

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
              <>
                <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <div className="flex flex-wrap items-end gap-3">
                    <label className="block text-xs font-medium text-slate-600">
                      Supplier
                      <select
                        className="mt-1 w-64 rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm"
                        value={supplierMat}
                        onChange={(e) => setSupplierMat(e.target.value)}
                      >
                        {supplierMatOpts.map((s) => (
                          <option key={s} value={s}>
                            {s}
                          </option>
                        ))}
                      </select>
                    </label>
                    <p className="pb-2 text-xs text-slate-500">
                      {kandidatTampil.length} dari {material.kandidat.length} material ditampilkan
                    </p>
                  </div>

                  <p className="mt-3 text-xs font-medium text-slate-600">Material</p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {material.kandidat.map((k) => {
                      const aktif = pilihMat === null || pilihMat.has(k.id);
                      return (
                        <button
                          key={k.id}
                          type="button"
                          aria-pressed={aktif}
                          onClick={() =>
                            setPilihMat((prev) => {
                              const dasar = prev ?? new Set(material.kandidat.map((x) => x.id));
                              const next = new Set(dasar);
                              if (next.has(k.id)) next.delete(k.id);
                              else next.add(k.id);
                              return next;
                            })
                          }
                          className={`rounded-full border px-2.5 py-1 text-xs transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 ${
                            aktif
                              ? "border-transparent bg-slate-800 text-white"
                              : "border-slate-300 bg-white text-slate-500 hover:border-slate-400"
                          }`}
                        >
                          {k.nama}
                        </button>
                      );
                    })}
                    {pilihMat !== null && (
                      <button
                        type="button"
                        onClick={() => setPilihMat(null)}
                        className="rounded-full px-2.5 py-1 text-xs text-slate-500 underline hover:text-slate-800"
                      >
                        tampilkan semua
                      </button>
                    )}
                  </div>
                </div>

                {kandidatTampil.length === 0 && (
                  <p className="mt-4 rounded-xl border border-dashed border-slate-300 px-5 py-8 text-center text-sm text-slate-500">
                    Tidak ada material yang cocok dengan pilihan di atas.
                  </p>
                )}

                {grafikMaterial.map(({ mataUang, data, seri }) => (
                  <div key={mataUang} className="mt-4 rounded-xl border border-slate-200 p-5">
                    <p className="mb-3 text-sm font-medium text-slate-700">
                      Harga satuan dalam {mataUang}
                    </p>
                    <ResponsiveContainer width="100%" height={300}>
                      <LineChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 8 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                        <XAxis dataKey="tanggal" tick={{ fontSize: 12, fill: "#64748b" }} tickMargin={8} />
                        <YAxis
                          tick={{ fontSize: 12, fill: "#64748b" }}
                          width={64}
                          tickFormatter={(v: number) =>
                            new Intl.NumberFormat("id-ID", { notation: "compact" }).format(v)
                          }
                        />
                        <Tooltip
                          formatter={(v, n) => [formatMoney(Number(v), mataUang), String(n)]}
                          contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }}
                        />
                        <Legend wrapperStyle={{ fontSize: 12, paddingTop: 12 }} />
                        {seri.map((s, i) => (
                          <Line
                            key={s}
                            type="monotone"
                            dataKey={s}
                            name={s}
                            stroke={WARNA_SERI[i % WARNA_SERI.length]}
                            strokeWidth={2}
                            dot={{ r: 3.5, fill: WARNA_SERI[i % WARNA_SERI.length] }}
                            activeDot={{ r: 5.5 }}
                            connectNulls
                          />
                        ))}
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                ))}

                <div className="mt-3 overflow-x-auto rounded-xl border border-slate-200">
                  <table className="min-w-full text-left text-sm">
                    <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                      <tr>
                        <th className="px-4 py-2.5">Material</th>
                        <th className="px-4 py-2.5">Spesifikasi</th>
                        <th className="px-4 py-2.5 text-right">Titik</th>
                        <th className="px-4 py-2.5 text-right">Harga Awal</th>
                        <th className="px-4 py-2.5 text-right">Harga Akhir</th>
                        <th className="px-4 py-2.5 text-right">Perubahan</th>
                        <th className="px-4 py-2.5">Rentang</th>
                      </tr>
                    </thead>
                    <tbody>
                      {kandidatTampil.map((k) => (
                        <tr key={k.id} className="border-t border-slate-100">
                          <td className="px-4 py-2 font-medium text-slate-800">{k.nama}</td>
                          <td className="px-4 py-2 font-mono text-xs text-slate-500">
                            {k.spesifikasi || "-"}
                          </td>
                          <td className="px-4 py-2 text-right tabular-nums">{k.n_harga}</td>
                          <td className="px-4 py-2 text-right tabular-nums text-slate-600">
                            {formatMoney(k.harga_awal, k.mata_uang)}
                          </td>
                          <td className="px-4 py-2 text-right tabular-nums text-slate-800">
                            {formatMoney(k.harga_akhir, k.mata_uang)}
                          </td>
                          <td className="px-4 py-2 text-right tabular-nums">
                            {k.perubahan_persen == null ? (
                              <span className="text-slate-400">-</span>
                            ) : (
                              <span
                                className={
                                  k.perubahan_persen > 0
                                    ? "font-semibold text-red-700"
                                    : k.perubahan_persen < 0
                                      ? "font-semibold text-emerald-700"
                                      : "text-slate-500"
                                }
                              >
                                {k.perubahan_persen > 0 ? "+" : ""}
                                {k.perubahan_persen.toFixed(2)}%
                              </span>
                            )}
                          </td>
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
              </>
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
          naik.
          {jasa && jasa.cakupan.tanpa_kategori > 0 && (
            <>
              {" "}
              Selain itu {jasa.cakupan.tanpa_kategori.toLocaleString("id-ID")} baris belum punya
              kategori kanonik dan sama sekali tidak masuk grafik ini — biasanya karena impor
              terakhir memakai sebutan kategori yang belum ada padanannya.
            </>
          )}
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
                <Tooltip content={<TooltipJasa seri={jasa?.seri ?? []} />} />
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
                    <th className="px-4 py-2.5 text-right">Rentang</th>
                    <th className="px-4 py-2.5 text-right">Baris</th>
                    <th className="px-4 py-2.5">Kapal yang menyusun median</th>
                  </tr>
                </thead>
                <tbody>
                  {jasa.seri.map((s) => (
                    <tr key={`${s.kategori}-${s.tahun}`} className="border-t border-slate-100 align-top">
                      <td className="px-4 py-2">{s.kategori}</td>
                      <td className="px-4 py-2 tabular-nums">{s.tahun}</td>
                      <td className="px-4 py-2 text-right font-medium tabular-nums">
                        {formatRp(s.median)}
                      </td>
                      <td className="whitespace-nowrap px-4 py-2 text-right text-xs tabular-nums text-slate-500">
                        {formatRp(s.minimum)} – {formatRp(s.maksimum)}
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums text-slate-500">{s.n_baris}</td>
                      <td className="px-4 py-2 text-xs text-slate-600">
                        <DaftarKapal kapal={s.kapal} n={s.n_kapal} />
                      </td>
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

/** Tooltip kustom, bukan `formatter` + `labelFormatter`: keduanya dipanggil terpisah dan
 * urutannya tidak dijamin, jadi menitipkan tahun dari satu ke lainnya mudah rusak. Komponen
 * ini menerima label (tahun) dan payload (nilai tiap kategori) sekaligus, sehingga jumlah
 * baris dan kapal penyusun median bisa ikut ditampilkan dengan andal. */
function TooltipJasa({
  seri,
  active,
  label,
  payload,
}: {
  seri: TrenJasaPoint[];
  active?: boolean;
  label?: string | number;
  payload?: { name?: string | number; value?: string | number }[];
}) {
  if (!active || !payload?.length) return null;
  const tahun = String(label);

  return (
    <div className="max-w-xs rounded-lg border border-slate-200 bg-white p-2.5 text-xs shadow-lg">
      <p className="mb-1.5 font-semibold text-slate-900">Tahun {tahun}</p>
      <div className="flex flex-col gap-1.5">
        {payload.map((p) => {
          const nama = String(p.name);
          const s = seri.find((x) => x.kategori === nama && x.tahun === tahun);
          return (
            <div key={nama}>
              <p className="font-medium text-slate-700">{nama}</p>
              <p className="tabular-nums text-slate-900">{formatRp(Number(p.value))}</p>
              {s && (
                <p className="text-slate-500">
                  {s.n_baris} baris · {s.n_kapal} kapal
                  {s.n_kapal === 1 && s.kapal?.[0] ? ` (${s.kapal[0]})` : ""}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Median dari 2 kapal dan median dari 20 kapal punya bobot yang sangat berbeda, tapi
 * angkanya terlihat sama meyakinkan. Daftar kapalnya ditampilkan supaya bobot itu kelihatan
 * tanpa harus menebak. */
function DaftarKapal({ kapal, n }: { kapal: string[] | null; n: number }) {
  const [buka, setBuka] = useState(false);
  const list = kapal ?? [];
  if (list.length === 0) return <span className="text-slate-400">tidak tercatat</span>;

  const BATAS = 3;
  const tampil = buka ? list : list.slice(0, BATAS);
  const sisa = list.length - tampil.length;

  return (
    <span className="flex flex-wrap items-center gap-1">
      {n === 1 && (
        <span className="mr-1 rounded bg-amber-100 px-1.5 py-0.5 font-medium text-amber-800">
          1 kapal saja
        </span>
      )}
      {tampil.map((k) => (
        <span key={k} className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-700">
          {k}
        </span>
      ))}
      {sisa > 0 && (
        <button
          type="button"
          onClick={() => setBuka(true)}
          className="rounded px-1 text-slate-500 underline hover:text-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1"
        >
          +{sisa} lagi
        </button>
      )}
      {buka && list.length > BATAS && (
        <button
          type="button"
          onClick={() => setBuka(false)}
          className="rounded px-1 text-slate-500 underline hover:text-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1"
        >
          ringkas
        </button>
      )}
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
