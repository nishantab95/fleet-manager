"use client";

import { Suspense } from "react";
import { LoginWorkspace } from "../../features/auth/LoginWorkspace";

export default function LoginPage() {
  return <Suspense fallback={<main className="auth-shell"><section className="auth-card">Loading secure access…</section></main>}><LoginWorkspace /></Suspense>;
}
