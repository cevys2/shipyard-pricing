import { Navigate, Route, Routes } from "react-router-dom";
import { useEffect, useState } from "react";
import { PORTAL_URL, decodeAuthFromToken, getStoredAuth, setStoredAuth, touchSession, type AuthUser } from "./lib/api";
import DashboardPage from "./pages/DashboardPage";

function redirectToPortalLogin() {
  const here = window.location.href.split("#")[0];
  // Sengaja ke root, bukan /login: Portal tidak pakai router - dia menampilkan
  // form login di path apapun selama belum ada sesi. Root selalu ada, jadi ini
  // nggak bergantung pada SPA-fallback si static host.
  window.location.href = `${PORTAL_URL}/?redirect=${encodeURIComponent(here)}`;
}

/** Kalau baru saja di-bounce balik dari Portal, tokennya ada di URL fragment. */
function consumeTokenFromUrl(): AuthUser | null {
  const hash = window.location.hash;
  if (!hash.startsWith("#token=")) return null;
  const auth = decodeAuthFromToken(decodeURIComponent(hash.slice("#token=".length)));
  if (auth) history.replaceState(null, "", window.location.pathname + window.location.search);
  return auth;
}

export default function App() {
  const [auth, setAuth] = useState<AuthUser | null>(() => consumeTokenFromUrl() ?? getStoredAuth());

  useEffect(() => {
    if (auth) {
      setStoredAuth(auth);
      return;
    }
    redirectToPortalLogin();
  }, [auth]);

  useEffect(() => {
    if (!auth) return;
    touchSession();
    const interval = setInterval(touchSession, 30_000);
    const onVisible = () => {
      if (document.visibilityState === "visible") touchSession();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [auth]);

  function onLogout() {
    setStoredAuth(null);
    setAuth(null);
    window.location.href = PORTAL_URL;
  }

  if (!auth) {
    return null;
  }

  return (
    <Routes>
      <Route path="/" element={<DashboardPage auth={auth} onLogout={onLogout} />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
