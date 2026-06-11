"use client";

import { authApi } from "@/api/auth";
import { AUTH_LOGOUT_EVENT } from "@/lib/http";
import type { User } from "@/types";
import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  // `loading` stays true until we've *validated* the stored token against the
  // server. We never render the app as "logged in" off a cached blob — that was
  // the old bug: a stale `user` in localStorage outlived its 60-min JWT, so the
  // dashboard showed a logged-in shell whose every request silently 401'd.
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  // On boot, ask the server who we are. The JWT is the only real credential;
  // localStorage can't tell us if it's expired, so /auth/me is the source of
  // truth. 200 → set the real user; any failure (401 = expired/invalid) → clear
  // the session. Either way we stop loading so the UI can resolve.
  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      setLoading(false);
      return;
    }
    authApi
      .me()
      .then((me) => {
        setUser(me);
        localStorage.setItem("user", JSON.stringify(me));
      })
      .catch(() => {
        localStorage.removeItem("access_token");
        localStorage.removeItem("user");
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const token = await authApi.login(email, password);
    localStorage.setItem("access_token", token.access_token);
    // Fetch the *real* user with the fresh token instead of fabricating one.
    const me = await authApi.me();
    localStorage.setItem("user", JSON.stringify(me));
    setUser(me);
    router.push("/dashboard");
  }, [router]);

  const register = useCallback(async (email: string, password: string) => {
    const newUser = await authApi.register(email, password);
    const token = await authApi.login(email, password);
    localStorage.setItem("access_token", token.access_token);
    localStorage.setItem("user", JSON.stringify(newUser));
    setUser(newUser);
    router.push("/dashboard");
  }, [router]);

  const logout = useCallback(() => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("user");
    setUser(null);
    router.push("/login");
  }, [router]);

  // When any API call hits a 401 with a token attached (session expired while
  // the app was open), http.ts fires AUTH_LOGOUT_EVENT. We catch it here and run
  // the same teardown as a manual logout, so a dead token bounces the user to
  // /login instead of leaving them on a broken page.
  useEffect(() => {
    const onLogout = () => logout();
    window.addEventListener(AUTH_LOGOUT_EVENT, onLogout);
    return () => window.removeEventListener(AUTH_LOGOUT_EVENT, onLogout);
  }, [logout]);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
