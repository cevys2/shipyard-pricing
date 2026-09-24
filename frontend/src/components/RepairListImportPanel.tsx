import { useMemo, useState } from "react";
import { CheckCircle2, Plus, Trash2, TriangleAlert } from "lucide-react";
import { api, formatRp, type RepairListPreview } from "../lib/api";
import PilihBerkas from "./PilihBerkas";

type Props = {
  token: string;
  onImported: () => void;
};

type EditRow = {
  key: string;
  kategori: string;
  induk: string;
  uraian: string;
  volume: number | null;
  satuan: string;
  harga: number;
  keterangan: string;
};

let counter = 0;
function newKey() {
  counter += 1;
  return `rl-${Date.now()}-${counter}`;
}

function fromParsed(items: RepairListPreview["items"]): EditRow[] {
  return items.map((it) => ({
    key: `p-${it.row}`,
    kategori: it.kategori || "-",
    induk: it.induk_uraian || "",
    uraian: it.uraian,
    volume: it.volume,
    satuan: it.satuan || "",
    harga: it.harga,
    keterangan: it.keterangan || "",
  }));
}

const emptyRow = (): EditRow => ({
  key: newKey(),
  kategori: "-",
  induk: "",
  uraian: "",
  volume: 1,
  satuan: "",
  harga: 0,
  keterangan: "",
});

/** Nilai satu baris. Volume kosong dihitung 1 x harga — sama persis dengan yang dipakai
 * parser di backend, supaya angka di layar ini tidak pernah beda dari angka yang jadi
 * dasar palang rekonsiliasi. */
const nilaiBaris = (r: EditRow) => (r.volume ?? 1) * (r.harga || 0);

export default function RepairListImportPanel({ token, onImported }: Props) {
  const [preview, setPreview] = useState<RepairListPreview | null>(null);
  const [rows, setRows] = useState<EditRow[] | null>(null);
  const [header, setHeader] = useState({ nama_perusahaan: "", nama_kapal: "", tahun: "" });
  const [loading, setLoading] = useState(false);
  const [menyimpan, setMenyimpan] = useState(0);
  const [error, setError] = useState("");
  const [resultMsg, setResultMsg] = useState("");

  // Dihitung ulang tiap kali tabelnya disunting, bukan cuma sekali waktu berkas dibaca.
  // Itu intinya: begitu satu baris dihapus atau harganya diubah, selisihnya langsung
  // bukan nol dan kelihatan sebelum apa pun tersimpan.
  const terbaca = useMemo(() => (rows ?? []).reduce((s, r) => s + nilaiBaris(r), 0), [rows]);
  const jumlahDokumen = preview?.rekonsiliasi.jumlah_dokumen ?? null;
  const selisih = jumlahDokumen === null ? null : terbaca - jumlahDokumen;
  const cocok = selisih !== null && Math.abs(selisih) < 0.5;

  async function handleFile(file: File) {
    setLoading(true);
    setError("");
    setResultMsg("");
    setPreview(null);
    setRows(null);
    try {
      const p = await api.repairListPreview(token, file);
      setPreview(p);
      setRows(fromParsed(p.items));
      setHeader({
        nama_perusahaan: p.detected_nama_perusahaan,
        nama_kapal: p.detected_nama_kapal,
        tahun: p.detected_tahun,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal membaca file");
    } finally {
      setLoading(false);
    }
  }

  function updateRow(key: string, field: keyof EditRow, value: string | number | null) {
    setRows((prev) => (prev ? prev.map((r) => (r.key === key ? { ...r, [field]: value } : r)) : prev));
  }

  async function commit() {
    if (!rows) return;
    if (!header.nama_kapal.trim() || !header.tahun.trim()) {
      setError("Nama Kapal dan Tahun wajib diisi sebelum simpan.");
      return;
    }
    if (rows.some((r) => !r.uraian.trim() || !(r.harga > 0))) {
      setError("Masih ada baris dengan Uraian kosong atau Harga 0 — benerin dulu di tabel di bawah.");
      return;
    }
    setLoading(true);
    setMenyimpan(rows.length);
    setError("");
    try {
      const res = await api.repairListCommit(token, {
        nama_perusahaan: header.nama_perusahaan,
        nama_kapal: header.nama_kapal,
        tahun: header.tahun,
        items: rows.map((r) => ({
          kategori_pekerjaan: r.kategori || "-",
          uraian_pekerjaan: r.uraian,
          // Kolom lama tetap diisi supaya baris ini terlihat sama dengan baris lama di
          // layar katalog; angka sebenarnya ada di `volume` + `satuan`.
          volume_satuan: r.satuan || "-",
          harga_satuan: r.harga,
          volume: r.volume,
          satuan: r.satuan || null,
          induk_uraian: r.induk || null,
          keterangan: r.keterangan || null,
        })),
      });
      setResultMsg(`Berhasil simpan ${res.saved} baris (${formatRp(terbaca)}).`);
      setPreview(null);
      setRows(null);
      onImported();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal menyimpan");
    } finally {
      setLoading(false);
      setMenyimpan(0);
    }
  }

  return (
    <div>
      <PilihBerkas terima={[".xlsx", ".xls"]} disabled={loading} onPilih={(f) => void handleFile(f)} />
      {loading && menyimpan === 0 && <p className="mt-3 text-sm text-slate-500">Memproses...</p>}
      {menyimpan > 0 && (
        <div className="mt-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm">
          <p className="font-medium text-slate-800">Menyimpan {menyimpan} baris...</p>
          <p className="mt-0.5 text-slate-600">
            Jangan tutup atau muat ulang halaman ini dulu. Kalau prosesnya terhenti, cek dulu tabelnya
            sebelum mencoba menyimpan lagi — sebagian data bisa jadi sudah masuk.
          </p>
        </div>
      )}
      {error && <p className="mt-3 text-sm font-medium text-red-600">{error}</p>}
      {resultMsg && <p className="mt-3 text-sm text-green-700">{resultMsg}</p>}

      {preview && rows && (
        <div className="mt-5">
          <p className="mb-3 text-xs text-slate-500">
            {preview.detected_jenis_dokumen && <strong>{preview.detected_jenis_dokumen}</strong>}
            {preview.detected_judul && <> — {preview.detected_judul}</>} · sheet: {preview.sheet_name}
          </p>

          <RekonsiliasiBanner
            terbaca={terbaca}
            jumlahDokumen={jumlahDokumen}
            selisih={selisih}
            cocok={cocok}
            ppn={preview.rekonsiliasi.ppn_dokumen}
            total={preview.rekonsiliasi.total_dokumen}
            jumlahBaris={rows.length}
          />

          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <label className="block text-xs font-medium text-slate-600">
              Perusahaan
              <input
                className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm"
                value={header.nama_perusahaan}
                onChange={(e) => setHeader((h) => ({ ...h, nama_perusahaan: e.target.value }))}
              />
            </label>
            <label className="block text-xs font-medium text-slate-600">
              Kapal * <span className="font-normal text-slate-400">(dari nama sheet — periksa)</span>
              <input
                className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm"
                value={header.nama_kapal}
                onChange={(e) => setHeader((h) => ({ ...h, nama_kapal: e.target.value }))}
              />
            </label>
            <label className="block text-xs font-medium text-slate-600">
              Tahun * <span className="font-normal text-slate-400">(tidak ada di berkas)</span>
              <input
                className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm"
                placeholder="mis. 2026"
                value={header.tahun}
                onChange={(e) => setHeader((h) => ({ ...h, tahun: e.target.value }))}
              />
            </label>
          </div>

          {preview.warnings.length > 0 && (
            <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-3">
              <p className="mb-1 text-xs font-bold text-amber-800">
                {preview.warnings.length} hal yang di-flag parser (nomor baris merujuk ke file Excel asli):
              </p>
              <ul className="max-h-32 list-disc overflow-auto pl-5 text-xs text-amber-800">
                {preview.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="mt-4 flex items-center justify-between">
            <p className="text-sm font-bold text-slate-800">{rows.length} baris</p>
            <button
              type="button"
              onClick={() => setRows((prev) => [...(prev ?? []), emptyRow()])}
              className="btn btn-secondary btn-sm"
            >
              <Plus size={13} />
              Tambah Baris Manual
            </button>
          </div>

          <div className="mt-1 max-h-[28rem] overflow-auto rounded-lg border border-blue-200 bg-white">
            <table className="min-w-full text-left text-xs">
              <thead className="sticky top-0 bg-slate-50 uppercase text-slate-500">
                <tr>
                  <th className="px-2 py-2">Kategori</th>
                  <th className="px-2 py-2">Induk / Uraian</th>
                  <th className="px-2 py-2 w-20">Vol</th>
                  <th className="px-2 py-2 w-20">Sat</th>
                  <th className="px-2 py-2 text-right">Harga Satuan</th>
                  <th className="px-2 py-2 text-right">Nilai</th>
                  <th className="px-2 py-2">Keterangan</th>
                  <th className="px-2 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.key} className="border-t border-slate-100 align-top">
                    <td className="px-1 py-1">
                      <input
                        className="cell-input"
                        value={r.kategori}
                        onChange={(e) => updateRow(r.key, "kategori", e.target.value)}
                      />
                    </td>
                    <td className="px-1 py-1">
                      {/* Induk di atas, uraian di bawah: itu bentuk aslinya di dokumen, dan
                          tanpa induknya tiga baris "Excentric P/N ..." terlihat identik. */}
                      <input
                        className="cell-input text-[10px] text-slate-500"
                        placeholder="(tanpa induk)"
                        value={r.induk}
                        onChange={(e) => updateRow(r.key, "induk", e.target.value)}
                      />
                      <input
                        className="cell-input mt-0.5"
                        value={r.uraian}
                        onChange={(e) => updateRow(r.key, "uraian", e.target.value)}
                      />
                    </td>
                    <td className="px-1 py-1">
                      <input
                        type="number"
                        className="cell-input text-right"
                        value={r.volume ?? ""}
                        onChange={(e) =>
                          updateRow(r.key, "volume", e.target.value === "" ? null : Number(e.target.value))
                        }
                      />
                    </td>
                    <td className="px-1 py-1">
                      <input
                        className="cell-input"
                        value={r.satuan}
                        onChange={(e) => updateRow(r.key, "satuan", e.target.value)}
                      />
                    </td>
                    <td className="px-1 py-1">
                      <input
                        type="number"
                        className="cell-input text-right"
                        value={r.harga}
                        onChange={(e) => updateRow(r.key, "harga", Number(e.target.value) || 0)}
                      />
                      {r.harga <= 0 && <span className="block text-[10px] text-red-500">harga wajib &gt; 0</span>}
                    </td>
                    <td className="px-2 py-2 text-right font-medium text-slate-700">
                      {formatRp(nilaiBaris(r))}
                    </td>
                    <td className="px-1 py-1">
                      <input
                        className="cell-input"
                        value={r.keterangan}
                        onChange={(e) => updateRow(r.key, "keterangan", e.target.value)}
                      />
                    </td>
                    <td className="whitespace-nowrap px-1 py-1">
                      <button
                        type="button"
                        onClick={() => setRows((prev) => (prev ? prev.filter((x) => x.key !== r.key) : prev))}
                        className="btn btn-danger px-1.5 py-1 text-[10px]"
                      >
                        <Trash2 size={11} />
                        Hapus
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <button type="button" disabled={loading} onClick={commit} className="btn btn-primary btn-md mt-5">
            <CheckCircle2 size={15} />
            Konfirmasi &amp; Simpan ({rows.length} baris)
          </button>
          {!cocok && (
            <p className="mt-2 text-xs text-amber-700">
              Selisihnya belum nol. Boleh tetap disimpan kalau memang disengaja, tapi periksa dulu —
              biasanya artinya ada baris yang belum terbaca.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/** Palang verifikasi impor. Sengaja ditaruh PALING ATAS, di atas tabelnya: kalau ada baris
 * yang jatuh, itu satu-satunya tempat yang memberitahu — dan sebelum ada ini, satu-satunya
 * cara mengetahuinya adalah menjumlahkan sendiri di luar aplikasi. */
function RekonsiliasiBanner({
  terbaca,
  jumlahDokumen,
  selisih,
  cocok,
  ppn,
  total,
  jumlahBaris,
}: {
  terbaca: number;
  jumlahDokumen: number | null;
  selisih: number | null;
  cocok: boolean;
  ppn: number | null;
  total: number | null;
  jumlahBaris: number;
}) {
  if (jumlahDokumen === null) {
    return (
      <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
        <p className="flex items-center gap-2 font-semibold">
          <TriangleAlert size={15} />
          Baris JUMLAH tidak ketemu di berkas
        </p>
        <p className="mt-1 text-xs">
          {jumlahBaris} baris terbaca senilai {formatRp(terbaca)}, tapi tidak ada angka di dokumen untuk
          dibandingkan. Impor ini tidak bisa diverifikasi otomatis — cocokkan manual sebelum simpan.
        </p>
      </div>
    );
  }
  const warna = cocok
    ? "border-green-300 bg-green-50 text-green-900"
    : "border-red-300 bg-red-50 text-red-900";
  return (
    <div className={`rounded-lg border p-3 text-sm ${warna}`}>
      <p className="flex items-center gap-2 font-semibold">
        {cocok ? <CheckCircle2 size={15} /> : <TriangleAlert size={15} />}
        {cocok ? "Cocok dengan dokumen" : "TIDAK cocok dengan dokumen"}
      </p>
      <div className="mt-1.5 flex flex-wrap gap-x-5 gap-y-1 text-xs">
        <span>
          Katalog ({jumlahBaris} baris): <strong>{formatRp(terbaca)}</strong>
        </span>
        <span>
          JUMLAH di dokumen: <strong>{formatRp(jumlahDokumen)}</strong>
        </span>
        <span>
          Selisih: <strong>{formatRp(selisih ?? 0)}</strong>
        </span>
      </div>
      {(ppn !== null || total !== null) && (
        <p className="mt-1 text-[11px] opacity-80">
          Di dokumen: PPN {ppn === null ? "—" : formatRp(ppn)} · TOTAL {total === null ? "—" : formatRp(total)}.
          PPN tidak ikut disimpan — di aplikasi ini PPN ditambahkan di tingkat dokumen penawaran, bukan
          per baris katalog.
        </p>
      )}
    </div>
  );
}
