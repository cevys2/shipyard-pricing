import { useState, type DragEvent } from "react";
import { FileSpreadsheet, FileUp } from "lucide-react";
import { cekBerkas } from "../lib/berkas";

type Props = {
  /** Ekstensi yang diterima, huruf kecil dengan titik: [".xlsx", ".xls"]. */
  terima: string[];
  onPilih: (file: File) => void;
  disabled?: boolean;
};

function formatUkuran(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toLocaleString("id-ID", { maximumFractionDigits: 1 })} MB`;
}

/** Pengganti <input type="file"> bawaan browser di tab Import.
 *
 * Yang bawaan menampilkan "Choose File / No file chosen" dalam bahasa Inggris, dan tidak
 * bisa dirapikan dengan CSS. Di sini input aslinya tetap ada (jadi dialog pilih berkas,
 * keyboard, dan pembaca layar tetap jalan), cuma disembunyikan di balik kotak yang bisa
 * diklik atau dijatuhi berkas. */
export default function PilihBerkas({ terima, onPilih, disabled = false }: Props) {
  const [terpilih, setTerpilih] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [seret, setSeret] = useState(false);

  function terimaBerkas(file: File) {
    const salah = cekBerkas(file.name, terima);
    if (salah) {
      setError(salah);
      setTerpilih(null);
      return;
    }
    setError("");
    setTerpilih(file);
    onPilih(file);
  }

  function onDrop(e: DragEvent<HTMLLabelElement>) {
    e.preventDefault();
    setSeret(false);
    if (disabled) return;
    const f = e.dataTransfer.files[0];
    if (f) terimaBerkas(f);
  }

  return (
    <div>
      <label
        className="drop-zone"
        data-seret={seret ? "ya" : undefined}
        aria-disabled={disabled || undefined}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setSeret(true);
        }}
        // dragleave juga menyala waktu kursor pindah ke elemen anak di dalam kotak;
        // abaikan yang itu supaya sorotannya tidak berkedip.
        onDragLeave={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setSeret(false);
        }}
        onDrop={onDrop}
      >
        <input
          type="file"
          accept={terima.join(",")}
          className="sr-only"
          disabled={disabled}
          onChange={(e) => {
            const f = e.target.files?.[0];
            // Dikosongkan supaya memilih berkas yang SAMA lagi (misalnya sesudah dibetulkan
            // di Excel) tetap dibaca ulang. Input bawaan diam saja kalau namanya sama.
            e.target.value = "";
            if (f) terimaBerkas(f);
          }}
        />
        <span className="flex h-11 w-11 items-center justify-center rounded-full border border-slate-200 bg-white text-[var(--marine)] shadow-sm">
          <FileUp size={20} />
        </span>
        <span className="text-sm font-semibold text-slate-800">
          Pilih berkas <span className="font-normal text-slate-500">atau tarik ke sini</span>
        </span>
        <span className="text-xs text-slate-500">Format {terima.join(", ")}</span>
      </label>

      {terpilih && !error && (
        <p className="mt-2 flex items-center gap-1.5 text-xs text-slate-600">
          <FileSpreadsheet size={14} className="shrink-0 text-slate-400" />
          <span className="truncate font-medium text-slate-700">{terpilih.name}</span>
          <span className="shrink-0 text-slate-400">· {formatUkuran(terpilih.size)}</span>
        </p>
      )}
      {error && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {error}
        </p>
      )}
    </div>
  );
}
