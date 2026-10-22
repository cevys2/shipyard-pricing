import { useRef, useState } from "react";
import { AlertTriangle, ChevronDown, ChevronRight, Info, Search } from "lucide-react";
import {
  api,
  formatRp,
  type AuthUser,
  type HargaWajar,
  type HargaWajarDocking,
  type HargaWajarKelompok,
} from "../lib/api";

type Props = { auth: AuthUser };

const CONTOH = ["sandblasting", "pengecatan lambung", "elbow 2"];

/** Layar Harga Wajar: "pekerjaan ini biasanya dihargai berapa per satuan?"
 *
 * Dipakai untuk item yang harganya tidak diingat waktu menyusun penawaran. Semua keputusan
 * soal kapan angka ringkas boleh tampil ada di backend (`services/harga_wajar.py`); layar ini
 * cuma membaca `tampilkan_ringkas` dan `alasan`, supaya kalimat penjelasnya tidak pernah
 * berbeda dari yang benar-benar dihitung. */
export default function HargaWajarPanel({ auth }: Props) {
  const [q, setQ] = useState("");
  const [hasil, setHasil] = useState<HargaWajar | null>(null);
  const [memuat, setMemuat] = useState(false);
  const [error, setError] = useState("");
  // Pencarian yang lebih dulu dikirim bisa selesai belakangan. Tanpa nomor ini, hasil
  // "elbow" yang lambat bisa menimpa hasil "elbow 2" yang sudah tampil.
  const nomor = useRef(0);

  async function cari(kata: string) {
    const teks = kata.trim();
    if (!teks) return;
    const ini = ++nomor.current;
    setMemuat(true);
    setError("");
    try {
      const r = await api.hargaWajar(auth.token, teks);
      if (ini === nomor.current) setHasil(r);
    } catch (e) {
      if (ini === nomor.current) {
        setHasil(null);
        setError(e instanceof Error ? e.message : "Pencarian gagal");
      }
    } finally {
      if (ini === nomor.current) setMemuat(false);
    }
  }

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void cari(q);
          }}
          className="flex flex-col gap-3 sm:flex-row"
        >
          <label htmlFor="hw-cari" className="sr-only">
            Nama pekerjaan
          </label>
          <div className="relative flex-1">
            <Search
              size={16}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
            />
            <input
              id="hw-cari"
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Nama pekerjaan, mis. sandblasting atau elbow 2"
              // Bukan `.cell-input`: kelas itu ditulis di luar layer Tailwind, jadi `px-2`-nya
              // mengalahkan `pl-9` dan ikon kaca pembesar menimpa huruf pertama.
              className="h-11 w-full rounded-lg border border-slate-300 bg-white pl-9 pr-3 text-sm outline-none transition-colors focus:border-[var(--marine)]"
              autoFocus
            />
          </div>
          <button
            type="submit"
            disabled={!q.trim() || memuat}
            className="btn btn-primary btn-md h-11 justify-center px-5 text-sm"
          >
            {memuat ? "Mencari…" : "Cari harga"}
          </button>
        </form>
        <p className="mt-3 text-xs text-slate-500">
          Ejaannya harus tepat. Pencarian di sini sengaja tidak memaafkan salah ketik, supaya pekerjaan
          yang namanya mirip (sandblasting dan sweepblasting) tidak tercampur jadi satu harga. Ukuran
          dicocokkan utuh: "elbow 2" tidak ikut menarik elbow 12, 2,5, atau 2 1/2.
        </p>
      </section>

      {error && (
        <div className="flex gap-2.5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <p>
            Pencarian gagal: {error.replace(/[.\s]+$/, "")}. Coba tekan <strong>Cari harga</strong>{" "}
            sekali lagi. Kalau tetap gagal, muat ulang halaman, atau masuk lagi lewat Portal kalau
            sesinya sudah habis.
          </p>
        </div>
      )}

      {!hasil && !error && (
        <Awal
          onContoh={(c) => {
            setQ(c);
            void cari(c);
          }}
          memuat={memuat}
        />
      )}

      {hasil && <Hasil hasil={hasil} />}
    </div>
  );
}

function Awal({ onContoh, memuat }: { onContoh: (c: string) => void; memuat: boolean }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 px-6 py-8 text-sm text-slate-600">
      <p className="font-medium text-slate-800">Ketik nama pekerjaan, lalu tekan Cari harga.</p>
      <p className="mt-1">
        Hasilnya dikelompokkan per satuan (m², kg, Ls, …). Kalau datanya cukup, ada harga tengah;
        kalau belum, ada harga terakhir lengkap dengan kapal asalnya. Coba salah satu:
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        {CONTOH.map((c) => (
          <button
            key={c}
            type="button"
            disabled={memuat}
            onClick={() => onContoh(c)}
            className="btn btn-secondary h-11 px-4 text-sm"
          >
            {c}
          </button>
        ))}
      </div>
    </div>
  );
}

function Hasil({ hasil }: { hasil: HargaWajar }) {
  const dicari = hasil.kata.map((k) => `"${k}"`).join(" + ");

  if (hasil.terlalu_banyak) {
    return (
      <Kotak nada="amber">
        Kata kunci {dicari} cocok dengan <strong>lebih dari {hasil.batas_baris.toLocaleString("id-ID")} baris</strong>,
        terlalu banyak untuk satu harga yang masuk akal. Perjelas, misalnya dengan menambah bagian kapal
        atau ukuran ("pengecatan lambung", "elbow 2").
      </Kotak>
    );
  }

  if (hasil.kata.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-300 px-6 py-8 text-sm text-slate-600">
        <p className="font-medium text-slate-800">Ketik nama pekerjaan dengan huruf atau angka.</p>
      </div>
    );
  }

  if (hasil.kelompok.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-300 px-6 py-8 text-sm text-slate-600">
        <p className="font-medium text-slate-800">
          Tidak ada baris berharga yang uraiannya memuat {dicari}.
        </p>
        <p className="mt-1">
          Periksa ejaannya dulu, karena salah satu huruf saja sudah membuat baris tidak ketemu. Kalau
          ejaannya sudah benar, coba kata yang lebih umum, misalnya tanpa ukuran. Baris yang harganya
          kosong atau nol memang tidak ikut.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <p className="text-sm text-slate-600">
        <strong className="text-slate-900">{(hasil.total_cocok ?? 0).toLocaleString("id-ID")} baris</strong>{" "}
        cocok dengan {dicari}, dalam {hasil.kelompok.length} kelompok satuan.
      </p>
      {hasil.kelompok.map((k) => (
        <KelompokKartu key={k.satuan ?? "-"} k={k} minKapal={hasil.aturan.min_kapal} />
      ))}
    </div>
  );
}

function KelompokKartu({ k, minKapal }: { k: HargaWajarKelompok; minKapal: number }) {
  const per = k.satuan ? ` / ${k.satuan}` : "";
  const rentangTahun =
    k.tahun_min && k.tahun_max
      ? k.tahun_min === k.tahun_max
        ? k.tahun_min
        : `${k.tahun_min}–${k.tahun_max}`
      : "tahun tidak tercatat";

  return (
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-slate-100 px-5 py-3">
        <h3 className="font-display text-base font-bold text-slate-900">
          {k.satuan ? `Per ${k.satuan}` : "Satuan tidak tercatat"}
        </h3>
        {k.borongan && (
          <Lencana
            className="bg-amber-100 text-amber-800"
            title="Satu Ls di kapal kecil dan kapal besar bisa berarti lingkup kerja yang jauh berbeda."
          >
            borongan
          </Lencana>
        )}
        {k.satuan && !k.dikenali && (
          <Lencana
            className="bg-slate-100 text-slate-700"
            title="Ejaan satuan ini belum masuk daftar satuan baku, jadi belum digabung dengan ejaan lain yang mungkin sama artinya."
          >
            ejaan belum diperiksa
          </Lencana>
        )}
        <span className="text-xs text-slate-500">
          {k.n_baris.toLocaleString("id-ID")} baris · {k.n_kapal} kapal · {rentangTahun}
        </span>
        {k.ejaan.length > 1 && (
          <span className="text-xs text-slate-400">ditulis: {k.ejaan.join(", ")}</span>
        )}
      </header>

      <div className="px-5 py-4">
        <Ringkasan k={k} per={per} minKapal={minKapal} />
      </div>

      <TabelDocking docking={k.docking} per={per} />
    </section>
  );
}

function Ringkasan({ k, per, minKapal }: { k: HargaWajarKelompok; per: string; minKapal: number }) {
  if (k.tampilkan_ringkas && k.ringkas) {
    return (
      <div className="space-y-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Harga tengah</p>
          <p className="mt-1 font-display text-3xl font-bold text-slate-900">
            {formatRp(k.ringkas.median)}
            <span className="text-base font-medium text-slate-500">{per}</span>
          </p>
          {/* Harga terendah-tertinggi yang benar-benar tertulis, bukan kuartil: dengan 3 docking,
              rentang kuartil cuma memuat satu di antaranya, jadi kalimat "separuh docking ada di
              X – Y" tidak benar justru di kasus yang paling sering. */}
          <p className="mt-1 text-sm text-slate-600">
            Harga yang tercatat {formatRp(k.harga_min)} – {formatRp(k.harga_max)}, dari{" "}
            {k.n_baris.toLocaleString("id-ID")} baris di {k.n_kapal} kapal. Harga tengahnya dihitung
            dengan satu suara per kapal per tahun.
          </p>
        </div>
        {k.terakhir && (
          <div className="border-t border-slate-100 pt-3">
            <Patokan terakhir={k.terakhir} per={per} kecil />
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {k.alasan === "kapal_kurang" && (
        <Kotak nada="biru">
          Pembandingnya baru <strong>{k.n_kapal} kapal</strong>, sedangkan harga tengah butuh minimal{" "}
          {minKapal}. Pakai harga terakhir di bawah sebagai patokan, dan lihat daftarnya per kapal.
        </Kotak>
      )}
      {k.alasan === "menyebar" && (
        <Kotak nada="amber">
          <strong>Harganya sangat bervariasi antar kapal:</strong> yang tercatat dari{" "}
          {formatRp(k.harga_min)} sampai {formatRp(k.harga_max)}
          {k.harga_min > 0 &&
            ` (${(k.harga_max / k.harga_min).toLocaleString("id-ID", { maximumFractionDigits: 1 })}× lipat)`}
          . Biasanya karena hasil nego atau lingkup kerja yang beda, jadi harga tengahnya tidak
          dipakai sebagai jawaban. Lihat per kapal.
        </Kotak>
      )}
      {k.alasan === "tanpa_satuan" && (
        <Kotak nada="amber">
          Baris-baris ini tidak mencatat satuannya, jadi harganya per apa tidak diketahui. Jangan
          dibandingkan langsung dengan kelompok lain.
        </Kotak>
      )}
      {k.terakhir && <Patokan terakhir={k.terakhir} per={per} />}
    </div>
  );
}

/** Patokan untuk bos: harga terakhir, SELALU dengan asalnya. Kalau tahun terbaru punya
 * beberapa docking, semuanya ditampilkan -- backend sengaja tidak memilih salah satu. */
function Patokan({
  terakhir,
  per,
  kecil,
}: {
  terakhir: NonNullable<HargaWajarKelompok["terakhir"]>;
  per: string;
  kecil?: boolean;
}) {
  const BATAS = 4;
  const tampil = terakhir.docking.slice(0, BATAS);
  const sisa = terakhir.docking.length - tampil.length;

  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        Harga terakhir ({terakhir.tahun})
      </p>
      <ul className="mt-1 space-y-1">
        {tampil.map((d) => (
          <li key={d.nama_kapal}>
            <span
              className={`font-display font-bold text-slate-900 ${kecil ? "text-base" : "text-2xl"}`}
            >
              {/* Kalau docking ini punya beberapa baris berbeda harga, nilai tengahnya tidak
                  tertulis di dokumen mana pun -- padahal angka inilah yang disalin ke penawaran.
                  Jadi yang ditampilkan harga aslinya. */}
              {d.harga_min === d.harga_max
                ? formatRp(d.harga_min)
                : `${formatRp(d.harga_min)} – ${formatRp(d.harga_max)}`}
              <span className="text-sm font-medium text-slate-500">{per}</span>
            </span>{" "}
            <span className="ml-1.5 text-sm text-slate-600">
              — {d.nama_kapal || "kapal tidak tercatat"}
              {d.klien.length > 0 && ` · ${d.klien.join(" / ")}`}
              {d.n_baris > 1 && ` (${d.n_baris} baris)`}
            </span>
          </li>
        ))}
      </ul>
      {sisa > 0 && (
        <p className="mt-1 text-xs text-slate-500">
          dan {sisa} docking lain di {terakhir.tahun}, lihat tabel di bawah.
        </p>
      )}
      {!kecil && (
        <p className="mt-2 text-xs text-slate-500">
          Ini kesepakatan dengan kapal di atas, bukan harga pasar. Bisa saja hasil nego yang alot,
          jadi cek asalnya sebelum dipakai.
        </p>
      )}
    </div>
  );
}

function TabelDocking({ docking, per }: { docking: HargaWajarDocking[]; per: string }) {
  const [buka, setBuka] = useState<Set<string>>(new Set());
  const kunci = (d: HargaWajarDocking) => `${d.nama_kapal}|${d.tahun}`;

  function alih(k: string) {
    setBuka((s) => {
      const baru = new Set(s);
      if (baru.has(k)) baru.delete(k);
      else baru.add(k);
      return baru;
    });
  }

  return (
    <div className="overflow-x-auto border-t border-slate-100">
      <table className="min-w-full text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase text-slate-500">
          <tr>
            <th className="px-5 py-2.5">Tahun</th>
            <th className="px-4 py-2.5">Kapal</th>
            <th className="hidden px-4 py-2.5 md:table-cell">Klien</th>
            <th className="px-4 py-2.5 text-right">Harga{per}</th>
            <th className="px-4 py-2.5">Rincian</th>
          </tr>
        </thead>
        <tbody>
          {docking.map((d) => {
            const k = kunci(d);
            const terbuka = buka.has(k);
            return (
              <FragmenDocking
                key={k}
                d={d}
                terbuka={terbuka}
                onAlih={() => alih(k)}
              />
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function FragmenDocking({
  d,
  terbuka,
  onAlih,
}: {
  d: HargaWajarDocking;
  terbuka: boolean;
  onAlih: () => void;
}) {
  const Panah = terbuka ? ChevronDown : ChevronRight;
  return (
    <>
      <tr className="border-t border-slate-100 align-top">
        <td className="whitespace-nowrap px-5 py-2.5 text-xs tabular-nums text-slate-500">
          {d.tahun || "-"}
        </td>
        <td className="px-4 py-2.5 font-medium text-slate-800">
          {d.nama_kapal || "kapal tidak tercatat"}
          {/* Di layar sempit kolom Klien disembunyikan; kliennya pindah ke bawah nama kapal,
              karena untuk pekerjaan yang dinego justru kliennya yang paling ingin dilihat. */}
          {d.klien.length > 0 && (
            <span className="block text-xs font-normal text-slate-500 md:hidden">{d.klien.join(" / ")}</span>
          )}
          {d.tipe.includes("Addendum") && (
            <Lencana className="ml-2 bg-sky-100 text-sky-800" title="Sebagian barisnya dari Addendum (pekerjaan tambahan).">
              addendum
            </Lencana>
          )}
        </td>
        <td className="hidden px-4 py-2.5 text-xs text-slate-500 md:table-cell">{d.klien.join(" / ") || "-"}</td>
        <td className="whitespace-nowrap px-4 py-2.5 text-right tabular-nums">
          <span className="font-medium text-slate-900">{formatRp(d.harga)}</span>
          {d.harga_min !== d.harga_max && (
            <span className="block text-xs text-slate-500">
              {formatRp(d.harga_min)} – {formatRp(d.harga_max)}
            </span>
          )}
        </td>
        <td className="px-4 py-1">
          <button
            type="button"
            onClick={onAlih}
            aria-expanded={terbuka}
            className="btn btn-ghost min-h-11 whitespace-nowrap px-2 text-xs"
          >
            <Panah size={14} />
            {d.n_baris} baris
          </button>
        </td>
      </tr>
      {terbuka && (
        <tr className="bg-slate-50/70">
          <td colSpan={5} className="px-5 pb-3 pt-1">
            <ul className="divide-y divide-slate-200/70">
              {d.baris.map((b) => (
                <li key={b.id} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5 py-1.5">
                  <span className="min-w-0 flex-1">
                    <span className="text-slate-800">{b.uraian}</span>
                    {b.induk_uraian && (
                      <span className="block text-xs text-slate-500">Bagian dari: {b.induk_uraian}</span>
                    )}
                  </span>
                  <span className="whitespace-nowrap text-xs text-slate-500">
                    {b.tipe_perjanjian === "Addendum" && "Addendum · "}
                    {b.satuan_tertulis && `ditulis "${b.satuan_tertulis}" · `}
                    <span className="font-medium tabular-nums text-slate-800">{formatRp(b.harga_satuan)}</span>
                  </span>
                </li>
              ))}
            </ul>
          </td>
        </tr>
      )}
    </>
  );
}

function Lencana({
  children,
  className,
  title,
}: {
  children: React.ReactNode;
  className: string;
  title?: string;
}) {
  return (
    <span title={title} className={`rounded px-1.5 py-0.5 text-xs font-medium ${className}`}>
      {children}
    </span>
  );
}

function Kotak({ nada, children }: { nada: "amber" | "biru"; children: React.ReactNode }) {
  const gaya =
    nada === "amber"
      ? "border-amber-200 bg-amber-50 text-amber-900"
      : "border-sky-200 bg-sky-50 text-sky-900";
  const Ikon = nada === "amber" ? AlertTriangle : Info;
  return (
    <div className={`flex gap-2.5 rounded-lg border px-4 py-3 text-sm ${gaya}`}>
      <Ikon size={16} className="mt-0.5 shrink-0" />
      <p>{children}</p>
    </div>
  );
}
