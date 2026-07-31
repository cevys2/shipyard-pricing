import { useState } from "react";

/** Input angka yang tidak melawan jari pengguna saat mengetik.
 *
 * Masalah pada `<input type="number" value={String(angka)}>`: mengetik "49.0" bikin nilai
 * sementara "49." yang di-parse jadi 49, lalu di-render balik sebagai "49" -- titiknya
 * terhapus tepat setelah diketik, jadi desimal mustahil dimasukkan. Hal yang sama terjadi
 * saat mengosongkan field: `Number("") || 0` memaksanya jadi "0".
 *
 * Solusinya menyimpan teks mentah selama field difokus, dan baru menyelaraskan tampilan
 * dengan nilai numerik saat field ditinggalkan. Induknya tetap menerima number.
 *
 * Koma diterima sebagai pemisah desimal ("49,5") karena itu kebiasaan penulisan di sini dan
 * harga di quotation MAN memang ditulis begitu. Titik sebagai pemisah ribuan TIDAK ditebak:
 * "1.050" ambigu antara seribu lima puluh dan 1,05 -- menebaknya berisiko mengubah harga
 * secara diam-diam, jadi dibiarkan apa adanya sebagai desimal.
 */
export default function NumberInput({
  value,
  onChange,
  integer = false,
  className = "",
  ariaLabel,
}: {
  value: number;
  onChange: (n: number) => void;
  integer?: boolean;
  className?: string;
  ariaLabel?: string;
}) {
  const [teks, setTeks] = useState<string | null>(null);

  function parse(raw: string): number {
    const bersih = raw.replace(/\s/g, "").replace(",", ".");
    const n = integer ? parseInt(bersih, 10) : parseFloat(bersih);
    return Number.isFinite(n) ? n : 0;
  }

  return (
    <input
      type="text"
      inputMode={integer ? "numeric" : "decimal"}
      aria-label={ariaLabel}
      className={className}
      value={teks ?? String(value)}
      onChange={(e) => {
        setTeks(e.target.value);
        onChange(parse(e.target.value));
      }}
      onBlur={() => setTeks(null)}
    />
  );
}
