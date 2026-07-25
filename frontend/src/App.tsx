import { Navigate, Route, Routes } from "react-router-dom";
import { useEffect, useState } from "react";
import { getStoredAuth, setStoredAuth, touchSession, type AuthUser } from "./lib/api";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";

export default function App() {
  const [auth, setAuth] = useState<AuthUser | null>(() => getStoredAuth());

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

  function onLogin(user: AuthUser) {
    setStoredAuth(user);
    setAuth(user);
  }

  function onLogout() {
    setStoredAuth(null);
    setAuth(null);
  }

  if (!auth) {
    return <LoginPage onLogin={onLogin} />;
  }

  return (
    <Routes>
      <Route path="/" element={<DashboardPage auth={auth} onLogout={onLogout} />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
