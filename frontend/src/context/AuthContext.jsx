import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

const AuthContext = createContext(null);

const TOKEN_KEY = "fairlens_access_token";
const REFRESH_KEY = "fairlens_refresh_token";

export function AuthProvider({ apiBase, children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY));
  const [refreshToken, setRefreshToken] = useState(() => localStorage.getItem(REFRESH_KEY));
  const [user, setUser] = useState(null);
  const [authRequired, setAuthRequired] = useState(false);
  const [loading, setLoading] = useState(false);

  const base = useMemo(() => apiBase.replace(/\/+$/, ""), [apiBase]);

  // Persist tokens
  useEffect(() => {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  }, [token]);

  useEffect(() => {
    if (refreshToken) localStorage.setItem(REFRESH_KEY, refreshToken);
    else localStorage.removeItem(REFRESH_KEY);
  }, [refreshToken]);

  // Check if auth is required by probing /auth/me
  useEffect(() => {
    let active = true;
    async function probe() {
      try {
        const res = await fetch(`${base}/auth/me`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!active) return;
        if (res.status === 401) {
          setAuthRequired(true);
          setUser(null);
        } else if (res.ok) {
          const profile = await res.json();
          setUser(profile);
          setAuthRequired(false);
        }
      } catch {
        // Backend unreachable — don't enforce auth
        if (active) setAuthRequired(false);
      }
    }
    probe();
    return () => { active = false; };
  }, [base, token]);

  const login = useCallback(async (email, password) => {
    setLoading(true);
    try {
      const form = new URLSearchParams();
      form.append("username", email);
      form.append("password", password);
      const res = await fetch(`${base}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: form.toString(),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Login failed");
      }
      const data = await res.json();
      setToken(data.access_token);
      setRefreshToken(data.refresh_token);
      // Fetch profile
      const me = await fetch(`${base}/auth/me`, {
        headers: { Authorization: `Bearer ${data.access_token}` },
      });
      if (me.ok) setUser(await me.json());
      setAuthRequired(false);
      return data;
    } finally {
      setLoading(false);
    }
  }, [base]);

  const register = useCallback(async (email, password, fullName, orgName) => {
    setLoading(true);
    try {
      const res = await fetch(`${base}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, full_name: fullName, org_name: orgName }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Registration failed");
      }
      const data = await res.json();
      setToken(data.access_token);
      setRefreshToken(data.refresh_token);
      const me = await fetch(`${base}/auth/me`, {
        headers: { Authorization: `Bearer ${data.access_token}` },
      });
      if (me.ok) setUser(await me.json());
      setAuthRequired(false);
      return data;
    } finally {
      setLoading(false);
    }
  }, [base]);

  const logout = useCallback(() => {
    setToken(null);
    setRefreshToken(null);
    setUser(null);
    setAuthRequired(true);
  }, []);

  const value = useMemo(() => ({
    token,
    user,
    authRequired,
    loading,
    isAuthenticated: !!user,
    login,
    register,
    logout,
  }), [token, user, authRequired, loading, login, register, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
