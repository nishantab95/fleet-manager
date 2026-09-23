"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AccessDenied } from "../../features/auth/AccessDenied";
import { useAuth } from "../../features/auth/AuthProvider";
import { DriverQaWorkspace } from "../../features/driver-test/DriverQaWorkspace";
import { driverQaEnabled } from "../../lib/auth/config";

export default function DriverTestPage() {
  const router = useRouter();
  const { status, me } = useAuth();
  useEffect(() => { if (status === "unauthenticated") router.replace("/login?workspace=driver-test"); }, [router, status]);
  if (status === "restoring") return <main className="auth-shell"><section className="auth-card">Restoring secure browser session…</section></main>;
  if (status !== "authenticated" || !me) return null;
  if (!driverQaEnabled) return <AccessDenied message="The Driver QA route is disabled by default. Set NEXT_PUBLIC_ENABLE_DRIVER_QA=true only for the controlled local QA build." />;
  if (me.role !== "DRIVER") return <AccessDenied message="Only DRIVER memberships may use the Driver QA simulator." />;
  return <DriverQaWorkspace />;
}
