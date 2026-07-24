const API_BASE = import.meta.env.VITE_API_URL ?? "/api";

export type AuthUser = { username: string; role: string; token: string };

export function getStoredAuth(): AuthUser | null {
  const raw = localStorage.getItem("dr_auth");
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function setStoredAuth(user: AuthUser | null) {
  if (!user) localStorage.removeItem("dr_auth");
  else localStorage.setItem("dr_auth", JSON.stringify(user));
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
