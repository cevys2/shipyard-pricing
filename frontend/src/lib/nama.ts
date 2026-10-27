/** Awalan jenis kapal yang ada di katalog (27 Oktober 2026). Awalan baru tambahkan di sini. */
export const AWALAN_KAPAL = ["KMP", "KLM", "KN", "LCT", "MV"];
export const AWALAN_PERUSAHAAN = ["PT"];

const kunci = (s: string) => s.toUpperCase().replace(/[.\s]+/g, "");

/** Rapikan nama kapal/perusahaan dari kotak isian impor: huruf besar, spasi ganda dibuang,
 * dan awalan yang sudah ditulis diberi titik -- "kmp  prathita iv" jadi "KMP. PRATHITA IV".
 *
 * Awalan TIDAK ditambahkan kalau tidak ditulis: katalog punya lima jenis kapal (KMP, KLM, KN,
 * LCT, MV), dan BASARNAS bukan PT. Menebak awalannya berarti mengarang data.
 *
 * Kalau nama yang sama sudah tersimpan dan bedanya cuma titik atau spasi, ejaan yang
 * tersimpan yang dipakai. Di database ada "KMP PRATHITA IV", "KN SAR 207", dan "PT MUNIC
 * LINE" tanpa titik; tanpa aturan ini impor berikutnya kapal yang sama terhitung kapal
 * kedua di dropdown dan Analitik, karena nama kapal dibandingkan persis. */
export function rapikanNama(teks: string, awalan: string[], sudahAda: string[] = []): string {
  let t = teks.toUpperCase().replace(/\s+/g, " ").trim();
  const m = t.match(/^([A-Z]+)(?:\. ?| )(.+)$/);
  if (m && awalan.includes(m[1])) t = `${m[1]}. ${m[2]}`;
  if (sudahAda.includes(t)) return t;
  return sudahAda.find((s) => kunci(s) === kunci(t)) ?? t;
}

/** Kotak Perusahaan + Kapal di panel impor. `ada` = daftar dari /catalog/filters; null kalau
 * gagal diambil, dan perapiannya tetap jalan tanpa pencocokan ejaan lama. */
export function rapikanHeader<T extends { nama_perusahaan: string; nama_kapal: string }>(
  h: T,
  ada: { perusahaan: string[]; kapal: string[] } | null,
): T {
  return {
    ...h,
    nama_perusahaan: rapikanNama(h.nama_perusahaan, AWALAN_PERUSAHAAN, ada?.perusahaan),
    nama_kapal: rapikanNama(h.nama_kapal, AWALAN_KAPAL, ada?.kapal),
  };
}
