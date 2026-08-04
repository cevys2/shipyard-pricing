const API_BASE = import.meta.env.VITE_API_URL ?? "/api";
export const PORTAL_URL = import.meta.env.VITE_PORTAL_URL ?? "http://localhost:5174";
const SESSION_TIMEOUT_MS = 10 * 60 * 1000; // 10 menit

export type AuthUser = { username: string; role: string; token: string };

/** Baca klaim `sub`/`role` dari JWT yang diterbitkan Portal, tanpa verifikasi
 * signature (itu tugas backend di setiap request) - cuma untuk tampilan. */
export function decodeAuthFromToken(token: string): AuthUser | null {
  try {
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    if (!payload.sub) return null;
    return { token, username: payload.sub, role: payload.role ?? "user" };
  } catch {
    return null;
  }
}

export function getStoredAuth(): AuthUser | null {
  const raw = localStorage.getItem("dr_auth");
  const lastSeenRaw = localStorage.getItem("dr_auth_last_seen");
  if (!raw) return null;
  const lastSeen = lastSeenRaw ? Number(lastSeenRaw) : 0;
  if (!lastSeen || Date.now() - lastSeen > SESSION_TIMEOUT_MS) {
    localStorage.removeItem("dr_auth");
    localStorage.removeItem("dr_auth_last_seen");
    return null;
  }
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function setStoredAuth(user: AuthUser | null) {
  if (!user) {
    localStorage.removeItem("dr_auth");
    localStorage.removeItem("dr_auth_last_seen");
  } else {
    localStorage.setItem("dr_auth", JSON.stringify(user));
    localStorage.setItem("dr_auth_last_seen", String(Date.now()));
  }
}

/** Panggil berkala selama app aktif supaya sesi tidak dianggap "ditinggal lama" (lihat SESSION_TIMEOUT_MS). */
export function touchSession() {
  if (localStorage.getItem("dr_auth")) {
    localStorage.setItem("dr_auth_last_seen", String(Date.now()));
  }
}

/** Pesan untuk permintaan yang kita hentikan sendiri karena kelamaan.
 *
 * Yang bikin kegagalan impor 31 Juli 2026 membingungkan bukan lamanya, melainkan
 * pengguna tidak punya cara tahu apakah datanya sudah masuk atau belum -- lalu mencoba
 * ulang secara buta, yang justru memperparah keadaan. Jadi pesannya harus menyebutkan
 * akibatnya, bukan cuma "gagal".
 */
const PESAN_TIMEOUT =
  "Permintaan dihentikan karena terlalu lama. Penyimpanan belum tentu gagal — " +
  "muat ulang halaman dan cek tabelnya dulu sebelum mencoba menyimpan lagi.";

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
  timeoutMs?: number,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);

  // Tanpa batas waktu, permintaan yang menggantung tidak pernah selesai dan tombolnya
  // terkunci selamanya. Batasnya sengaja longgar: yang dikejar bukan memutus cepat,
  // melainkan memastikan ada akhir yang bisa dijelaskan.
  const ac = timeoutMs ? new AbortController() : undefined;
  const timer = ac ? setTimeout(() => ac.abort(), timeoutMs) : undefined;

  try {
    const res = await fetch(`${API_BASE}${path}`, { ...options, headers, signal: ac?.signal });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
    }
    return (await res.json()) as T;
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw new Error(PESAN_TIMEOUT);
    throw e;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

export const api = {
  catalog(token: string, params: Record<string, string | undefined>) {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v && v !== "Semua") q.set(k, v);
    });
    const qs = q.toString();
    return request<CatalogRow[]>(`/catalog${qs ? `?${qs}` : ""}`, {}, token);
  },
  stats(token: string, params: Record<string, string | undefined>) {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v && v !== "Semua") q.set(k, v);
    });
    const qs = q.toString();
    return request<CatalogStats>(`/catalog/stats${qs ? `?${qs}` : ""}`, {}, token);
  },
  filters(token: string, params: Record<string, string | undefined> = {}) {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v && v !== "Semua") q.set(k, v);
    });
    const qs = q.toString();
    return request<FilterOptions>(`/catalog/filters${qs ? `?${qs}` : ""}`, {}, token);
  },
  importFile(token: string, file: File, dryRun = false) {
    const fd = new FormData();
    fd.append("file", file);
    return request<{ saved?: number; valid?: boolean; rows?: number; warnings?: string[] }>(
      `/catalog/import?dry_run=${dryRun}`,
      { method: "POST", body: fd },
      token,
    );
  },
  addRow(token: string, header: CatalogHeader, item: CatalogItemInput) {
    return request<{ saved: number }>(
      "/catalog/bulk",
      { method: "POST", body: JSON.stringify({ ...header, items: [item] }) },
      token,
    );
  },
  bulkCreateMany(token: string, header: CatalogHeader, items: CatalogItemInput[]) {
    return request<{ saved: number }>(
      "/catalog/bulk",
      { method: "POST", body: JSON.stringify({ ...header, items }) },
      token,
    );
  },
  patchCatalog(token: string, body: { updates?: { id: string; data: CatalogRowInput }[]; delete_ids?: string[] }) {
    return request<{ deleted: number; updated: number }>(
      "/catalog",
      { method: "PATCH", body: JSON.stringify(body) },
      token,
    );
  },
  dockingPreview(token: string, file: File) {
    const fd = new FormData();
    fd.append("file", file);
    return request<DockingImportPreview>(
      "/catalog/import/docking-preview",
      { method: "POST", body: fd },
      token,
    );
  },
  dockingCommit(token: string, body: DockingImportCommit) {
    // Satu-satunya panggilan yang diberi batas waktu: ini yang menulis ratusan baris
    // sekaligus, dan satu-satunya yang pernah menggantung sampai proxy menyerah.
    return request<{ saved: number }>(
      "/catalog/import/docking-commit",
      { method: "POST", body: JSON.stringify(body) },
      token,
      5 * 60 * 1000,
    );
  },
  material(token: string, params: Record<string, string | undefined> = {}) {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v && v !== "Semua") q.set(k, v);
    });
    const qs = q.toString();
    return request<MaterialRow[]>(`/material${qs ? `?${qs}` : ""}`, {}, token);
  },
  materialStats(token: string, params: Record<string, string | undefined> = {}) {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v && v !== "Semua") q.set(k, v);
    });
    const qs = q.toString();
    return request<MaterialStats>(`/material/stats${qs ? `?${qs}` : ""}`, {}, token);
  },
  materialFilters(token: string, params: Record<string, string | undefined> = {}) {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v && v !== "Semua") q.set(k, v);
    });
    const qs = q.toString();
    return request<MaterialFilterOptions>(`/material/filters${qs ? `?${qs}` : ""}`, {}, token);
  },
  materialBulkPreview(token: string, items: MaterialItemInput[], jenis: JenisSumberDaya = "BAHAN") {
    return request<PastePreview>(
      `/material/bulk/preview?jenis=${jenis}`,
      { method: "POST", body: JSON.stringify({ items }) },
      token,
    );
  },
  materialBulkCreate(token: string, items: MaterialItemInput[], jenis: JenisSumberDaya = "BAHAN") {
    return request<{ saved: number; titik_harga_baru: number; dilewati: number }>(
      `/material/bulk?jenis=${jenis}`,
      { method: "POST", body: JSON.stringify({ items }) },
      token,
    );
  },
  materialPatch(
    token: string,
    body: { updates?: { id: number; data: MaterialRowInput }[]; delete_ids?: number[] },
  ) {
    return request<{ deleted: number; updated: number; titik_harga_baru: number }>(
      "/material",
      { method: "PATCH", body: JSON.stringify(body) },
      token,
    );
  },
  priceHistory(token: string, sumberDayaId: number) {
    return request<PriceHistoryRow[]>(`/material/${sumberDayaId}/harga`, {}, token);
  },
  addPrice(token: string, sumberDayaId: number, body: PriceInput) {
    return request<{ id: number }>(
      `/material/${sumberDayaId}/harga`,
      { method: "POST", body: JSON.stringify(body) },
      token,
    );
  },
  deletePrice(token: string, hargaId: number) {
    return request<{ deleted: number }>(`/material/harga/${hargaId}`, { method: "DELETE" }, token);
  },
  ahspList(token: string) {
    return request<AhspRow[]>("/ahsp", {}, token);
  },
  ahspRingkas(token: string) {
    return request<AhspRingkas>("/ahsp/ringkas", {}, token);
  },
  ahspCreate(token: string, body: AhspCreateInput) {
    return request<{ id: number }>("/ahsp", { method: "POST", body: JSON.stringify(body) }, token);
  },
  ahspDelete(token: string, id: number) {
    return request<{ deleted: number }>(`/ahsp/${id}`, { method: "DELETE" }, token);
  },
  ahspKomponen(token: string, id: number) {
    return request<AhspKomponenRow[]>(`/ahsp/${id}/komponen`, {}, token);
  },
  ahspSimpanKomponen(token: string, id: number, items: AhspKomponenInput[]) {
    return request<{ komponen: number }>(
      `/ahsp/${id}/komponen`,
      { method: "PUT", body: JSON.stringify(items) },
      token,
    );
  },
  ahspHitung(token: string, id: number) {
    return request<AhspHitung>(`/ahsp/${id}/hitung`, {}, token);
  },
  trenJasa(token: string, params: { kategori?: string; min_sampel?: number } = {}) {
    const q = new URLSearchParams();
    if (params.kategori && params.kategori !== "Semua") q.set("kategori", params.kategori);
    if (params.min_sampel != null) q.set("min_sampel", String(params.min_sampel));
    const qs = q.toString();
    return request<TrenJasa>(`/analitik/tren-jasa${qs ? `?${qs}` : ""}`, {}, token);
  },
  trenJasaKategori(token: string) {
    return request<string[]>("/analitik/tren-jasa/kategori", {}, token);
  },
  trenMaterial(token: string) {
    return request<TrenMaterial>("/analitik/tren-material", {}, token);
  },
  auditLog(token: string, params: { entitas?: string; limit?: number } = {}) {
    const q = new URLSearchParams();
    if (params.entitas && params.entitas !== "Semua") q.set("entitas", params.entitas);
    if (params.limit) q.set("limit", String(params.limit));
    const qs = q.toString();
    return request<AuditRow[]>(`/analitik/log${qs ? `?${qs}` : ""}`, {}, token);
  },
};

export type PriceInput = {
  harga_satuan: number;
  mata_uang: Currency;
  tahun_pembelian: number;
  supplier_nama: string;
  nama_kapal: string;
  berlaku_dari: string | null;
  sumber: string;
  no_dokumen: string;
  catatan: string;
};

export type PriceHistoryRow = {
  id: number;
  harga_satuan: number;
  mata_uang: string;
  berlaku_dari: string;
  tahun_pembelian: number;
  nama_kapal: string | null;
  supplier_nama: string | null;
  sumber: string | null;
  no_dokumen: string | null;
  catatan: string | null;
  dibuat_pada: string;
};

export type TrenJasaPoint = {
  kategori: string;
  tahun: string;
  n_baris: number;
  n_kapal: number;
  median: number;
  minimum: number;
  maksimum: number;
  /** Kapal yang menyusun median ini. Median tanpa ini tidak bisa ditindaklanjuti:
   * tidak jelas angkanya dari kapal besar, kapal kecil, atau campuran. */
  kapal: string[] | null;
};

export type TrenJasa = {
  seri: TrenJasaPoint[];
  per_tahun: { tahun: string; n_baris: number; n_kapal: number }[];
  cakupan: { total_baris: number; total_kategori: number; total_tahun: number };
};

export type TrenMaterialKandidat = {
  id: number;
  nama: string;
  spesifikasi: string | null;
  satuan: string;
  n_harga: number;
  dari: string;
  sampai: string;
  n_mata_uang: number;
  mata_uang: string;
  harga_awal: number;
  harga_akhir: number;
  /** null kalau mata uangnya campur -- persentase lintas mata uang tidak bermakna. */
  perubahan_persen: number | null;
};

export type TrenMaterialTitik = {
  sumber_daya_id: number;
  berlaku_dari: string;
  harga_satuan: number;
  mata_uang: string;
  nama_kapal: string | null;
  supplier_nama: string | null;
};

export type TrenMaterial = {
  ringkas: { total_material: number; siap_tren: number; total_titik_harga: number };
  kandidat: TrenMaterialKandidat[];
  titik: TrenMaterialTitik[];
};

export type PastePreviewRow = {
  nama: string;
  spesifikasi: string;
  satuan: string;
  harga_satuan: number;
  mata_uang: string;
  status: "material_baru" | "harga_baru" | "dilewati";
  harga_lama: number | null;
  perubahan_persen: number | null;
  peringatan: string | null;
};

export type PastePreview = {
  ringkas: { material_baru: number; harga_baru: number; dilewati: number; peringatan: number };
  baris: PastePreviewRow[];
};

export type AuditRow = {
  id: number;
  aktor: string;
  aksi: string;
  entitas: string;
  jumlah: number;
  detail: Record<string, unknown> | null;
  dibuat_pada: string;
};

export type CatalogHeader = {
  nama_perusahaan: string;
  nama_kapal: string;
  tahun: string;
  tipe_perjanjian: "Induk" | "Addendum";
};

export type CatalogItemInput = {
  kategori_pekerjaan: string;
  uraian_pekerjaan: string;
  volume_satuan: string;
  harga_satuan: number;
};

export type CatalogRowInput = CatalogHeader & CatalogItemInput;

export type DockingParsedItem = {
  row: number;
  kategori: string | null;
  uraian: string;
  volume_satuan: string;
  keterangan: string;
  harga: number;
};

export type DockingImportPreview = {
  sheet_name: string;
  detected_nama_kapal: string;
  detected_nama_perusahaan: string;
  detected_tahun: string;
  induk: DockingParsedItem[];
  addendum: DockingParsedItem[];
  warnings: string[];
};

export type DockingImportCommit = {
  nama_perusahaan: string;
  nama_kapal: string;
  tahun: string;
  induk_items: CatalogItemInput[];
  addendum_items: CatalogItemInput[];
};

export type CatalogRow = {
  id: string;
  nama_perusahaan: string;
  nama_kapal: string;
  tipe_perjanjian: string;
  tahun: string;
  kategori_pekerjaan: string;
  uraian_pekerjaan: string;
  volume_satuan: string;
  harga_satuan: number;
};

export type CatalogStats = {
  total_item: number;
  total_klien: number;
  total_kapal: number;
  total_tahun: number;
};

export type FilterOptions = {
  perusahaan: string[];
  kapal: string[];
  kategori: string[];
  tahun: string[];
  tipe: string[];
};

export type Currency = "IDR" | "EUR" | "USD";

/** Harus sama persis dengan CHECK constraint sumber_daya.jenis di backend. */
export type JenisSumberDaya = "BAHAN" | "UPAH" | "ALAT" | "KONSUMABEL";

export const JENIS_SUMBER_DAYA: { nilai: JenisSumberDaya; label: string }[] = [
  { nilai: "BAHAN", label: "Bahan" },
  { nilai: "UPAH", label: "Upah" },
  { nilai: "ALAT", label: "Alat" },
  { nilai: "KONSUMABEL", label: "Konsumabel" },
];

/** Supplier dan kapal itu sifat PEMBELIAN. Upah dan alat milik sendiri tidak dibeli dari
 * siapa pun -- angkanya tarif internal -- jadi dua kolom itu akan selalu kosong dan lebih
 * baik tidak ditampilkan sama sekali. Konsumabel (oksigen, elektroda) tetap dibeli. */
export function pakaiKolomPembelian(jenis: JenisSumberDaya) {
  return jenis === "BAHAN" || jenis === "KONSUMABEL";
}

export type MaterialItemInput = {
  nama: string;
  spesifikasi: string;
  satuan: string;
  harga_satuan: number;
  mata_uang: Currency;
  tahun_pembelian: number;
  supplier_nama: string;
  nama_kapal: string;
  berlaku_dari: string | null;
  sumber: string;
  no_dokumen: string;
  catatan: string;
};

export type MaterialRowInput = MaterialItemInput;

export type MaterialRow = {
  id: number;
  nama: string;
  spesifikasi: string;
  satuan: string;
  harga_satuan: number | null;
  mata_uang: string | null;
  tahun_pembelian: number | null;
  supplier_nama: string | null;
  nama_kapal: string | null;
  berlaku_dari: string | null;
};

export type MaterialStats = {
  total_material: number;
  total_supplier: number;
  total_kapal: number;
  update_terakhir: string | null;
};

export type MaterialFilterOptions = {
  supplier: string[];
  satuan: string[];
  kapal: string[];
  tahun: string[];
};

/* ---------- AHSP / Struktur Biaya ----------
 *
 * Semua angka uang dan pengali datang sebagai STRING, bukan number. Pydantic
 * menserialisasi Decimal jadi string ("12000.50"), dan itu memang yang diinginkan:
 * koefisien seperti 0,07 tidak lewat float sama sekali. Konversi ke number cuma
 * dilakukan sesaat sebelum ditampilkan. */

export type AhspRow = {
  id: number;
  uraian: string;
  satuan: string;
  jenis_jual: "JASA" | "MATERIAL";
  kategori: string | null;
  catatan: string | null;
  aktif: boolean;
  n_komponen: number;
  n_tanpa_harga: number;
  lengkap: boolean;
  subtotal_total: string | null;
};

export type AhspKomponenRow = {
  id: number;
  sumber_daya_id: number;
  nama: string;
  spesifikasi: string;
  satuan: string;
  kelompok: JenisSumberDaya;
  qty: string;
  shift: string;
  jml_hari: string;
  urutan: number;
  catatan: string;
  /** null = belum ada baris harga sama sekali. Bukan nol. */
  harga_satuan: string | null;
  mata_uang: string | null;
  jumlah: string | null;
};

export type AhspHitung = {
  subtotal: Record<string, string>;
  subtotal_total: string;
  /** null selama `lengkap` false -- backend menahan harga jual, bukan menampilkan angka separuh. */
  harga_jual: string | null;
  rumus_terpasang: boolean;
  lengkap: boolean;
  alasan: string[];
};

export type AhspRingkas = { total: number; lengkap: number; komponen_tanpa_harga: number };

export type AhspCreateInput = {
  uraian: string;
  satuan: string;
  jenis_jual: "JASA" | "MATERIAL";
  kategori: string;
  catatan: string;
};

export type AhspKomponenInput = {
  sumber_daya_id: number;
  kelompok: JenisSumberDaya;
  /** Dikirim sebagai string supaya 0,07 sampai ke Decimal tanpa mampir ke float. */
  qty: string;
  shift: string;
  jml_hari: string;
  urutan: number;
  catatan: string;
};

export function formatRp(n: number) {
  return new Intl.NumberFormat("id-ID", {
    style: "currency",
    currency: "IDR",
    maximumFractionDigits: 0,
  }).format(n);
}

/** Angka IDR dan EUR/USD TIDAK dikonversi satu sama lain - ini cuma format tampilan
 * sesuai mata uang aslinya masing-masing baris. */
export function formatMoney(n: number, currency: string) {
  return new Intl.NumberFormat("id-ID", {
    style: "currency",
    currency: currency || "IDR",
    maximumFractionDigits: 2,
  }).format(n);
}
