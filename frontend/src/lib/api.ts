const API_BASE = import.meta.env.VITE_API_URL ?? "/api";
const SESSION_TIMEOUT_MS = 10 * 60 * 1000; // 10 menit

export type AuthUser = { username: string; role: string; token: string };

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

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail));
  }
  return res.json() as Promise<T>;
}

export const api = {
  login(username: string, password: string) {
    return request<{ access_token: string; username: string; role: string }>(
      "/auth/login",
      { method: "POST", body: JSON.stringify({ username, password }) },
    );
  },
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
  filters(token: string) {
    return request<FilterOptions>("/catalog/filters", {}, token);
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
    return request<{ saved: number }>(
      "/catalog/import/docking-commit",
      { method: "POST", body: JSON.stringify(body) },
      token,
    );
  },
  listUsers(token: string) {
    return request<UserOut[]>("/users", {}, token);
  },
  createUser(token: string, body: { username: string; password: string; role: "user" | "admin" }) {
    return request<UserOut>("/users", { method: "POST", body: JSON.stringify(body) }, token);
  },
  deleteUser(token: string, username: string) {
    return request<{ ok: boolean }>(`/users/${encodeURIComponent(username)}`, { method: "DELETE" }, token);
  },
  changePassword(token: string, username: string, new_password: string) {
    return request<{ ok: boolean }>(
      "/users/password",
      { method: "POST", body: JSON.stringify({ username, new_password }) },
      token,
    );
  },
};

export type UserOut = {
  id: number;
  username: string;
  role: string;
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

export function formatRp(n: number) {
  return new Intl.NumberFormat("id-ID", {
    style: "currency",
    currency: "IDR",
    maximumFractionDigits: 0,
  }).format(n);
}
