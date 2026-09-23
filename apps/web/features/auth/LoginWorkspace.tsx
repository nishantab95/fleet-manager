"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { driverQaEnabled, workspaceForRole } from "../../lib/auth/config";
import { useAuth } from "./AuthProvider";
import { AccessDenied } from "./AccessDenied";

const workspaceLabels = {
  owner: "OWNER TEST WORKSPACE",
  supervisor: "SUPERVISOR TEST WORKSPACE",
  "driver-test": "DRIVER QA TEST WORKSPACE",
} as const;

export function workspaceHintLabel(value: string | null): string | null {
  if (!value || !(value in workspaceLabels)) return null;
  return workspaceLabels[value as keyof typeof workspaceLabels];
}

export function LoginWorkspace() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const auth = useAuth();
  const [phone, setPhone] = useState("");
  const [otp, setOtp] = useState("");
  const [challengeId, setChallengeId] = useState("");
  const [preSessionToken, setPreSessionToken] = useState("");
  const [memberships, setMemberships] = useState<Awaited<ReturnType<typeof auth.verifyOtp>>["memberships"]>([]);
  const [phase, setPhase] = useState<"phone" | "otp" | "membership">("phone");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (auth.status === "authenticated" && auth.me) {
      const target = workspaceForRole(auth.me.role);
      if (target) router.replace(target);
    }
  }, [auth.me, auth.status, router]);

  const reason = searchParams.get("reason");
  const workspaceLabel = workspaceHintLabel(searchParams.get("workspace"));
  const submitPhone = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setChallengeId(await auth.requestOtp(phone.trim()));
      setPhase("otp");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not request an OTP.");
    } finally {
      setBusy(false);
    }
  };

  const submitOtp = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await auth.verifyOtp(challengeId, otp.trim());
      setPreSessionToken(result.preSessionToken);
      setMemberships(result.memberships);
      setPhase("membership");
      if (!result.memberships.length) setError("No active company membership is available.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The OTP could not be verified.");
    } finally {
      setBusy(false);
    }
  };

  const selectMembership = async (membershipId: string) => {
    setBusy(true);
    setError("");
    try {
      const session = await auth.selectMembership(preSessionToken, membershipId);
      const target = workspaceForRole(session.role);
      if (target) router.replace(target);
      else setError("Access denied: Driver QA is disabled. Enable NEXT_PUBLIC_ENABLE_DRIVER_QA=true for the local QA client.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not create a session.");
    } finally {
      setBusy(false);
    }
  };

  if (auth.status === "restoring") return <main className="auth-shell"><section className="auth-card"><p>Restoring secure browser session…</p></section></main>;
  if (auth.status === "authenticated" && auth.me && !workspaceForRole(auth.me.role)) return <AccessDenied message="Access denied: the Driver QA web client is disabled by configuration." />;

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <p className="eyebrow">Fleet Manager · Secure access</p>
        <h1>Choose your operations workspace</h1>
        {workspaceLabel && <div className="workspace-hint">{workspaceLabel}</div>}
        <p className="summary">Sign in with your phone and choose an active company membership. The access token is runtime-only; the refresh credential is an HttpOnly cookie.</p>
        {reason === "driver-disabled" && <div className="notice error">Access denied: the Driver QA workspace is disabled by configuration.</div>}
        {!driverQaEnabled && <div className="notice">Driver QA is disabled by default. Owner and Supervisor workspaces remain available.</div>}
        {phase === "phone" && <form className="stack" onSubmit={submitPhone}><label>Phone number<input value={phone} onChange={(event) => setPhone(event.target.value)} required /></label><button disabled={busy} type="submit">{busy ? "Requesting…" : "Send OTP"}</button></form>}
        {phase === "otp" && <form className="stack" onSubmit={submitOtp}><label>One-time code<input inputMode="numeric" maxLength={6} pattern="[0-9]{6}" value={otp} onChange={(event) => setOtp(event.target.value)} required /></label><button disabled={busy} type="submit">{busy ? "Checking…" : "Verify and continue"}</button><button className="secondary" type="button" onClick={() => setPhase("phone")}>Use another phone</button></form>}
        {phase === "membership" && <div className="stack"><h2>Choose company access</h2>{memberships.map((membership) => <button className="choice" disabled={busy} key={membership.membership_id} onClick={() => void selectMembership(membership.membership_id)} type="button"><span>{membership.company_name}</span><small>{membership.role}</small></button>)}</div>}
        {error && <div className="notice error">{error}</div>}
      </section>
    </main>
  );
}
