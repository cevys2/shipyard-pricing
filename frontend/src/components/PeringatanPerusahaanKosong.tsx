/** Peringatan, bukan palang: nama PT sering belum diketahui waktu mengimpor, dan kapalnya
 * sudah tercatat sehingga bisa dilengkapi belakangan. Tanpa peringatan ini, KLM. PRANA dan
 * KLM. JEEVA SAMUDERA (5 Oktober 2026) masuk tanpa klien dan di analitik tergabung jadi
 * satu "klien" tanpa nama, padahal pemiliknya berbeda. */
export default function PeringatanPerusahaanKosong({ nama }: { nama: string }) {
  if (nama.trim()) return null;
  return (
    <span className="mt-1 block font-normal text-amber-700">
      Nama perusahaan kosong. Baris tetap bisa disimpan, tapi di analitik semua klien kosong
      tergabung jadi satu. Isi sekarang kalau sudah tahu nama PT-nya.
    </span>
  );
}
