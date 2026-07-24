import { useState } from "react";
import { api, type AuthUser } from "../lib/api";

type Props = { onLogin: (user: AuthUser) => void };

export default function LoginPage({ onLogin }: Props) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api.login(username, password);
      onLogin({
        token: res.access_token,
        username: res.username,
        role: res.role,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login gagal");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 px-4">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-10 shadow-xl">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-900">DUKUH RAYA</h1>
          <p className="mt-1 text-sm font-medium text-slate-500">Shipyard Maintenance System</p>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Username</label>
            <input
              className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none ring-blue-500 focus:ring-2"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Password</label>
            <input
              type="password"
              className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none ring-blue-500 focus:ring-2"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-slate-900 py-3 text-sm font-bold text-white hover:bg-slate-800 disabled:opacity-60"
          >
            {loading ? "Memproses..." : "Masuk ke Dashboard"}
          </button>
        </form>
      </div>
    </div>
  );
}
