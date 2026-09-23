"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AccessDenied } from "../../features/auth/AccessDenied";
import { useAuth } from "../../features/auth/AuthProvider";
import { SupervisorWorkspace } from "../../features/supervisor/SupervisorWorkspace";

export default function SupervisorPage() {
  const router = useRouter();
  const { status, me } = useAuth();
  useEffect(() => { if (status === "unauthenticated") router.replace("/login?workspace=supervisor"); }, [router, status]);
  if (status === "restoring") return <main className="auth-shell"><section className="auth-card">Restoring secure browser session…</section></main>;
  if (status !== "authenticated" || !me) return null;
  if (me.role !== "SUPERVISOR") return <AccessDenied message="Only SUPERVISOR memberships may use this internal QA workspace." />;
  return <SupervisorWorkspace />;
}
