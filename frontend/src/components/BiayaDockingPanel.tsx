import { useState } from "react";
import { CheckCircle2 } from "lucide-react";
import { api, type BiayaDockingHasil } from "../lib/api";
import PilihBerkas from "./PilihBerkas";

/** Base64 dari backend -> unduhan .xlsx di browser. */
function unduh(hasil: BiayaDockingHasil) {
  const bytes = Uint8Array.from(atob(hasil.isi), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(
    new Blob([bytes], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = hasil.nama_berkas;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function BiayaDockingPanel({ token }: { token: string }) {
  const [memuat, setMemuat] = useState(false);
  const [error, setError] = useState("");
  const [hasil, setHasil] = useState<BiayaDockingHasil | null>(null);

  async function buat(file: File) {
    setMemuat(true);
    setError("");
    setHasil(null);
    try {
      const h = await api.biayaDocking(token, file);
      unduh(h);
      setHasil(h);
    } catch (e) {
      setError(e instanceof Error ? e.message : "File Biaya Docking gagal dibuat");
    } finally {
      setMemuat(false);
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
      <h3 className="font-display text-lg font-bold text-slate-900">Buat file Biaya Docking dari repair list</h3>
      <p className="mt-2 text-sm text-slate-600">
        Semua baris repair list disalin persis urutannya ke format Biaya Docking (Pekerjaan Induk). Kolom{" "}
        <strong>harga satuan sengaja kosong</strong> — isi di Excel; Jumlah, PPN 11%, TOTAL, dan terbilang ikut
        terhitung sendiri. Tidak ada yang disimpan ke katalog.
      </p>
      <div className="mt-6 max-w-xl">
        <PilihBerkas terima={[".xlsx", ".xls"]} onPilih={(f) => void buat(f)} disabled={memuat} />
      </div>

      {memuat && <p className="mt-4 text-sm text-slate-600">Membaca repair list…</p>}
      {error && (
        <p role="alert" className="mt-4 text-sm text-red-600">
          {error}
        </p>
      )}
      {hasil && (
        <div className="mt-4 max-w-xl">
          <p className="flex items-start gap-2 text-sm text-slate-700">
            <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-emerald-600" />
            <span>
              <strong>{hasil.nama_berkas}</strong> sudah diunduh — {hasil.jumlah_baris} baris pekerjaan. Cek data
              kapal di bagian atas sebelum dikirim.
            </span>
          </p>
          {hasil.peringatan.length > 0 && (
            <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 p-3">
              <p className="mb-1 text-xs font-bold text-amber-800">
                {hasil.peringatan.length} hal yang perlu dicek (nomor baris merujuk ke repair list asli):
              </p>
              <ul className="list-disc pl-5 text-xs text-amber-800">
                {hasil.peringatan.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
