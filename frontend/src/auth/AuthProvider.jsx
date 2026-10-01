/**
 * Auth state for the whole app.
 *
 *   const { user, role, status, isStudent, unread, login, logout, refresh, patchUser } = useAuth();
 *
 * status: "loading" (first session check) | "authenticated" | "unauthenticated" | "error" (server unreachable)
 *
 * The session object comes from GET /api/auth/session and is polled every 30s, which keeps the unread
 * notification / message counters fresh and notices an expired session. A 401 from any request clears
 * the auth state (see setUnauthorizedHandler) and the route guards send the user to /login?next=...
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { fetchSession, setUnauthorizedHandler } from "@/lib/api";
import { authApi } from "@/lib/endpoints";
import { queryKeys } from "@/lib/queryClient";
import { forgetStoredTheme } from "@/lib/themeStorage";

const POLL_MS = 30_000;
const GUEST = { authenticated: false, user: null, unread_notifications: 0, unread_messages: 0 };

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const qc = useQueryClient();
  const wasAuthed = useRef(false);

  const query = useQuery({
    queryKey: queryKeys.session,
    queryFn: fetchSession,
    staleTime: 10_000,
    refetchInterval: (q) => (q.state.data?.authenticated ? POLL_MS : false),
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    retry: 1,
  });

  const data = query.data;
  const user = data?.authenticated ? data.user : null;
  const status = query.isPending
    ? "loading"
    : user
      ? "authenticated"
      : data
        ? "unauthenticated"
        : "error";

  // Tell the person when their session disappears underneath them (expiry, signed out elsewhere).
  useEffect(() => {
    if (status === "authenticated") wasAuthed.current = true;
    else if (status === "unauthenticated" && wasAuthed.current) {
      wasAuthed.current = false;
      toast.info("You have been signed out. Please sign in again.");
    }
  }, [status]);

  // A 401 from any API call -> clear the session; guards handle the redirect.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      const current = qc.getQueryData(queryKeys.session);
      if (current?.authenticated) qc.setQueryData(queryKeys.session, GUEST);
    });
    return () => setUnauthorizedHandler(null);
  }, [qc]);

  const refresh = useCallback(() => qc.fetchQuery({ queryKey: queryKeys.session, queryFn: fetchSession, staleTime: 0 }), [qc]);

  const login = useCallback(async (credentials) => {
    await authApi.login(credentials);
    // The CSRF token rotates on login, so always re-read the session (also carries the unread counters).
    const fresh = await refresh();
    return fresh?.user || null;
  }, [refresh]);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      wasAuthed.current = false; // do not toast "signed out" for a deliberate logout
      qc.clear();
      forgetStoredTheme();
      // Fresh token for the login screen.
      try { qc.setQueryData(queryKeys.session, await fetchSession()); } catch { qc.setQueryData(queryKeys.session, GUEST); }
    }
  }, [qc]);

  const patchUser = useCallback((patch) => {
    qc.setQueryData(queryKeys.session, (old) => (old?.user ? { ...old, user: { ...old.user, ...patch } } : old));
  }, [qc]);

  const value = useMemo(() => {
    const role = user?.role || null;
    return {
      status,
      user,
      role,
      isAuthenticated: status === "authenticated",
      isStudent: role === "STUDENT",
      isFaculty: role === "FACULTY",
      isAdmin: role === "ADMIN",
      hasRole: (...roles) => !!role && roles.flat().includes(role),
      unread: {
        notifications: data?.unread_notifications || 0,
        messages: data?.unread_messages || 0,
      },
      login,
      logout,
      refresh,
      patchUser,
      retry: () => query.refetch(),
    };
  }, [status, user, data, login, logout, refresh, patchUser, query]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
