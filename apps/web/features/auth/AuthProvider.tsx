"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { ApiError, request, refreshWebSession } from "../../lib/api/client";
import type { Membership, MembershipRole, Me, Tokens } from "../../lib/types";

type AuthStatus = "restoring" | "unauthenticated" | "authenticated";
type AuthContextValue = {
  status: AuthStatus;
  session: Tokens | null;
  me: Me | null;
  requestOtp: (phone: string, requestedRole?: MembershipRole) => Promise<string>;
  verifyOtp: (challengeId: string, otp: string) => Promise<{ preSessionToken: string; memberships: Membership[] }>;
  selectMembership: (preSessionToken: string, membershipId: string) => Promise<Tokens>;
  logout: () => Promise<void>;
  request: typeof request;
  refresh: () => Promise<Tokens | null>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("restoring");
  const [session, setSession] = useState<Tokens | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const refreshInFlight = useRef<Promise<Tokens | null> | null>(null);

  const applySession = useCallback(async (tokens: Tokens) => {
    const identity = await request<Me>("/api/v1/auth/me", {}, tokens.access_token);
    setSession(tokens);
    setMe(identity);
    setStatus("authenticated");
    return tokens;
  }, []);

  const refresh = useCallback(async () => {
    if (refreshInFlight.current) return refreshInFlight.current;
    const pending = (async () => {
      try {
        return await applySession(await refreshWebSession());
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          setSession(null);
          setMe(null);
          setStatus("unauthenticated");
          return null;
        }
        throw error;
      }
    })();
    refreshInFlight.current = pending;
    try {
      return await pending;
    } finally {
      if (refreshInFlight.current === pending) refreshInFlight.current = null;
    }
  }, [applySession]);

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => refresh()).catch(() => {
      if (active) {
        setSession(null);
        setMe(null);
        setStatus("unauthenticated");
      }
    });
    return () => {
      active = false;
    };
  }, [refresh]);

  const authenticatedRequest = useCallback(async <T,>(path: string, options: RequestInit = {}) => {
    const token = session?.access_token;
    try {
      return await request<T>(path, options, token);
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401 || !token) throw error;
      const renewed = await refresh();
      if (!renewed) throw error;
      return request<T>(path, options, renewed.access_token);
    }
  }, [refresh, session]);

  const requestOtp = useCallback(async (phone: string, requestedRole?: MembershipRole) => {
    const result = await request<{ challenge_id: string }>("/api/v1/auth/otp/request", { method: "POST", body: JSON.stringify({ phone, ...(requestedRole ? { requested_role: requestedRole } : {}) }) });
    return result.challenge_id;
  }, []);

  const verifyOtp = useCallback(async (challengeId: string, otp: string) => {
    const verified = await request<{ pre_session_token: string }>("/api/v1/auth/otp/verify", { method: "POST", body: JSON.stringify({ challenge_id: challengeId, otp }) });
    const options = await request<{ memberships: Membership[] }>("/api/v1/auth/memberships", { method: "POST", body: JSON.stringify({ pre_session_token: verified.pre_session_token }) });
    return { preSessionToken: verified.pre_session_token, memberships: options.memberships };
  }, []);

  const selectMembership = useCallback(async (preSessionToken: string, membershipId: string) => {
    const tokens = await request<Tokens>("/api/v1/auth/web-session", { method: "POST", body: JSON.stringify({ pre_session_token: preSessionToken, membership_id: membershipId }) });
    return applySession(tokens);
  }, [applySession]);

  const logout = useCallback(async () => {
    if (session) await request<void>("/api/v1/auth/web-logout", { method: "POST" }, session.access_token).catch(() => undefined);
    setSession(null);
    setMe(null);
    setStatus("unauthenticated");
  }, [session]);

  const value = useMemo<AuthContextValue>(() => ({ status, session, me, request: authenticatedRequest, requestOtp, verifyOtp, selectMembership, logout, refresh }), [authenticatedRequest, logout, me, refresh, requestOtp, selectMembership, session, status, verifyOtp]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
