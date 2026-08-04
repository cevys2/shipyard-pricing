/**
 * Parses text pasted from Excel/Sheets (tab-separated columns, newline-separated rows)
 * into an array of row arrays. Handles \r\n line endings and trims trailing empty rows.
 */
export function parseTsv(text: string): string[][] {
  const rows = text
    .replace(/\r\n/g, "\n")
    .split("\n")
    .map((line) => line.split("\t").map((cell) => cell.trim()))
    .filter((cells) => cells.some((c) => c !== ""));
  return rows;
}

// Titik ribuan Indonesia: satu sampai tiga angka, lalu kelompok tiga angka, boleh
// diakhiri koma desimal. "150.000" dan "1.234.567,50" cocok; "45.10" tidak, karena
// angka di belakang titiknya cuma dua.
const RIBUAN_ID = /^-?\d{1,3}(\.\d{3})+(,\d+)?$/;

/** Baca satu sel angka dari tempelan.
 *
 * `NumberInput` sengaja TIDAK menebak titik ribuan: "1.050" ambigu antara seribu lima
 * puluh dan satu koma nol lima, dan menebaknya berarti mengubah harga diam-diam. Alasan
 * itu berlaku untuk orang yang mengetik satu angka sambil melihat hasilnya.
 *
 * Untuk tempelan puluhan baris keadaannya terbalik: tidak ada yang memeriksa satu per
 * satu, dan "150.000" yang terbaca 150 adalah kesalahan 1000x yang lolos tanpa jejak.
 * Jadi di sini pola ribuan dibaca sebagai ribuan -- tapi tiap sel yang ditafsirkan begitu
 * dilaporkan balik lewat `ditafsirkan`, supaya penafsirannya bisa dikatakan terang-terangan
 * ke pengguna alih-alih terjadi diam-diam.
 */
export function angkaTempel(raw: string): { nilai: number; ditafsirkan: boolean } {
  const t = raw.replace(/[^\d.,-]/g, "").trim();
  if (RIBUAN_ID.test(t)) {
    return { nilai: Number(t.replace(/\./g, "").replace(",", ".")) || 0, ditafsirkan: true };
  }
  return { nilai: Number(t.replace(",", ".")) || 0, ditafsirkan: false };
}
