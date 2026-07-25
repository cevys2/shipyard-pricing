import { useEffect, useState } from "react";
import { KeyRound, Plus, Trash2, UserPlus } from "lucide-react";
import { api, type AuthUser, type UserOut } from "../lib/api";

type Props = { auth: AuthUser };

export default function UsersPanel({ auth }: Props) {
  const [users, setUsers] = useState<UserOut[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [newUser, setNewUser] = useState({ username: "", password: "", role: "user" as "user" | "admin" });
  const [busy, setBusy] = useState(false);
  const [resetTarget, setResetTarget] = useState<string | null>(null);
  const [resetPassword, setResetPassword] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const list = await api.listUsers(auth.token);
      setUsers(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal memuat daftar user");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function createUser() {
    if (!newUser.username.trim() || newUser.password.length < 4) {
      setError("Username wajib diisi dan password minimal 4 karakter");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api.createUser(auth.token, newUser);
      setNewUser({ username: "", password: "", role: "user" });
      setShowAdd(false);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal membuat user");
    } finally {
      setBusy(false);
    }
  }

  async function deleteUser(username: string) {
    if (!confirm(`Hapus akun "${username}"? Tindakan ini tidak bisa dibatalkan.`)) return;
    setBusy(true);
    setError("");
    try {
      await api.deleteUser(auth.token, username);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal menghapus user");
    } finally {
      setBusy(false);
    }
  }

  async function submitReset() {
    if (!resetTarget || resetPassword.length < 4) {
      setError("Password baru minimal 4 karakter");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api.changePassword(auth.token, resetTarget, resetPassword);
      setResetTarget(null);
      setResetPassword("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal reset password");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-3xl rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h3 className="font-display text-lg font-bold text-slate-900">Kelola Akses</h3>
          <p className="mt-1 text-sm text-slate-500">Tambah, hapus, atau reset password akun yang bisa login.</p>
        </div>
        <button type="button" onClick={() => setShowAdd((s) => !s)} className="btn btn-primary btn-md">
          <UserPlus size={15} />
          Tambah User
        </button>
      </div>

      {error && <p className="mb-4 text-sm font-medium text-red-600">{error}</p>}

      {showAdd && (
        <div className="mb-6 rounded-xl border border-slate-200 bg-slate-50 p-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <label className="block text-xs font-medium text-slate-600">
              Username
              <input
                className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm"
                value={newUser.username}
                onChange={(e) => setNewUser((u) => ({ ...u, username: e.target.value }))}
              />
            </label>
            <label className="block text-xs font-medium text-slate-600">
              Password
              <input
                type="password"
                className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-2 text-sm"
                value={newUser.password}
                onChange={(e) => setNewUser((u) => ({ ...u, password: e.target.value }))}
              />
            </label>
            <label className="block text-xs font-medium text-slate-600">
              Role
              <select
                className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm"
                value={newUser.role}
                onChange={(e) => setNewUser((u) => ({ ...u, role: e.target.value as "user" | "admin" }))}
              >
                <option value="user">User</option>
                <option value="admin">Admin</option>
              </select>
            </label>
          </div>
          <div className="mt-3 flex gap-2">
            <button type="button" disabled={busy} onClick={createUser} className="btn btn-primary btn-sm">
              <Plus size={14} />
              Simpan User
            </button>
            <button type="button" onClick={() => setShowAdd(false)} className="btn btn-secondary btn-sm">
              Batal
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <p className="py-8 text-center text-sm text-slate-500">Memuat...</p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">Username</th>
                <th className="px-4 py-3">Role</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {(users ?? []).map((u) => (
                <tr key={u.id} className="border-t border-slate-100">
                  <td className="px-4 py-3 font-medium text-slate-800">{u.username}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                        u.role === "admin" ? "bg-amber-100 text-amber-800" : "bg-slate-100 text-slate-600"
                      }`}
                    >
                      {u.role}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      onClick={() => {
                        setResetTarget(u.username);
                        setResetPassword("");
                      }}
                      className="btn btn-ghost btn-sm"
                    >
                      <KeyRound size={13} />
                      Reset Password
                    </button>
                    {u.username !== "admin" && u.username !== auth.username && (
                      <button type="button" disabled={busy} onClick={() => deleteUser(u.username)} className="btn btn-danger btn-sm ml-2">
                        <Trash2 size={13} />
                        Hapus
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {resetTarget && (
        <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow-lg">
            <h4 className="font-display text-base font-bold text-slate-900">Reset password "{resetTarget}"</h4>
            <input
              type="password"
              placeholder="Password baru (min. 4 karakter)"
              className="mt-4 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              value={resetPassword}
              onChange={(e) => setResetPassword(e.target.value)}
              autoFocus
            />
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" onClick={() => setResetTarget(null)} className="btn btn-secondary btn-sm">
                Batal
              </button>
              <button type="button" disabled={busy} onClick={submitReset} className="btn btn-primary btn-sm">
                Simpan
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
