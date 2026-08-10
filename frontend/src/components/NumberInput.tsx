import { useState, type ClipboardEvent } from "react";
import { bacaAngkaUang } from "../lib/tsv";

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
 *
 * MENGETIK dan MENEMPEL sengaja diperlakukan berbeda, dan bedanya bukan soal kepraktisan:
 *
 * Orang yang mengetik sedang menyusun angka sambil melihat hasilnya. Tiap penekanan tombol
 * dia yang putuskan, jadi dia berhak atas persis apa yang dia ketik -- itu alasan "1.050"
 * di atas dibiarkan jadi 1,05.
 *
 * Orang yang menempel sedang memindahkan isi yang sudah jadi dari tempat lain, dan isi itu
 * membawa format aslinya: "Rp.150.000" dari WhatsApp, "150.000,-" dari kuitansi, "1.234.567,50"
 * dari Excel. Tidak ada yang "diketiknya" untuk dihormati di situ; yang ada cuma bentuk asing
 * yang dulu semuanya jadi 0 tanpa pemberitahuan apa pun. Jadi tempelan dibaca lewat
 * `bacaAngkaUang`, sama seperti semua jalur harga yang lain.
 */
export default function NumberInput({
  value,
  onChange,
  integer = false,
  className = "",
  ariaLabel,
  onDitafsirkan,
}: {
  value: number;
  onChange: (n: number) => void;
  integer?: boolean;
  className?: string;
  ariaLabel?: string;
  /** Dipanggil kalau tempelannya ditafsirkan, bukan diambil apa adanya. Ada supaya induk
   * BISA menampilkan catatan "Rp.150.000 dibaca sebagai 150.000" tanpa komponen ini sendiri
   * memutuskan tampilan. Tidak diberikan berarti tidak terjadi apa-apa. */
  onDitafsirkan?: (asal: string, jadi: number) => void;
}) {
  const [teks, setTeks] = useState<string | null>(null);

  function parse(raw: string): number {
    const bersih = raw.replace(/\s/g, "").replace(",", ".");
    const n = integer ? parseInt(bersih, 10) : parseFloat(bersih);
    return Number.isFinite(n) ? n : 0;
  }

  function tempel(e: ClipboardEvent<HTMLInputElement>) {
    const isi = e.clipboardData.getData("text");
    // Tempelan banyak sel bukan urusan satu kotak. Dibiarkan lewat supaya jalur paste
    // massal di komponen induk yang menanganinya, seperti sebelumnya.
    if (isi.includes("\n") || isi.includes("\t")) return;
    e.preventDefault();

    const r = bacaAngkaUang(isi);
    // Tempelan yang tidak terbaca tidak mengubah apa pun. Menimpa harga yang sudah benar
    // dengan 0 karena salah salin itu kerusakan yang jauh lebih mahal daripada tempelan
    // yang kelihatan tidak berefek.
    if (!r.dikenali) return;

    const nilai = integer ? Math.trunc(r.nilai) : r.nilai;
    setTeks(String(nilai));
    onChange(nilai);
    // Pemotongan desimal di field bilangan bulat juga penafsiran: "2024,5" jadi 2024 tanpa
    // ini akan berubah diam-diam, persis hal yang mau dihindari.
    if (r.ditafsirkan || nilai !== r.nilai) onDitafsirkan?.(isi.trim(), nilai);
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
      onPaste={tempel}
      onBlur={() => setTeks(null)}
    />
  );
}
