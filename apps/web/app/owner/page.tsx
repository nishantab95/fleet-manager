"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AccessDenied } from "../../features/auth/AccessDenied";
import { useAuth } from "../../features/auth/AuthProvider";
import { OwnerWorkspace } from "../../features/owner/OwnerWorkspace";

export default function OwnerPage() {
  const router = useRouter();
  const { status, me } = useAuth();
  useEffect(() => { if (status === "unauthenticated") router.replace("/login"); }, [router, status]);
  if (status === "restoring") return <main className="auth-shell"><section className="auth-card">Restoring secure browser session…</section></main>;
  if (status !== "authenticated" || !me) return null;
  if (me.role !== "OWNER_ADMIN") return <AccessDenied message="Only OWNER_ADMIN memberships may use the Owner workspace." />;
  return <OwnerWorkspace />;
}
