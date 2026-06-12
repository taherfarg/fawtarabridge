import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, getTokens, setOnUnauthorized, setTokens } from "../api/client";
import type { TenantOut, TokenPair, UserOut } from "../api/types";

interface SignupCompany {
  legal_name_ar: string;
  legal_name_en: string;
  trn: string;
  emirate?: string;
  revenue_band: string;
}

interface AuthState {
  user: UserOut | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (data: {
    email: string;
    password: string;
    full_name: string;
    phone: string;
    company: SignupCompany;
  }) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [ready, setReady] = useState(false);

  const refreshUser = useCallback(async () => {
    setUser(await api.get<UserOut>("/users/me"));
  }, []);

  useEffect(() => {
    setOnUnauthorized(() => setUser(null));
    if (!getTokens()) {
      setReady(true);
      return;
    }
    refreshUser()
      .catch(() => setTokens(null))
      .finally(() => setReady(true));
  }, [refreshUser]);

  const login = useCallback(async (email: string, password: string) => {
    const body = await api.post<{ tokens: TokenPair; user: UserOut }>("/auth/login", {
      email,
      password,
    });
    setTokens(body.tokens);
    setUser(body.user);
  }, []);

  const signup = useCallback(async (data: Parameters<AuthState["signup"]>[0]) => {
    const body = await api.post<{ tokens: TokenPair; user: UserOut; tenant: TenantOut }>(
      "/auth/signup",
      data,
    );
    setTokens(body.tokens);
    setUser(body.user);
  }, []);

  const logout = useCallback(() => {
    const tokens = getTokens();
    if (tokens) void api.post("/auth/logout", { refresh_token: tokens.refresh_token }).catch(() => {});
    setTokens(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, ready, login, signup, logout, refreshUser }),
    [user, ready, login, signup, logout, refreshUser],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
