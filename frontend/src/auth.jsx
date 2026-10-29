import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, setUnauthorizedHandler } from "./api.js";

const Ctx = createContext(null);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }) {
  const [state, setState] = useState({ status: "loading", me: null, bootError: null });

  const refresh = useCallback(async () => {
    try {
      const me = await api.me();
      setState({ status: "authed", me, bootError: null });
    } catch (e) {
      setState({ status: "anon", me: null, bootError: e.status === 401 ? null : e });
    }
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => setState({ status: "anon", me: null, bootError: null }));
    refresh();
  }, [refresh]);

  const value = useMemo(() => ({
    ...state,
    refresh,
    async login(loginId, password) { await api.login(loginId, password); await refresh(); },
    async logout() {
      try { await api.logout(); } finally { setState({ status: "anon", me: null, bootError: null }); }
    },
  }), [state, refresh]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
