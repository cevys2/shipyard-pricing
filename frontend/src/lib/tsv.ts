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

// Awalan mata uang yang biasa menempel di angka waktu disalin dari invoice, WhatsApp,
// atau Excel. Titiknya opsional supaya "Rp." ikut terbuang -- justru ini yang dulu bikin
// pembaca lama gagal: sesudah "Rp" dibuang tersisa ".150.000" yang diawali titik,
// sehingga tidak cocok dengan pola ribuan yang ter-anchor di awal string.
const MATA_UANG_AWAL = /^\s*(rp|idr|usd|eur|sgd|myr)\s*\.?\s*|^\s*[$€£]\s*/i;
// Ekor "150.000,-" -- lazim di kuitansi, artinya "nol sen", bukan angka negatif.
const EKOR_KOSONG = /[,.]\s*-\s*$/;
// Titik ribuan Indonesia/Eropa: kelompoknya wajib TEPAT tiga angka. "150.000" dan
// "1.234.567,50" cocok; "45.10" tidak, karena angka di belakang titiknya cuma dua --
// itu dibaca desimal. Batas tiga angka inilah yang memisahkan ribuan dari desimal.
const RIBUAN_TITIK = /^-?\d{1,3}(\.\d{3})+(,\d+)?$/;
// Kebalikannya, untuk harga bergaya Inggris/USD: "1,234.56".
const RIBUAN_KOMA = /^-?\d{1,3}(,\d{3})+(\.\d+)?$/;
const DESIMAL_KOMA = /^-?\d+,\d+$/;
const POLOS = /^-?\d+(\.\d+)?$/;

/** Baca satu sel harga, dari mana pun asalnya.
 *
 * Fungsi ini ada karena dulu ada TIGA pembaca angka yang berbeda perilaku untuk masukan
 * yang sama: `angkaTempel` di berkas ini, `cellsToDraft` di EditableCatalogTable, dan
 * `parse` di NumberInput. "150.000" tersimpan 150000 di satu jalur dan 150 di jalur lain
 * -- salah 1000x, tapi angkanya tetap masuk akal sekilas, jadi lolos tanpa jejak. Dan
 * "Rp.150.000" gagal jadi 0 di ketiga-tiganya.
 *
 * Yang dikembalikan bukan cuma angkanya:
 *
 * - `ditafsirkan` menandai bahwa fungsi ini MENAFSIRKAN, bukan mengambil apa adanya:
 *   membuang awalan mata uang, membuang ekor ",-", atau membaca titik/koma sebagai
 *   pemisah ribuan. Penafsiran yang benar tapi diam tetap membuat orang tidak punya cara
 *   memeriksa, jadi pemanggil wajib punya bahan untuk mengatakannya terang-terangan.
 * - `dikenali` memisahkan "nol beneran" dari "gagal baca". Tanpa ini "abc" dan "0" tidak
 *   bisa dibedakan, dan sampah tersimpan diam-diam sebagai harga 0.
 *
 * Catatan soal keputusan yang paling mungkin salah: "2.500" dibaca 2500, bukan 2,5.
 * Dalam konteks harga rupiah itu hampir selalu benar, tapi kalau suatu saat ada satuan
 * berharga di bawah sepuluh rupiah dengan tiga desimal, pembacaan ini akan meleset --
 * dan yang menyelamatkannya cuma `ditafsirkan` yang ditampilkan ke pengguna.
 */
export function bacaAngkaUang(raw: string): { nilai: number; ditafsirkan: boolean; dikenali: boolean } {
  if (raw == null) return { nilai: 0, ditafsirkan: false, dikenali: false };
  let t = String(raw).trim();
  if (!t) return { nilai: 0, ditafsirkan: false, dikenali: false };
  let ditafsirkan = false;
  const sebelum = t;
  t = t.replace(MATA_UANG_AWAL, "").replace(EKOR_KOSONG, "").trim();
  t = t.replace(/\s/g, "").replace(/[^\d.,-]/g, "");
  if (t !== sebelum.replace(/\s/g, "")) ditafsirkan = true;
  if (!t || t === "-") return { nilai: 0, ditafsirkan: false, dikenali: false };

  const jadi = (n: number, tafsir: boolean) => ({
    nilai: Number.isFinite(n) ? n : 0,
    ditafsirkan: ditafsirkan || tafsir,
    dikenali: Number.isFinite(n),
  });

  if (RIBUAN_TITIK.test(t)) return jadi(Number(t.replace(/\./g, "").replace(",", ".")), true);
  if (RIBUAN_KOMA.test(t)) return jadi(Number(t.replace(/,/g, "")), true);
  if (DESIMAL_KOMA.test(t)) return jadi(Number(t.replace(",", ".")), false);
  if (POLOS.test(t)) return jadi(Number(t), false);
  return { nilai: 0, ditafsirkan: false, dikenali: false };
}

/** Pembungkus tipis di atas `bacaAngkaUang`, dipertahankan supaya pemanggil lama tidak
 * perlu disentuh sama sekali di sesi yang sama dengan perubahan logikanya. Tanda tangannya
 * sengaja tidak berubah; yang memanggilnya dipindahkan satu per satu belakangan, supaya
 * tiap diff-nya bisa diperiksa sendiri-sendiri.
 *
 * Efek sampingnya: pemanggil `angkaTempel` belum bisa membedakan "abc" dari "0", karena
 * `dikenali` tidak ikut diteruskan. Itu yang jadi alasan pemindahannya nanti. */
export function angkaTempel(raw: string): { nilai: number; ditafsirkan: boolean } {
  const r = bacaAngkaUang(raw);
  return { nilai: r.nilai, ditafsirkan: r.ditafsirkan };
}
