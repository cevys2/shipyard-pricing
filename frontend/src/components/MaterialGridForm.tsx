import { useState } from "react";
import { Copy, Plus, Save, Trash2 } from "lucide-react";
import {
  api,
  labelTahun,
  pakaiKolomPembelian,
  pakaiSpesifikasi,
  DASAR_PENETAPAN,
  JENIS_DOKUMEN_BELI,
  type Currency,
  type JenisSumberDaya,
  type MaterialItemInput,
  type PastePreview,
} from "../lib/api";
import { bacaAngkaUang } from "../lib/tsv";
import NumberInput from "./NumberInput";

/** Jalan tengah antara menempel seluruh tabel Excel dan mengisi satu baris manual.
 *
 * Supplier, kapal, tahun, tanggal berlaku, mata uang, dan dokumen adalah sifat SATU
 * pembelian -- diisi sekali di atas, bukan diulang di tiap baris. Yang tersisa diketik per
 * barang cuma empat kolom yang memang berbeda-beda: nama, part number, satuan, harga.
 * Untuk quotation 25 baris seperti punya MAN, ini memangkas isian dari 225 sel jadi 100
 * plus 6 isian bersama.
 */

const CURRENCIES: Currency[] = ["IDR", "EUR", "USD"];
const CURRENT_YEAR = new Date().getFullYear();

type Baris = { nama: string; spesifikasi: string; satuan: string; harga_satuan: number };

const barisKosong: Baris = { nama: "", spesifikasi: "", satuan: "", harga_satuan: 0 };

type Props = {
  token: string;
  jenis: JenisSumberDaya;
  onSaved: () => void;
  onClose: () => void;
};

export default function MaterialGridForm({ token, jenis, onSaved, onClose }: Props) {
  const adaPembelian = pakaiKolomPembelian(jenis);
  const adaSpesifikasi = pakaiSpesifikasi(jenis);
  // Urutan kolom tabel di bawah. Dipakai juga waktu menempel banyak sel sekaligus,
  // supaya tempelan mendarat di kolom yang benar tanpa indeks dihitung tangan.
  const kolomGrid: (keyof Baris)[] = adaSpesifikasi
    ? ["nama", "spesifikasi", "satuan", "harga_satuan"]
    : ["nama", "satuan", "harga_satuan"];
  const [supplier, setSupplier] = useState("");
  const [kapal, setKapal] = useState("");
  const [tahun, setTahun] = useState(CURRENT_YEAR);
  const [berlakuDari, setBerlakuDari] = useState("");
  const [mataUang, setMataUang] = useState<Currency>("IDR");
  const [sumber, setSumber] = useState(
    pakaiKolomPembelian(jenis) ? "Quotation" : "SK Manajemen",
  );
  const [noDokumen, setNoDokumen] = useState("");

  const [baris, setBaris] = useState<Baris[]>([{ ...barisKosong }, { ...barisKosong }, { ...barisKosong }]);
  const [dampak, setDampak] = useState<PastePreview | null>(null);
  const [catatanTempel, setCatatanTempel] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const terisi = baris.filter((b) => b.nama.trim() && b.satuan.trim() && b.harga_satuan > 0);

  function ubah(i: number, patch: Partial<Baris>) {
    setBaris((prev) => prev.map((b, j) => (j === i ? { ...b, ...patch } : b)));
    setDampak(null);
  }

  function tambahBaris() {
    setBaris((prev) => [...prev, { ...barisKosong }]);
  }

  function duplikat(i: number) {
    setBaris((prev) => [...prev.slice(0, i + 1), { ...prev[i] }, ...prev.slice(i + 1)]);
    setDampak(null);
  }

  function hapus(i: number) {
    setBaris((prev) => (prev.length === 1 ? [{ ...barisKosong }] : prev.filter((_, j) => j !== i)));
    setDampak(null);
  }

  /** Tempel banyak baris sekaligus ke dalam grid.
   *
   * Mengisi satu per satu itu pekerjaan yang sebenarnya tidak perlu: sumber datanya
   * biasanya sudah berupa daftar, cuma berantakan. Menempel teks banyak baris ke satu
   * kotak secara bawaan cuma menghasilkan satu baris kacau, karena begitulah perilaku
   * <input>. Di sini tempelannya dipecah: tiap baris teks jadi satu baris grid, dan kalau
   * tempelannya memuat tab (mis. langsung dari Excel) tiap sel mendarat di kolom
   * berikutnya, dimulai dari kolom tempat kursornya berada.
   *
   * Baris ditambahkan otomatis kalau tempelannya lebih panjang daripada grid.
   */
  function tempelBanyak(e: React.ClipboardEvent, mulaiBaris: number, kolom: keyof Baris) {
    const teks = e.clipboardData.getData("text");
    if (!teks.includes("\n") && !teks.includes("\t")) return; // satu sel: biarkan normal
    e.preventDefault();

    const grid = teks
      .split(/\r?\n/)
      .map((b) => b.split("\t"))
      .filter((sel) => sel.some((v) => v.trim() !== ""));
    if (grid.length === 0) return;

    const mulaiKolom = kolomGrid.indexOf(kolom);
    let nTafsir = 0;
    let nGagal = 0;
    setBaris((prev) => {
      const next = [...prev];
      while (next.length < mulaiBaris + grid.length) next.push({ ...barisKosong });
      grid.forEach((sel, r) => {
        const target = { ...next[mulaiBaris + r] };
        sel.forEach((nilai, c) => {
          const k = kolomGrid[mulaiKolom + c];
          if (!k) return; // tempelan lebih lebar dari kolom yang ada -- sisanya diabaikan
          const bersih = nilai.trim();
          if (k === "harga_satuan") {
            const r = bacaAngkaUang(bersih);
            // Sel yang tidak terbaca tetap dijadikan 0, tidak dibiarkan memakai harga
            // lama baris itu. Nama dan spesifikasinya sudah tertimpa tempelan baru, jadi
            // harga lama yang bertahan berarti barang baru berpasangan dengan harga
            // barang lama -- salah yang tidak kelihatan. 0 salah yang kelihatan, dan
            // baris berharga 0 memang tidak ikut tersimpan.
            target.harga_satuan = r.nilai;
            if (bersih !== "" && !r.dikenali) nGagal++;
            else if (r.ditafsirkan) nTafsir++;
          }
          else if (k === "nama") target.nama = bersih;
          else if (k === "spesifikasi") target.spesifikasi = bersih;
          else if (k === "satuan") target.satuan = bersih;
        });
        next[mulaiBaris + r] = target;
      });
      return next;
    });
    setDampak(null);
    // Dua hal yang berbeda, jadi dikatakan terpisah: yang ditafsirkan tetap masuk dan cuma
    // perlu diperiksa, yang gagal dibaca tidak akan tersimpan sama sekali kalau dibiarkan.
    const catatan = [`${grid.length} baris ditempel.`];
    if (nTafsir > 0) {
      catatan.push(
        `${nTafsir} harga ditulis dengan format uang (mis. "Rp.150.000" atau "150.000") dan ` +
          `ditafsirkan — periksa kolom Harga sebelum menyimpan.`,
      );
    }
    if (nGagal > 0) {
      catatan.push(
        `${nGagal} harga tidak terbaca sebagai angka dan dikosongkan — baris berharga 0 ` +
          `tidak ikut tersimpan, jadi perbaiki dulu.`,
      );
    }
    setCatatanTempel(catatan.join(" "));
  }

  /** Isi nilai satu kolom ke semua baris di bawahnya. Satuan sering sama sekelompok
   * ("pcs" untuk semua spare part), jadi mengetiknya sekali sudah cukup. */
  function isiKeBawah(i: number, kolom: keyof Baris) {
    setBaris((prev) =>
      prev.map((b, j) => (j > i ? { ...b, [kolom]: prev[i][kolom] } : b)),
    );
    setDampak(null);
  }

  function keItems(): MaterialItemInput[] {
    return terisi.map((b) => ({
      nama: b.nama.trim(),
      spesifikasi: b.spesifikasi.trim(),
      satuan: b.satuan.trim(),
      harga_satuan: b.harga_satuan,
      mata_uang: mataUang,
      tahun_pembelian: tahun,
      supplier_nama: adaPembelian ? supplier.trim() : "",
      nama_kapal: adaPembelian ? kapal.trim() : "",
      berlaku_dari: berlakuDari || null,
      sumber,
      no_dokumen: noDokumen.trim(),
      catatan: "",
    }));
  }

  function validasi(): string {
    if (terisi.length === 0) return "Belum ada baris yang lengkap (nama, satuan, dan harga di atas 0).";
    if (tahun < 1990 || tahun > 2100) return `${labelTahun(jenis)} tidak valid.`;
    return "";
  }

  async function cek() {
    const pesan = validasi();
    if (pesan) return setError(pesan);
    setError("");
    setBusy(true);
    try {
      setDampak(await api.materialBulkPreview(token, keItems(), jenis));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal memeriksa dampak");
    } finally {
      setBusy(false);
    }
  }

  async function simpan() {
    const pesan = validasi();
    if (pesan) return setError(pesan);
    setError("");
    setBusy(true);
    try {
      const res = await api.materialBulkCreate(token, keItems(), jenis);
      onSaved();
      alert(
        res.dilewati > 0
          ? `Tersimpan ${res.saved} titik harga. ${res.dilewati} baris dilewati karena harganya ` +
            `sudah persis sama dengan yang tercatat.`
          : `Berhasil menyimpan ${res.saved} titik harga.`,
      );
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal menyimpan");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 p-4">
      <p className="mb-1 text-xs font-bold text-slate-700">Input Beberapa Baris</p>
      <p className="mb-3 text-xs text-slate-600">
        {adaPembelian
          ? "Isian di bawah ini berlaku untuk seluruh baris, karena satu pembelian biasanya satu supplier, satu kapal, dan satu dokumen. Di tabel bawah tinggal mengetik yang memang berbeda tiap barang."
          : "Isian di bawah ini berlaku untuk seluruh baris. Supplier dan kapal tidak ditanyakan -- tarif milik sendiri tidak dibeli dari siapa pun."}
      </p>

      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        {adaPembelian && (
          <>
            <Isian label="Supplier" value={supplier} onChange={setSupplier} />
            <Isian label="Kapal" value={kapal} onChange={setKapal} />
          </>
        )}
        <label className="block text-xs font-medium text-slate-600">
          {labelTahun(jenis)} *
          <NumberInput
            integer
            className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm"
            value={tahun}
            onChange={setTahun}
          />
        </label>
        <label className="block text-xs font-medium text-slate-600">
          Berlaku Dari
          <input
            type="date"
            className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm"
            value={berlakuDari}
            onChange={(e) => setBerlakuDari(e.target.value)}
          />
        </label>
        <label className="block text-xs font-medium text-slate-600">
          Mata Uang
          <select
            className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm"
            value={mataUang}
            onChange={(e) => setMataUang(e.target.value as Currency)}
          >
            {CURRENCIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </label>
        <label className="block text-xs font-medium text-slate-600">
          {adaPembelian ? "Jenis Dokumen" : "Dasar Penetapan"}
          <select
            className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm"
            value={sumber}
            onChange={(e) => setSumber(e.target.value)}
          >
            {(adaPembelian ? JENIS_DOKUMEN_BELI : DASAR_PENETAPAN).map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
        <div className="md:col-span-2">
          <Isian
            label={adaPembelian ? "Nomor Dokumen" : "Nomor SK / Memo"}
            value={noDokumen}
            onChange={setNoDokumen}
            placeholder={adaPembelian ? "mis. 2410-1547/MAN-SQ" : "mis. SK-012/DR/2026"}
          />
        </div>
      </div>

      <p className="mb-2 text-xs text-slate-500">
        Punya daftarnya di tempat lain? Salin satu kolom sekaligus, lalu tempel di kotak
        <strong> Nama</strong> baris pertama — tiap baris teks jadi satu baris sendiri, dan
        barisnya ditambah otomatis kalau kurang. Kalau menyalin beberapa kolom dari Excel,
        kolom-kolomnya ikut mendarat di tempatnya. Tanda <strong>↓</strong> di kolom Satuan
        mengisi nilai itu ke semua baris di bawahnya.
      </p>

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full text-left text-xs">
          <thead className="bg-slate-50 uppercase text-slate-500">
            <tr>
              <th className="w-8 px-2 py-2">#</th>
              <th className="px-2 py-2">Nama *</th>
              {adaSpesifikasi && <th className="px-2 py-2">Part No. / Spesifikasi</th>}
              <th className="px-2 py-2">Satuan *</th>
              <th className="px-2 py-2 text-right">Harga *</th>
              <th className="px-2 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {baris.map((b, i) => (
              <tr key={i} className="border-t border-slate-100">
                <td className="px-2 py-1 text-slate-400">{i + 1}</td>
                <td className="px-2 py-1">
                  <input
                    aria-label={`Nama baris ${i + 1}`}
                    className="w-full rounded border border-slate-200 px-1.5 py-1"
                    value={b.nama}
                    onChange={(e) => ubah(i, { nama: e.target.value })}
                    onPaste={(e) => tempelBanyak(e, i, "nama")}
                  />
                </td>
                {adaSpesifikasi && (
                  <td className="px-2 py-1">
                    <input
                      aria-label={`Part number baris ${i + 1}`}
                      className="w-full rounded border border-slate-200 px-1.5 py-1 font-mono"
                      value={b.spesifikasi}
                      onChange={(e) => ubah(i, { spesifikasi: e.target.value })}
                      onPaste={(e) => tempelBanyak(e, i, "spesifikasi")}
                    />
                  </td>
                )}
                <td className="px-2 py-1">
                  <div className="flex items-center gap-1">
                    <input
                      aria-label={`Satuan baris ${i + 1}`}
                      className="w-full rounded border border-slate-200 px-1.5 py-1"
                      value={b.satuan}
                      onChange={(e) => ubah(i, { satuan: e.target.value })}
                      onPaste={(e) => tempelBanyak(e, i, "satuan")}
                    />
                    {i < baris.length - 1 && b.satuan.trim() !== "" && (
                      <button
                        type="button"
                        title="Isi satuan ini ke semua baris di bawah"
                        onClick={() => isiKeBawah(i, "satuan")}
                        className="shrink-0 rounded px-1 text-slate-400 hover:text-slate-800"
                      >
                        ↓
                      </button>
                    )}
                  </div>
                </td>
                <td className="px-2 py-1">
                  <NumberInput
                    ariaLabel={`Harga baris ${i + 1}`}
                    className="w-full rounded border border-slate-200 px-1.5 py-1 text-right"
                    value={b.harga_satuan}
                    onChange={(n) => ubah(i, { harga_satuan: n })}
                  />
                </td>
                <td className="whitespace-nowrap px-2 py-1">
                  <button
                    type="button"
                    title="Duplikat baris ini"
                    onClick={() => duplikat(i)}
                    className="rounded p-1 text-slate-400 hover:text-slate-800"
                  >
                    <Copy size={13} />
                  </button>
                  <button
                    type="button"
                    title="Hapus baris ini"
                    onClick={() => hapus(i)}
                    className="rounded p-1 text-slate-400 hover:text-red-700"
                  >
                    <Trash2 size={13} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button type="button" onClick={tambahBaris} className="btn btn-secondary btn-sm">
          <Plus size={13} />
          Tambah Baris
        </button>
        <button type="button" disabled={busy} onClick={cek} className="btn btn-secondary btn-sm">
          Cek Dampak
        </button>
        <span className="text-xs text-slate-500">
          {terisi.length} dari {baris.length} baris siap disimpan
        </span>
      </div>

      {dampak && (
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          <span className="rounded bg-emerald-100 px-2 py-1 font-medium text-emerald-800">
            {dampak.ringkas.material_baru} material baru
          </span>
          <span className="rounded bg-blue-100 px-2 py-1 font-medium text-blue-800">
            {dampak.ringkas.harga_baru} titik harga baru
          </span>
          <span className="rounded bg-slate-100 px-2 py-1 font-medium text-slate-700">
            {dampak.ringkas.dilewati} dilewati
          </span>
          {dampak.baris
            .filter((b) => b.peringatan)
            .map((b, i) => (
              <p key={i} className="w-full text-amber-800">
                <span className="font-medium">{b.nama}</span>: {b.peringatan}
              </p>
            ))}
        </div>
      )}

      {catatanTempel && (
        <p className="mt-2 text-xs text-slate-600">{catatanTempel}</p>
      )}

      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

      <div className="mt-3 flex gap-2">
        <button type="button" disabled={busy} onClick={simpan} className="btn btn-primary btn-md">
          <Save size={13} />
          {busy ? "Menyimpan..." : `Simpan ${terisi.length} Baris`}
        </button>
        <button type="button" onClick={onClose} className="btn btn-secondary btn-md">
          Tutup
        </button>
      </div>
    </div>
  );
}

function Isian({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="block text-xs font-medium text-slate-600">
      {label}
      <input
        className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}
