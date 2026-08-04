import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Plus, Save, Search, Trash2, X } from "lucide-react";
import {
  api,
  formatRp,
  type AhspHitung,
  type AhspKomponenInput,
  type AhspKomponenRow,
  type AhspRingkas,
  type AhspRow,
  type AuthUser,
  type JenisSumberDaya,
  type MaterialRow,
} from "../lib/api";

/** Lembar AHSP: satu item yang dijual, rinciannya, dan biaya modalnya.
 *
 * Frontend TIDAK PERNAH menghitung angka final. Perkalian qty x shift x jml_hari x harga
 * di sini cuma pratinjau hidup saat mengetik; angka yang dipakai selalu datang dari
 * GET /ahsp/{id}/hitung. Kalau rumusnya ada di dua tempat, suatu saat keduanya beda dan
 * tidak ada yang tahu mana yang benar.
 */

const KELOMPOK_LABEL: Record<JenisSumberDaya, string> = {
  BAHAN: "Bahan",
  UPAH: "Upah",
  ALAT: "Alat",
  KONSUMABEL: "Konsumabel",
};

const KELOMPOK_CATATAN: Record<JenisSumberDaya, string> = {
  BAHAN: "diambil dari Katalog Material",
  UPAH: "tenaga kerja sendiri, 8 jam kerja per hari",
  ALAT: "milik sendiri, tarif internal",
  KONSUMABEL: "milik sendiri, tarif internal",
};

const SEMUA_KELOMPOK: JenisSumberDaya[] = ["BAHAN", "UPAH", "ALAT", "KONSUMABEL"];
const TAHUN_INI = new Date().getFullYear();

/** String Decimal dari backend -> number, hanya untuk ditampilkan atau dipratinjau. */
function n(v: string | null | undefined): number {
  return v == null ? 0 : Number(v);
}

/** Tenaga kerja dan alat DISEWA per waktu: biayanya tarif x lama x banyaknya.
 * Bahan dan konsumabel HABIS DIPAKAI: biayanya harga x jumlah, tanpa dimensi waktu.
 *
 * Dua-duanya dulu dipaksa masuk satu bentuk tabel, sehingga baris pasir harus diisi
 * "Jml Hari = 1" -- angka yang tidak berarti apa-apa, dipasang cuma supaya perkaliannya
 * tidak berubah. Excel aslinya sendiri sudah menunjukkan gejalanya: 18 dari 298 baris
 * memang cuma memakai Qty x Harga. */
function pakaiDimensiWaktu(kel: JenisSumberDaya): boolean {
  return kel === "UPAH" || kel === "ALAT";
}

/** Koefisien AHSP: berapa banyak sumber daya ini untuk SATU satuan yang dijual.
 *
 * Inilah angka yang sebenarnya bermakna; qty/shift/jml_hari cuma cara menurunkannya
 * ("3 orang x 1 shift x 0,02 hari = 0,06 OH"). Satuannya milik sumber dayanya sendiri,
 * bukan milik barang yang dijual -- karena harga_satuan juga per satuan itu. Menamainya
 * terhadap satuan jual menghasilkan omong kosong seperti "hari per pcs". */
function koefisien(d: { qty: string; shift: string; jml_hari: string }): number {
  return Number((n(d.qty) * n(d.shift) * n(d.jml_hari)).toFixed(6));
}

function angka(x: number): string {
  return new Intl.NumberFormat("id-ID", { maximumFractionDigits: 6 }).format(x);
}

/** Cari pakai dua kata pertama saja.
 *
 * Mengetik "Cat Epoxy" memang menemukan "Cat Epoxy 5kg" karena pencariannya substring,
 * tapi arah sebaliknya tidak: mengetik "Cat Epoxy 5kg" tidak akan menemukan "Cat Epoxy"
 * yang sudah ada, lalu orang membuat barang kembar tanpa sadar. Memotong ke dua kata
 * pertama menutup arah kedua itu. */
function kunciCari(teks: string): string {
  return teks.trim().split(/\s+/).slice(0, 2).join(" ");
}

type Props = { auth: AuthUser };

export default function AhspPanel({ auth }: Props) {
  const [items, setItems] = useState<AhspRow[]>([]);
  const [ringkas, setRingkas] = useState<AhspRingkas | null>(null);
  const [loading, setLoading] = useState(true);
  const [terpilih, setTerpilih] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");

  const muat = useCallback(async () => {
    setLoading(true);
    try {
      const [daftar, r] = await Promise.all([api.ahspList(auth.token), api.ahspRingkas(auth.token)]);
      setItems(daftar);
      setRingkas(r);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal memuat daftar AHSP");
    } finally {
      setLoading(false);
    }
  }, [auth.token]);

  useEffect(() => {
    void muat();
  }, [muat]);

  const dipilih = items.find((i) => i.id === terpilih) ?? null;

  async function hapus(item: AhspRow) {
    if (!confirm(`Hapus analisa "${item.uraian}" beserta seluruh rinciannya?`)) return;
    try {
      await api.ahspDelete(auth.token, item.id);
      if (terpilih === item.id) setTerpilih(null);
      await muat();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal menghapus");
    }
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-lg font-bold text-slate-900">Struktur Biaya</h2>
          <p className="text-xs text-slate-500">
            Rincian biaya modal per item yang dijual — dasar justifikasi harga ke pelanggan.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowForm((s) => !s)}
          className={`btn btn-md ${showForm ? "btn-secondary" : "btn-primary"}`}
        >
          {showForm ? <X size={14} /> : <Plus size={14} />}
          {showForm ? "Batal" : "Analisa Baru"}
        </button>
      </div>

      {error && <p className="mb-3 text-sm text-red-600">{error}</p>}

      {ringkas && (
        <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <KpiCard
            title="Sudah punya rincian"
            value={`${ringkas.lengkap} dari ${ringkas.total}`}
            accent
          />
          <KpiCard
            title="Komponen tanpa harga"
            value={String(ringkas.komponen_tanpa_harga)}
            peringatan={ringkas.komponen_tanpa_harga > 0}
          />
        </div>
      )}

      {showForm && (
        <FormAhspBaru
          token={auth.token}
          onSelesai={async (id) => {
            setShowForm(false);
            await muat();
            setTerpilih(id);
          }}
        />
      )}

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <p className="border-b border-slate-100 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Daftar item yang dijual
        </p>
        {loading ? (
          <p className="p-8 text-center text-slate-500">Memuat...</p>
        ) : items.length === 0 ? (
          <p className="p-8 text-center text-sm text-slate-400">
            Belum ada analisa harga satuan. Klik "Analisa Baru" untuk mulai.
          </p>
        ) : (
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">Uraian</th>
                <th className="px-4 py-3">Satuan</th>
                <th className="px-4 py-3">Jenis</th>
                <th className="px-4 py-3 text-right">Subtotal biaya</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {items.map((i) => (
                <tr
                  key={i.id}
                  onClick={() => setTerpilih(terpilih === i.id ? null : i.id)}
                  className={`cursor-pointer border-t border-slate-100 hover:bg-slate-50 ${
                    terpilih === i.id ? "bg-slate-50" : ""
                  }`}
                >
                  <td className="px-4 py-2 font-medium text-slate-800">{i.uraian}</td>
                  <td className="px-4 py-2">{i.satuan}</td>
                  <td className="px-4 py-2 text-slate-500">
                    {i.jenis_jual === "JASA" ? "Jasa" : "Material"}
                  </td>
                  <td className="px-4 py-2 text-right font-medium tabular-nums">
                    {/* Angka ini subtotal dari komponen yang harganya sudah ada. Kalau masih
                        ada yang bolong, sengaja diberi tanda supaya tidak dibaca sebagai final. */}
                    {i.subtotal_total == null ? "-" : formatRp(n(i.subtotal_total))}
                    {!i.lengkap && i.subtotal_total != null && (
                      <span className="ml-1 text-amber-600">*</span>
                    )}
                  </td>
                  <td className="px-4 py-2">
                    <StatusBadge row={i} />
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button
                      type="button"
                      title="Hapus analisa ini"
                      onClick={(e) => {
                        e.stopPropagation();
                        void hapus(i);
                      }}
                      className="rounded p-1 text-slate-400 hover:text-red-700"
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {dipilih && (
        <LembarRincian
          key={dipilih.id}
          token={auth.token}
          ahsp={dipilih}
          onBerubah={muat}
        />
      )}
    </div>
  );
}

function StatusBadge({ row }: { row: AhspRow }) {
  if (row.n_komponen === 0) {
    return <Tag warna="bg-slate-100 text-slate-600">belum diisi</Tag>;
  }
  if (row.n_tanpa_harga > 0) {
    return (
      <Tag warna="bg-amber-100 text-amber-800">
        harga kurang ({row.n_tanpa_harga})
      </Tag>
    );
  }
  return <Tag warna="bg-emerald-100 text-emerald-800">{row.n_komponen} komponen</Tag>;
}

function Tag({ children, warna }: { children: React.ReactNode; warna: string }) {
  return <span className={`rounded px-2 py-0.5 text-xs font-medium ${warna}`}>{children}</span>;
}

function KpiCard({
  title,
  value,
  accent,
  peringatan,
}: {
  title: string;
  value: string;
  accent?: boolean;
  peringatan?: boolean;
}) {
  return (
    <div
      className="rounded-xl border border-slate-200 p-5 shadow-sm"
      style={accent ? { background: "var(--marine)" } : { background: "white" }}
    >
      <p
        className={`text-xs font-semibold uppercase tracking-wide ${
          accent ? "text-blue-100" : "text-slate-500"
        }`}
      >
        {title}
      </p>
      <p
        className={`mt-2 font-display text-3xl font-bold ${
          accent ? "text-white" : peringatan ? "text-amber-600" : "text-slate-900"
        }`}
      >
        {value}
      </p>
    </div>
  );
}

// ---------- form analisa baru ----------

function FormAhspBaru({
  token,
  onSelesai,
}: {
  token: string;
  onSelesai: (id: number) => void | Promise<void>;
}) {
  const [uraian, setUraian] = useState("");
  const [satuan, setSatuan] = useState("");
  const [jenisJual, setJenisJual] = useState<"JASA" | "MATERIAL">("JASA");
  const [kategori, setKategori] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function simpan() {
    if (!uraian.trim() || !satuan.trim()) {
      setError("Uraian dan satuan wajib diisi.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const res = await api.ahspCreate(token, {
        uraian: uraian.trim(),
        satuan: satuan.trim(),
        jenis_jual: jenisJual,
        kategori: kategori.trim(),
        catatan: "",
      });
      await onSelesai(res.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal menyimpan");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mb-6 rounded-xl border border-blue-200 bg-blue-50 p-4">
      <p className="mb-3 text-xs font-bold text-slate-700">Analisa Harga Satuan Baru</p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Isian label="Uraian pekerjaan *" value={uraian} onChange={setUraian} placeholder="mis. Pengecatan lambung" />
        <Isian label="Satuan *" value={satuan} onChange={setSatuan} placeholder="mis. m2, Kali, Unit" />
        <label className="block text-xs font-medium text-slate-600">
          Yang dijual
          <select
            className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm"
            value={jenisJual}
            onChange={(e) => setJenisJual(e.target.value as "JASA" | "MATERIAL")}
          >
            <option value="JASA">Jasa</option>
            <option value="MATERIAL">Material</option>
          </select>
        </label>
        <Isian label="Kategori" value={kategori} onChange={setKategori} placeholder="opsional" />
      </div>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      <div className="mt-3">
        <button type="button" disabled={busy} onClick={simpan} className="btn btn-primary btn-md">
          <Save size={13} />
          {busy ? "Menyimpan..." : "Simpan"}
        </button>
      </div>
    </div>
  );
}

// ---------- lembar rincian ----------

type Draf = {
  key: string;
  sumber_daya_id: number;
  nama: string;
  spesifikasi: string;
  satuan: string;
  kelompok: JenisSumberDaya;
  qty: string;
  shift: string;
  jml_hari: string;
  harga_satuan: string | null;
  mata_uang: string | null;
};

/** NUMERIC(18,6) kembali dari Postgres sebagai "2.000000". Dibersihkan sekali di sini,
 * waktu masuk draf -- bukan tiap ketikan. Kalau dibersihkan tiap ketikan, mengetik "0."
 * langsung jadi "0" dan angka desimal tidak bisa diketik sama sekali. */
function rapi(s: string): string {
  const x = Number(s);
  return Number.isFinite(x) ? String(x) : s;
}

function keDraf(k: AhspKomponenRow): Draf {
  return {
    key: `k${k.id}`,
    sumber_daya_id: k.sumber_daya_id,
    nama: k.nama,
    spesifikasi: k.spesifikasi,
    satuan: k.satuan,
    kelompok: k.kelompok,
    qty: rapi(k.qty),
    shift: rapi(k.shift),
    jml_hari: rapi(k.jml_hari),
    harga_satuan: k.harga_satuan,
    mata_uang: k.mata_uang,
  };
}

function LembarRincian({
  token,
  ahsp,
  onBerubah,
}: {
  token: string;
  ahsp: AhspRow;
  onBerubah: () => void | Promise<void>;
}) {
  const [komponen, setKomponen] = useState<AhspKomponenRow[]>([]);
  const [hitung, setHitung] = useState<AhspHitung | null>(null);
  const [draf, setDraf] = useState<Draf[] | null>(null);
  const [memuat, setMemuat] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [tambahKe, setTambahKe] = useState<JenisSumberDaya | null>(null);

  const ambil = useCallback(async () => {
    setMemuat(true);
    try {
      const [k, h] = await Promise.all([
        api.ahspKomponen(token, ahsp.id),
        api.ahspHitung(token, ahsp.id),
      ]);
      setKomponen(k);
      setHitung(h);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal memuat rincian");
    } finally {
      setMemuat(false);
    }
  }, [token, ahsp.id]);

  useEffect(() => {
    void ambil();
  }, [ambil]);

  /** Urutan kelompok mengikuti kolom `urutan`, BUKAN urutan tetap Bahan-Upah-Alat.
   * Di file asli urutannya berbeda-beda per pekerjaan (29 blok Upah-Alat-Bahan, 8 blok
   * cuma Alat, dst), jadi mematoknya akan salah untuk sebagian besar pekerjaan. */
  const kelompokTampil = useMemo(() => {
    const sumber = draf ?? komponen.map(keDraf);
    const urut = new Map<JenisSumberDaya, number>();
    (draf ? draf : komponen).forEach((k, i) => {
      const kel = k.kelompok;
      const posisi = draf ? i : (k as AhspKomponenRow).urutan;
      if (!urut.has(kel) || posisi < (urut.get(kel) as number)) urut.set(kel, posisi);
    });
    return SEMUA_KELOMPOK.filter((kel) => sumber.some((s) => s.kelompok === kel)).sort(
      (a, b) => (urut.get(a) ?? 0) - (urut.get(b) ?? 0),
    );
  }, [draf, komponen]);

  const barisTampil: Draf[] = draf ?? komponen.map(keDraf);

  function ubah(key: string, patch: Partial<Draf>) {
    setDraf((prev) => (prev ?? komponen.map(keDraf)).map((d) => (d.key === key ? { ...d, ...patch } : d)));
  }

  function hapusBaris(key: string) {
    setDraf((prev) => (prev ?? komponen.map(keDraf)).filter((d) => d.key !== key));
  }

  function tambahBaris(kel: JenisSumberDaya, m: MaterialRow) {
    const sekarang = draf ?? komponen.map(keDraf);
    // Backend menolak pasangan (komponen, kelompok) yang kembar, tapi kalau baru ketahuan
    // waktu menyimpan, seluruh isian lain ikut tertahan sampai orang menemukan barisnya.
    if (sekarang.some((d) => d.sumber_daya_id === m.id && d.kelompok === kel)) {
      setError(`"${m.nama}" sudah ada di kelompok ${KELOMPOK_LABEL[kel]}. Ubah saja barisnya.`);
      setTambahKe(null);
      return;
    }
    setError("");
    setDraf((prev) => [
      ...(prev ?? komponen.map(keDraf)),
      {
        key: `b${Date.now()}-${m.id}`,
        sumber_daya_id: m.id,
        nama: m.nama,
        spesifikasi: m.spesifikasi,
        satuan: m.satuan,
        kelompok: kel,
        qty: "1",
        shift: "1",
        jml_hari: "1",
        harga_satuan: m.harga_satuan == null ? null : String(m.harga_satuan),
        mata_uang: m.mata_uang,
      },
    ]);
    setTambahKe(null);
  }

  async function simpan() {
    if (!draf) return;
    setBusy(true);
    setError("");
    try {
      const items: AhspKomponenInput[] = draf.map((d, i) => ({
        sumber_daya_id: d.sumber_daya_id,
        kelompok: d.kelompok,
        qty: d.qty || "1",
        shift: d.shift || "1",
        jml_hari: d.jml_hari || "1",
        urutan: i,
        catatan: "",
      }));
      await api.ahspSimpanKomponen(token, ahsp.id, items);
      setDraf(null);
      await ambil();
      await onBerubah();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal menyimpan rincian");
    } finally {
      setBusy(false);
    }
  }

  const sedangEdit = draf !== null;

  return (
    <div className="mt-6 rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
        <div>
          <p className="font-display text-base font-bold text-slate-900">{ahsp.uraian}</p>
          <p className="text-xs text-slate-500">per {ahsp.satuan}</p>
        </div>
        <div className="flex gap-2">
          {sedangEdit ? (
            <>
              <button type="button" disabled={busy} onClick={simpan} className="btn btn-primary btn-sm">
                <Save size={13} />
                {busy ? "Menyimpan..." : "Simpan Rincian"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setDraf(null);
                  setTambahKe(null);
                }}
                className="btn btn-secondary btn-sm"
              >
                Batal
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={() => setDraf(komponen.map(keDraf))}
              className="btn btn-secondary btn-sm"
            >
              Ubah rincian
            </button>
          )}
        </div>
      </div>

      {error && <p className="px-4 pt-3 text-sm text-red-600">{error}</p>}

      {memuat ? (
        <p className="p-8 text-center text-slate-500">Memuat rincian...</p>
      ) : (
        <div className="p-4">
          {barisTampil.length === 0 && !sedangEdit && (
            <p className="py-6 text-center text-sm text-slate-400">
              Belum ada komponen. Klik "Ubah rincian" untuk mulai mengisi.
            </p>
          )}

          {kelompokTampil.map((kel, idx) => {
            const baris = barisTampil.filter((b) => b.kelompok === kel);
            return (
              <div key={kel} className="mb-5">
                <p className="mb-2 text-sm font-semibold text-slate-800">
                  {idx + 1} · {KELOMPOK_LABEL[kel]}{" "}
                  <span className="font-normal text-xs text-slate-500">
                    — {KELOMPOK_CATATAN[kel]}
                    {pakaiDimensiWaktu(kel)
                      ? `; koefisien = banyaknya × shift × lama, dalam satuan sumber dayanya`
                      : `; koefisien = jumlah yang habis dipakai untuk satu ${ahsp.satuan}`}
                  </span>
                </p>
                <TabelKelompok
                  baris={baris}
                  kelompok={kel}
                  sedangEdit={sedangEdit}
                  onUbah={ubah}
                  onHapus={hapusBaris}
                  subtotal={hitung?.subtotal[kel] ?? null}
                  satuanJual={ahsp.satuan}
                />
              </div>
            );
          })}

          {sedangEdit && (
            <div className="mb-5">
              {tambahKe ? (
                <PilihSumberDaya
                  token={token}
                  kelompok={tambahKe}
                  onPilih={(m) => tambahBaris(tambahKe, m)}
                  onBatal={() => setTambahKe(null)}
                />
              ) : (
                <div className="flex flex-wrap gap-2">
                  {SEMUA_KELOMPOK.map((kel) => (
                    <button
                      key={kel}
                      type="button"
                      onClick={() => setTambahKe(kel)}
                      className="btn btn-secondary btn-sm"
                    >
                      <Plus size={13} />
                      Tambah {KELOMPOK_LABEL[kel]}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {hitung && <Penutup hitung={hitung} satuan={ahsp.satuan} sedangEdit={sedangEdit} />}
        </div>
      )}
    </div>
  );
}

function TabelKelompok({
  baris,
  kelompok,
  sedangEdit,
  onUbah,
  onHapus,
  subtotal,
  satuanJual,
}: {
  baris: Draf[];
  kelompok: JenisSumberDaya;
  sedangEdit: boolean;
  onUbah: (key: string, patch: Partial<Draf>) => void;
  onHapus: (key: string) => void;
  subtotal: string | null;
  satuanJual: string;
}) {
  const berwaktu = pakaiDimensiWaktu(kelompok);
  // Kolom sebelum Harga satuan: berwaktu punya penurunannya (banyaknya, shift, lama) plus
  // hasil koefisiennya; yang habis dipakai cuma punya koefisiennya.
  const kolomSebelumHarga = berwaktu ? 5 : 2;

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="min-w-full text-left text-xs">
        <thead className="bg-slate-50 uppercase text-slate-500">
          <tr>
            <th className="px-3 py-2">Uraian</th>
            {berwaktu && <th className="px-2 py-2 w-20">Banyaknya</th>}
            {berwaktu && <th className="px-2 py-2 w-16">Shift</th>}
            {berwaktu && <th className="px-2 py-2 w-28">Lama (hari)</th>}
            <th className="px-3 py-2 w-32">Koefisien per {satuanJual}</th>
            <th className="px-3 py-2 text-right">Harga satuan</th>
            <th className="px-3 py-2 text-right">Jumlah</th>
            {sedangEdit && <th className="w-8"></th>}
          </tr>
        </thead>
        <tbody>
          {baris.map((b) => {
            const belumBerharga = b.harga_satuan == null;
            const bukanRupiah = b.mata_uang != null && b.mata_uang !== "IDR";
            const bermasalah = belumBerharga || bukanRupiah;
            const koef = koefisien(b);
            // Pratinjau saja -- angka final datang dari /ahsp/{id}/hitung.
            const jumlah = bermasalah ? null : koef * n(b.harga_satuan);
            return (
              <tr
                key={b.key}
                className={`border-t border-slate-100 ${bermasalah ? "bg-amber-50" : ""}`}
              >
                <td className="px-3 py-1.5">
                  {b.nama}
                  {b.spesifikasi && <span className="text-slate-400"> · {b.spesifikasi}</span>}
                </td>

                {berwaktu && (
                  <>
                    <SelAngka
                      nilai={b.qty}
                      edit={sedangEdit}
                      onUbah={(v) => onUbah(b.key, { qty: v })}
                    />
                    <SelAngka
                      nilai={b.shift}
                      edit={sedangEdit}
                      onUbah={(v) => onUbah(b.key, { shift: v })}
                    />
                    <SelAngka
                      nilai={b.jml_hari}
                      edit={sedangEdit}
                      onUbah={(v) => onUbah(b.key, { jml_hari: v })}
                      petunjuk={petunjukLama(b.jml_hari, satuanJual)}
                    />
                  </>
                )}

                {/* Untuk bahan dan konsumabel, koefisiennya ADALAH jumlahnya -- tidak ada
                    lama atau shift yang perlu ditanyakan, jadi kotaknya menulis langsung
                    ke qty dan dua kolom lain tidak pernah muncul. */}
                {berwaktu ? (
                  <td className="px-3 py-1.5 tabular-nums font-medium text-slate-700">
                    {angka(koef)} <span className="font-normal text-slate-400">{b.satuan}</span>
                  </td>
                ) : (
                  <SelAngka
                    // Membaca: tampilkan koefisien sebenarnya, supaya baris warisan yang
                    // shift/jml_hari-nya bukan 1 tidak berbohong soal angkanya.
                    // Menyunting: kotaknya menulis ke qty dan sekalian mengembalikan dua
                    // pengali lain ke 1 -- itu yang membuat janji kolom ini benar.
                    nilai={sedangEdit ? b.qty : String(koef)}
                    edit={sedangEdit}
                    onUbah={(v) => onUbah(b.key, { qty: v, shift: "1", jml_hari: "1" })}
                    suffix={b.satuan}
                  />
                )}

                <td className="px-3 py-1.5 text-right tabular-nums">
                  {belumBerharga ? (
                    <span className="font-medium text-amber-700">belum ada harga</span>
                  ) : bukanRupiah ? (
                    <span className="font-medium text-amber-700">
                      {b.mata_uang} {b.harga_satuan}
                    </span>
                  ) : (
                    <>
                      {formatRp(n(b.harga_satuan))}
                      <span className="text-slate-400"> /{b.satuan}</span>
                    </>
                  )}
                </td>
                <td className="px-3 py-1.5 text-right tabular-nums">
                  {jumlah == null ? <span className="text-amber-700">—</span> : formatRp(jumlah)}
                </td>
                {sedangEdit && (
                  <td className="px-1 py-1.5">
                    <button
                      type="button"
                      title="Hapus komponen ini"
                      onClick={() => onHapus(b.key)}
                      className="rounded p-1 text-slate-400 hover:text-red-700"
                    >
                      <Trash2 size={13} />
                    </button>
                  </td>
                )}
              </tr>
            );
          })}
          <tr className="border-t border-slate-200 bg-slate-50 font-semibold">
            <td className="px-3 py-2" colSpan={kolomSebelumHarga + 1}>
              Sub Total
            </td>
            <td className="px-3 py-2 text-right tabular-nums">
              {subtotal == null ? "-" : formatRp(n(subtotal))}
            </td>
            {sedangEdit && <td></td>}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

/** Kalimat pembanding di bawah kotak "Lama".
 *
 * Kolom ini punya satu mode gagal yang berbahaya: salah ketik 0,2 alih-alih 0,02 membuat
 * harganya 10x lipat dan tidak ada apa pun di layar yang terlihat aneh. Angka pembaliknya
 * jauh lebih mudah dibantah orang lapangan -- "5 m2 per hari" langsung ketahuan salah.
 *
 * Di atas 1 hari pembaliknya justru membingungkan ("0,33 Unit per hari"), jadi di sana
 * kalimatnya dibalik jadi durasi.
 */
function petunjukLama(jmlHari: string, satuanJual: string): string {
  const h = Number(jmlHari);
  if (!Number.isFinite(h) || h <= 0) return "";
  if (h >= 1) return `${angka(h)} hari untuk 1 ${satuanJual}`;
  return `≈ ${angka(Number((1 / h).toFixed(2)))} ${satuanJual} per hari`;
}

function SelAngka({
  nilai,
  edit,
  onUbah,
  petunjuk,
  suffix,
}: {
  nilai: string;
  edit: boolean;
  onUbah: (v: string) => void;
  petunjuk?: string;
  suffix?: string;
}) {
  // Sengaja input teks, bukan number: koefisien seperti 0,07 dikirim apa adanya sebagai
  // string ke Decimal di backend, tidak lewat float sama sekali.
  return (
    <td className="px-2 py-1.5 tabular-nums">
      {edit ? (
        <input
          inputMode="decimal"
          className="w-full rounded border border-slate-200 px-1 py-0.5 text-right"
          value={nilai}
          onChange={(e) => onUbah(e.target.value.replace(",", "."))}
        />
      ) : (
        <span>{angka(Number(nilai))}</span>
      )}
      {suffix && <span className="ml-1 text-slate-400">{suffix}</span>}
      {petunjuk && <p className="mt-0.5 text-[10px] font-normal text-slate-400">{petunjuk}</p>}
    </td>
  );
}

function Penutup({
  hitung,
  satuan,
  sedangEdit,
}: {
  hitung: AhspHitung;
  satuan: string;
  sedangEdit: boolean;
}) {
  return (
    <div className="mt-2 rounded-lg border border-slate-200 bg-slate-50 p-4">
      {hitung.lengkap ? (
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="font-display text-sm font-bold text-slate-800">
            Jumlah harga satuan per {satuan}
          </p>
          <p className="font-display text-2xl font-bold tabular-nums" style={{ color: "var(--ink)" }}>
            {formatRp(n(hitung.harga_jual))}
          </p>
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="font-display text-sm font-bold text-slate-700">
              Subtotal sementara per {satuan}
            </p>
            <p className="font-display text-2xl font-bold tabular-nums text-slate-400">
              {formatRp(n(hitung.subtotal_total))}
            </p>
          </div>
          <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3">
            <p className="flex items-center gap-1.5 text-xs font-semibold text-amber-900">
              <AlertTriangle size={13} />
              Belum bisa dipakai sebagai harga
            </p>
            <ul className="mt-1.5 list-disc space-y-0.5 pl-5 text-xs text-amber-800">
              {hitung.alasan.map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
            <p className="mt-1.5 text-xs text-amber-800">
              Angka di atas cuma menjumlahkan komponen yang harganya sudah ada, jadi lebih
              rendah dari biaya sebenarnya.
            </p>
          </div>
        </>
      )}

      <p className="mt-3 text-xs font-medium text-slate-600">
        Belum termasuk PPN. PPN ditambahkan sekali di tingkat dokumen penawaran, bukan per item.
      </p>
      {sedangEdit && (
        <p className="mt-1 text-xs text-slate-500">
          Angka di kotak ini masih dari rincian yang tersimpan — baru ikut berubah setelah
          "Simpan Rincian" ditekan.
        </p>
      )}
    </div>
  );
}

// ---------- pemilih sumber daya + tambah cepat ----------

function PilihSumberDaya({
  token,
  kelompok,
  onPilih,
  onBatal,
}: {
  token: string;
  kelompok: JenisSumberDaya;
  onPilih: (m: MaterialRow) => void;
  onBatal: () => void;
}) {
  const [teks, setTeks] = useState("");
  const [hasil, setHasil] = useState<MaterialRow[]>([]);
  const [mencari, setMencari] = useState(false);
  const [buatBaru, setBuatBaru] = useState(false);
  const [satuan, setSatuan] = useState("");
  const [harga, setHarga] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const kunci = kunciCari(teks);
    if (kunci.length < 2) {
      setHasil([]);
      return;
    }
    let batal = false;
    setMencari(true);
    const t = setTimeout(async () => {
      try {
        const r = await api.material(token, { jenis: kelompok, search: kunci });
        if (!batal) setHasil(r.slice(0, 8));
      } catch {
        if (!batal) setHasil([]);
      } finally {
        if (!batal) setMencari(false);
      }
    }, 250);
    return () => {
      batal = true;
      clearTimeout(t);
    };
  }, [teks, token, kelompok]);

  async function simpanBaru() {
    if (!teks.trim() || !satuan.trim() || !(Number(harga) > 0)) {
      setError("Nama, satuan, dan harga awal (di atas 0) wajib diisi.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api.materialBulkCreate(
        token,
        [
          {
            nama: teks.trim(),
            spesifikasi: "",
            satuan: satuan.trim(),
            harga_satuan: Number(harga),
            mata_uang: "IDR",
            tahun_pembelian: TAHUN_INI,
            supplier_nama: "",
            nama_kapal: "",
            berlaku_dari: null,
            sumber: kelompok === "BAHAN" || kelompok === "KONSUMABEL" ? "Manual" : "Tarif internal",
            no_dokumen: "",
            catatan: "",
          },
        ],
        kelompok,
      );
      // Endpoint bulk tidak mengembalikan id, jadi barangnya dicari lagi lewat jalur yang
      // sama dengan pencarian biasa -- sekaligus memastikan dia memang sudah tersimpan.
      const r = await api.material(token, { jenis: kelompok, search: kunciCari(teks) });
      const ketemu = r.find((m) => m.nama.trim().toLowerCase() === teks.trim().toLowerCase());
      if (!ketemu) {
        setError("Tersimpan, tapi belum ketemu waktu dicari ulang. Coba cari manual.");
        return;
      }
      onPilih(ketemu);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal menyimpan barang baru");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-blue-200 bg-blue-50 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-xs font-bold text-slate-700">
          Tambah komponen ke kelompok {KELOMPOK_LABEL[kelompok]}
        </p>
        <button type="button" onClick={onBatal} className="btn btn-secondary btn-sm">
          <X size={12} />
          Tutup
        </button>
      </div>

      <div className="relative">
        <Search
          size={14}
          className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400"
        />
        <input
          autoFocus
          placeholder={`Ketik nama ${KELOMPOK_LABEL[kelompok].toLowerCase()}...`}
          className="w-full rounded-lg border border-slate-300 py-2 pl-8 pr-3 text-sm"
          value={teks}
          onChange={(e) => {
            setTeks(e.target.value);
            setBuatBaru(false);
            setError("");
          }}
        />
      </div>

      {/* Saran ditampilkan LEBIH DULU, "buat baru" di bawahnya. uq_sd_identitas cuma menolak
          yang persis sama, jadi "Cat Epoxy" vs "Cat Epoxy 5kg" tetap lolos sebagai dua barang
          -- penjaganya harus di sini, bukan di index. */}
      {teks.trim().length >= 2 && (
        <div className="mt-2">
          {mencari ? (
            <p className="text-xs text-slate-500">Mencari yang sudah ada...</p>
          ) : hasil.length > 0 ? (
            <>
              <p className="mb-1 text-xs text-slate-500">
                Sudah ada di katalog — pakai yang ini kalau memang barang yang sama:
              </p>
              <div className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
                {hasil.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => onPilih(m)}
                    className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-slate-50"
                  >
                    <span>
                      {m.nama}
                      {m.spesifikasi && <span className="text-slate-400"> · {m.spesifikasi}</span>}
                      <span className="text-slate-400"> / {m.satuan}</span>
                    </span>
                    <span className="shrink-0 tabular-nums text-slate-600">
                      {m.harga_satuan == null ? "belum ada harga" : formatRp(m.harga_satuan)}
                    </span>
                  </button>
                ))}
              </div>
            </>
          ) : (
            <p className="text-xs text-slate-500">Tidak ada yang mirip di katalog.</p>
          )}

          {!buatBaru ? (
            <button
              type="button"
              onClick={() => setBuatBaru(true)}
              className="btn btn-secondary btn-sm mt-2"
            >
              <Plus size={12} />
              Buat baru: "{teks.trim()}"
            </button>
          ) : (
            <div className="mt-2 rounded-lg border border-slate-200 bg-white p-3">
              <p className="mb-2 text-xs text-slate-600">
                Barang ini akan tersimpan di Katalog Material juga — memang satu tabel yang
                sama, dilihat dari dua layar.
              </p>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                <Isian label="Nama" value={teks} onChange={setTeks} />
                <Isian label="Satuan *" value={satuan} onChange={setSatuan} placeholder="mis. Kg, OH, Unit" />
                <label className="block text-xs font-medium text-slate-600">
                  Harga awal (Rp) *
                  <input
                    inputMode="decimal"
                    className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm text-right"
                    value={harga}
                    onChange={(e) => setHarga(e.target.value.replace(",", "."))}
                  />
                </label>
              </div>
              <button
                type="button"
                disabled={busy}
                onClick={simpanBaru}
                className="btn btn-primary btn-sm mt-2"
              >
                <Save size={12} />
                {busy ? "Menyimpan..." : "Simpan & pakai"}
              </button>
            </div>
          )}
        </div>
      )}

      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </div>
  );
}

function Isian({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="block text-xs font-medium text-slate-600">
      {label}
      <input
        className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}
