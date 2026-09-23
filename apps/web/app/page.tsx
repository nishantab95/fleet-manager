"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AccessDenied } from "../features/auth/AccessDenied";
import { useAuth } from "../features/auth/AuthProvider";
import { driverQaEnabled, workspaceForRole } from "../lib/auth/config";

export default function HomePage() {
  const router = useRouter();
  const { status, me } = useAuth();
  useEffect(() => {
    if (status === "unauthenticated") router.replace("/login");
    if (status === "authenticated" && me && workspaceForRole(me.role)) router.replace(workspaceForRole(me.role)!);
  }, [me, router, status]);
  if (status === "authenticated" && me && me.role === "DRIVER" && !driverQaEnabled) return <AccessDenied message="Access denied: the Driver QA web client is disabled by configuration." />;
  return <main className="auth-shell"><section className="auth-card"><p>Restoring secure browser session…</p></section></main>;
}
