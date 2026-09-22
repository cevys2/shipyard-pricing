import { useCallback, useEffect, useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AlertTriangle, Plus, Trash2, X } from "lucide-react";
import {
  api,
  formatBulanTahun,
  formatMoney,
  formatTanggal,
  formatTanggalDariEpoch,
  tahunDari,
  type Currency,
  type MaterialRow,
  type PriceHistoryRow,
  type PriceInput,
} from "../lib/api";

const CURRENCIES: Currency[] = ["IDR", "EUR", "USD"];
const CURRENT_YEAR = new Date().getFullYear();

type Props = {
  token: string;
  material: MaterialRow;
  onClose: () => void;
  onChanged: () => void;
};

function emptyForm(m: MaterialRow): PriceInput {
  // Pra-isi dari harga terkini: yang biasanya berubah cuma angka harganya, supplier &
  // kapal umumnya sama. Tanggal sengaja dikosongkan supaya user sadar mengisinya --
  // tanggal itu sumbu-X grafik tren, salah isi = tren ikut salah.
  return {
    harga_satuan: 0,
    mata_uang: (m.mata_uang as Currency) ?? "IDR",
    tahun_pembelian: CURRENT_YEAR,
    supplier_nama: m.supplier_nama ?? "",
    nama_kapal: m.nama_kapal ?? "",
    berlaku_dari: "",
    sumber: "",
    no_dokumen: "",
    catatan: "",
  };
}

export default function PriceHistoryDrawer({ token, material, onClose, onChanged }: Props) {
  const [rows, setRows] = useState<PriceHistoryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState<PriceInput>(() => emptyForm(material));

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setRows(await api.priceHistory(token, material.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal memuat riwayat harga");
    } finally {
      setLoading(false);
    }
  }, [token, material.id]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const onEsc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onEsc);
    return () => window.removeEventListener("keydown", onEsc);
  }, [onClose]);

  // Mata uang berbeda TIDAK boleh masuk satu garis -- 456 EUR dan 48.000 IDR di satu
  // sumbu-Y bikin grafik yang terlihat masuk akal padahal tak berarti apa-apa. Jadi
  // yang digambar cuma mata uang yang paling banyak dipakai, sisanya diberi peringatan.
  const { chartData, mataUangUtama, mataUangLain } = useMemo(() => {
    const hitung = new Map<string, number>();
    rows.forEach((r) => hitung.set(r.mata_uang, (hitung.get(r.mata_uang) ?? 0) + 1));
    const urut = [...hitung.entries()].sort((a, b) => b[1] - a[1]);
    const utama = urut[0]?.[0] ?? "IDR";
    return {
      mataUangUtama: utama,
      mataUangLain: urut.slice(1).map(([c]) => c),
      chartData: rows
        .filter((r) => r.mata_uang === utama)
        .map((r) => ({
          // Sumbu-X numerik (epoch ms), bukan teks tanggal. Sebagai kategori, recharts
          // menjarakkan tiap titik sama rata -- pembelian Januari dan Februari 2025
          // terlihat sejauh pembelian 2025 dan 2026. Garis yang menanjak landai lalu
          // curam jadi tak terbaca bedanya, padahal itu justru yang dicari.
          waktu: new Date(r.berlaku_dari).getTime(),
          tanggal: r.berlaku_dari,
          tahun_pembelian: r.tahun_pembelian,
          // Titik ini diplot di posisi `berlaku_dari`, padahal yang berwenang soal "kapan"
          // adalah `tahun_pembelian`. Tanggalnya TIDAK dikarang ulang ke tahun pembelian --
          // bulan sebenarnya tidak diketahui, dan menebaknya akan menampilkan angka yang
          // tidak pernah ada di dokumen mana pun. Yang dilakukan: titiknya ditandai, supaya
          // belokan tajam di grafik punya penjelasan alih-alih jadi misteri.
          cocok: tahunDari(r.berlaku_dari) === r.tahun_pembelian,
          harga: r.harga_satuan,
          supplier: r.supplier_nama ?? "-",
        }))
        .filter((d) => Number.isFinite(d.waktu)),
    };
  }, [rows]);

  /** Dikelompokkan per tahun pembelian, terbaru di atas.
   *
   * `tahun_pembelian` yang berwenang, bukan `berlaku_dari` -- `berlaku_dari` boleh
   * dikosongkan waktu menempel dan kalau kosong jatuh ke hari ini, jadi sering dia fakta
   * soal kapan orang sempat menginput. Backend juga MENGURUTKAN dengan itu
   * (`urutan_harga_sql`), jadi sebelum ini tabelnya diurutkan oleh kolom yang tidak
   * ditampilkan sama sekali -- baris tampak melompat tanpa sebab yang kelihatan. */
  const perTahun = useMemo(() => {
    const peta = new Map<number, PriceHistoryRow[]>();
    rows.forEach((r) => {
      const t = r.tahun_pembelian;
      if (!peta.has(t)) peta.set(t, []);
      peta.get(t)!.push(r);
    });
    return [...peta.entries()]
      .sort((a, b) => b[0] - a[0])
      .map(([tahun, isi]) => ({ tahun, isi: [...isi].reverse() }));
  }, [rows]);

  const rentangTahun = useMemo(() => {
    if (rows.length === 0) return "-";
    const t = rows.map((r) => r.tahun_pembelian);
    const min = Math.min(...t);
    const max = Math.max(...t);
    return min === max ? String(min) : `${min} → ${max}`;
  }, [rows]);

  const nBedaTahun = useMemo(
    () => chartData.filter((d) => !d.cocok).length,
    [chartData],
  );

  const perubahan = useMemo(() => {
    if (chartData.length < 2) return null;
    const awal = chartData[0].harga;
    const akhir = chartData[chartData.length - 1].harga;
    if (!awal) return null;
    return { persen: ((akhir - awal) / awal) * 100, awal, akhir };
  }, [chartData]);

  async function submit() {
    setBusy(true);
    setError("");
    try {
      if (!form.harga_satuan || form.harga_satuan <= 0) throw new Error("Harga harus lebih dari 0");
      if (!form.berlaku_dari) throw new Error("Tanggal 'Berlaku Dari' wajib diisi");
      await api.addPrice(token, material.id, form);
      setForm(emptyForm(material));
      setFormOpen(false);
      await load();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal menyimpan harga");
    } finally {
      setBusy(false);
    }
  }

  async function hapus(id: number) {
    if (!window.confirm("Hapus titik harga ini dari riwayat?")) return;
    setBusy(true);
    setError("");
    try {
      await api.deletePrice(token, id);
      await load();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal menghapus");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-slate-900/40" onClick={onClose} aria-hidden />
      <aside className="relative flex h-full w-full max-w-2xl flex-col overflow-y-auto bg-white shadow-2xl">
        <header className="sticky top-0 z-10 border-b border-slate-200 bg-white px-6 py-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Riwayat Harga</p>
              <h3 className="font-display text-xl font-bold text-slate-900">{material.nama}</h3>
              <p className="mt-0.5 text-sm text-slate-500">
                {material.spesifikasi || "tanpa spesifikasi"} &middot; satuan {material.satuan}
              </p>
            </div>
            <button type="button" onClick={onClose} className="btn btn-secondary btn-sm">
              <X size={13} />
              Tutup
            </button>
          </div>
        </header>

        <div className="space-y-6 px-6 py-5">
          {error && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
          )}

          {loading ? (
            <p className="py-8 text-center text-sm text-slate-500">Memuat riwayat...</p>
          ) : (
            <>
              <div className="grid grid-cols-3 gap-3">
                <Stat label="Titik Harga" value={String(rows.length)} />
                {/* Tahun pembelian, bukan `berlaku_dari` -- supaya angka di sini sama
                    dengan sumbu-X grafik tren di tab Analitik. Sebelumnya dua layar bisa
                    menyebut rentang yang berbeda untuk material yang sama. */}
                <Stat label="Rentang Beli" value={rentangTahun} />
                <Stat
                  label="Perubahan"
                  value={perubahan ? `${perubahan.persen >= 0 ? "+" : ""}${perubahan.persen.toFixed(1)}%` : "-"}
                  tone={perubahan ? (perubahan.persen > 0 ? "naik" : perubahan.persen < 0 ? "turun" : undefined) : undefined}
                />
              </div>

              {mataUangLain.length > 0 && (
                <Peringatan>
                  Material ini punya harga dalam {[mataUangUtama, ...mataUangLain].join(", ")}. Grafik
                  hanya menampilkan <strong>{mataUangUtama}</strong> &mdash; nilai antar mata uang tidak
                  dikonversi karena belum ada tabel kurs, jadi menggabungkannya akan menyesatkan.
                </Peringatan>
              )}

              {chartData.length < 2 ? (
                <div className="rounded-xl border border-dashed border-slate-300 px-5 py-8 text-center">
                  <p className="text-sm font-medium text-slate-700">
                    Belum bisa digambar sebagai tren.
                  </p>
                  <p className="mt-1 text-sm text-slate-500">
                    Baru ada {chartData.length} titik harga {mataUangUtama}. Grafik butuh minimal 2 titik
                    di tanggal berbeda &mdash; tambahkan harga baru setiap kali dapat quotation/invoice.
                  </p>
                </div>
              ) : (
                <div className="rounded-xl border border-slate-200 p-4">
                  <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Tren harga ({mataUangUtama})
                  </p>
                  <ResponsiveContainer width="100%" height={230}>
                    <LineChart data={chartData} margin={{ top: 5, right: 12, bottom: 5, left: 4 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                      <XAxis
                        dataKey="waktu"
                        type="number"
                        scale="time"
                        domain={["dataMin", "dataMax"]}
                        tick={{ fontSize: 11, fill: "#64748b" }}
                        tickMargin={8}
                        tickFormatter={formatBulanTahun}
                      />
                      <YAxis
                        tick={{ fontSize: 11, fill: "#64748b" }}
                        width={80}
                        tickFormatter={(v: number) =>
                          new Intl.NumberFormat("id-ID", { notation: "compact" }).format(v)
                        }
                      />
                      <Tooltip
                        formatter={(v) => formatMoney(Number(v), mataUangUtama)}
                        labelFormatter={(l) => formatTanggalDariEpoch(Number(l))}
                        contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }}
                      />
                      <Line
                        type="monotone"
                        dataKey="harga"
                        stroke="var(--marine)"
                        strokeWidth={2}
                        dot={<TitikHarga />}
                        activeDot={{ r: 5 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                  {nBedaTahun > 0 && (
                    <p className="mt-2 flex items-start gap-1.5 text-xs text-amber-800">
                      <AlertTriangle size={13} className="mt-0.5 shrink-0" />
                      <span>
                        {nBedaTahun} titik (bulat kuning) tanggal berlakunya jatuh di tahun yang
                        berbeda dari tahun pembeliannya, jadi posisinya di sumbu waktu tidak
                        mewakili kapan barangnya dibeli. Daftar di bawah mengelompokkannya
                        menurut <strong>tahun beli</strong> &mdash; itu yang berwenang.
                      </span>
                    </p>
                  )}
                </div>
              )}

              <div>
                <div className="mb-2 flex items-center justify-between">
                  <h4 className="text-sm font-semibold text-slate-800">Daftar titik harga</h4>
                  <button
                    type="button"
                    onClick={() => setFormOpen((v) => !v)}
                    className="btn btn-primary btn-sm"
                  >
                    <Plus size={13} />
                    Tambah Harga
                  </button>
                </div>

                {formOpen && (
                  <div className="mb-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
                    <div className="grid grid-cols-2 gap-3">
                      <Field label="Harga Satuan *">
                        <input
                          type="number"
                          className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
                          value={form.harga_satuan || ""}
                          onChange={(e) => setForm((f) => ({ ...f, harga_satuan: Number(e.target.value) || 0 }))}
                        />
                      </Field>
                      <Field label="Mata Uang">
                        <select
                          className="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm"
                          value={form.mata_uang}
                          onChange={(e) => setForm((f) => ({ ...f, mata_uang: e.target.value as Currency }))}
                        >
                          {CURRENCIES.map((c) => (
                            <option key={c} value={c}>
                              {c}
                            </option>
                          ))}
                        </select>
                      </Field>
                      <Field label="Berlaku Dari *">
                        <input
                          type="date"
                          className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
                          value={form.berlaku_dari ?? ""}
                          onChange={(e) => setForm((f) => ({ ...f, berlaku_dari: e.target.value || null }))}
                        />
                      </Field>
                      <Field label="Tahun Pembelian">
                        <input
                          type="number"
                          className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
                          value={form.tahun_pembelian}
                          onChange={(e) => setForm((f) => ({ ...f, tahun_pembelian: Number(e.target.value) || 0 }))}
                        />
                      </Field>
                      <Field label="Supplier">
                        <input
                          className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
                          value={form.supplier_nama}
                          onChange={(e) => setForm((f) => ({ ...f, supplier_nama: e.target.value }))}
                        />
                      </Field>
                      <Field label="Kapal">
                        <input
                          className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
                          value={form.nama_kapal}
                          onChange={(e) => setForm((f) => ({ ...f, nama_kapal: e.target.value }))}
                        />
                      </Field>
                      <Field label="Sumber">
                        <input
                          placeholder="Quotation / PO / Invoice"
                          className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
                          value={form.sumber}
                          onChange={(e) => setForm((f) => ({ ...f, sumber: e.target.value }))}
                        />
                      </Field>
                      <Field label="No. Dokumen">
                        <input
                          className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
                          value={form.no_dokumen}
                          onChange={(e) => setForm((f) => ({ ...f, no_dokumen: e.target.value }))}
                        />
                      </Field>
                    </div>
                    <div className="mt-3 flex gap-2">
                      <button type="button" disabled={busy} onClick={submit} className="btn btn-primary btn-md">
                        {busy ? "Menyimpan..." : "Simpan Harga"}
                      </button>
                      <button
                        type="button"
                        onClick={() => setFormOpen(false)}
                        className="btn btn-secondary btn-md"
                      >
                        Batal
                      </button>
                    </div>
                  </div>
                )}

                <div className="overflow-hidden rounded-xl border border-slate-200">
                  <table className="min-w-full text-left text-sm">
                    <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                      <tr>
                        <th className="px-3 py-2.5">Berlaku Dari</th>
                        <th className="px-3 py-2.5 text-right">Harga</th>
                        <th className="px-3 py-2.5">Supplier</th>
                        <th className="px-3 py-2.5">Dokumen</th>
                        <th className="px-3 py-2.5"></th>
                      </tr>
                    </thead>
                    {/* Satu tbody per tahun pembelian, terbaru di atas. Tahunnya jadi
                        judul yang menempel waktu digulir, jadi "titik harga 2025 yang mana
                        saja" bisa dijawab dengan melihat, bukan membaca satu per satu. */}
                    {perTahun.map(({ tahun, isi }) => (
                      <tbody key={tahun}>
                        <tr>
                          <th
                            colSpan={5}
                            className="sticky top-0 border-t border-slate-200 bg-slate-100 px-3 py-1.5 text-left text-xs font-bold text-slate-700"
                          >
                            Tahun beli {tahun}
                            <span className="ml-2 font-medium text-slate-500">{isi.length} titik</span>
                          </th>
                        </tr>
                        {isi.map((r) => (
                          <tr key={r.id} className="border-t border-slate-100">
                            <td className="whitespace-nowrap px-3 py-2">
                              {formatTanggal(r.berlaku_dari)}
                              {/* Tahun `berlaku_dari` yang berbeda dari tahun pembelian
                                  bukan kesalahan, tapi harus kelihatan: itu satu-satunya
                                  penjelasan kenapa baris ini duduk di kelompok tahun yang
                                  terlihat "salah". Di cadangan 9 Agustus, 9 dari 68 baris
                                  harga seperti ini. */}
                              {tahunDari(r.berlaku_dari) !== r.tahun_pembelian && (
                                <span
                                  className="ml-1.5 rounded bg-amber-100 px-1.5 py-0.5 text-[11px] font-medium text-amber-800"
                                  title={JUDUL_BEDA_TAHUN(r.berlaku_dari, r.tahun_pembelian)}
                                >
                                  beda tahun
                                </span>
                              )}
                            </td>
                            <td className="px-3 py-2 text-right font-medium tabular-nums">
                              {formatMoney(r.harga_satuan, r.mata_uang)}
                            </td>
                            <td className="px-3 py-2">{r.supplier_nama ?? "-"}</td>
                            <td className="px-3 py-2 text-xs text-slate-500">
                              {[r.sumber, r.no_dokumen].filter(Boolean).join(" · ") || "-"}
                            </td>
                            <td className="px-3 py-2 text-right">
                              <button
                                type="button"
                                disabled={busy}
                                onClick={() => hapus(r.id)}
                                className="btn btn-danger btn-sm"
                                title="Hapus titik harga ini"
                              >
                                <Trash2 size={12} />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    ))}
                  </table>
                </div>
              </div>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}

/** Titik yang tahun `berlaku_dari`-nya tidak sama dengan tahun pembelian digambar kuning
 * dan berongga. Tanpa penanda ini, baris seperti itu bikin garis membelok tajam di ujung
 * dan terbaca sebagai "harga turun", padahal yang terjadi cuma titiknya duduk di posisi
 * waktu yang salah. */
function TitikHarga(props: {
  cx?: number;
  cy?: number;
  payload?: { cocok?: boolean };
}) {
  const { cx, cy, payload } = props;
  if (cx == null || cy == null) return null;
  const cocok = payload?.cocok !== false;
  return (
    <circle
      cx={cx}
      cy={cy}
      r={cocok ? 3 : 4.5}
      fill={cocok ? "var(--marine)" : "#fff"}
      stroke={cocok ? "var(--marine)" : "#d97706"}
      strokeWidth={cocok ? 0 : 2}
    />
  );
}

function JUDUL_BEDA_TAHUN(iso: string | null, tahunBeli: number): string {
  return (
    `Tanggal berlakunya ${tahunDari(iso)}, tapi pembeliannya dicatat tahun ${tahunBeli}. ` +
    "Yang dipakai mengurutkan dan menggambar grafik adalah tahun pembelian."
  );
}

function Stat({
  label,
  value,
  small,
  tone,
}: {
  label: string;
  value: string;
  small?: boolean;
  tone?: "naik" | "turun";
}) {
  const color = tone === "naik" ? "text-red-600" : tone === "turun" ? "text-emerald-600" : "text-slate-900";
  return (
    <div className="rounded-xl border border-slate-200 p-3">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 font-display font-bold ${small ? "text-xs" : "text-lg"} ${color}`}>{value}</p>
    </div>
  );
}

function Peringatan({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-2.5 rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-2.5 text-sm text-amber-900">
      <AlertTriangle size={16} className="mt-0.5 shrink-0" />
      <p>{children}</p>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-xs font-medium text-slate-600">
      {label}
      <div className="mt-1">{children}</div>
    </label>
  );
}
