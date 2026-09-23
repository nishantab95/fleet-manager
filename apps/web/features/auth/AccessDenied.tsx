"use client";

import { useAuth } from "./AuthProvider";

export function AccessDenied({ message = "This membership is not permitted to use this workspace." }: { message?: string }) {
  const { logout } = useAuth();
  return (
    <main className="auth-shell">
      <section className="auth-card">
        <p className="eyebrow">Fleet Manager · Access denied</p>
        <h1>Workspace unavailable</h1>
        <div className="notice error">{message}</div>
        <button className="secondary" onClick={() => void logout()} type="button">Sign out</button>
      </section>
    </main>
  );
}
