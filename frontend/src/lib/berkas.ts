/** Periksa apakah berkas yang dipilih atau ditarik ke layar memang jenis yang bisa dibaca.
 *
 * Atribut `accept` di <input type="file"> cuma menyaring dialog pilih berkas, dan itu pun
 * bisa dilewati lewat pilihan "All files". Berkas yang DITARIK ke layar tidak disaring sama
 * sekali. Tanpa pemeriksaan ini, PDF yang salah tarik baru ditolak backend, dengan pesan
 * yang tidak menyebut apa salahnya.
 *
 * Kembalikan `null` kalau berkasnya boleh. Kalau tidak boleh, kembalikan kalimat untuk
 * ditampilkan di layar: sebut apa yang salah DAN berkas apa yang diterima.
 *
 *   cekBerkas("REALISASI MISHIMA.xlsx", [".xlsx", ".xls"])  -> null
 *   cekBerkas("foto kapal.pdf", [".xlsx", ".xls"])          -> "Berkas .pdf tidak bisa ..."
 *
 * Aturannya dijaga `tests/berkas.test.ts`. Jalankan: `npm test` dari folder frontend.
 */
export function cekBerkas(namaBerkas: string, terima: string[]): string | null {
  const posisi = namaBerkas.lastIndexOf(".");
  const ext = namaBerkas.slice(posisi).toLowerCase();
  if (terima.includes(ext)) return null;
  return `Extension ${ext} tidak sesuai dengan aturan. Pilih berkas ${terima.join(", ")}.`;
}
