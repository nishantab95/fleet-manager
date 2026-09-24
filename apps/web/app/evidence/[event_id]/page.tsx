"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { AccessDenied } from "../../../features/auth/AccessDenied";
import { useAuth } from "../../../features/auth/AuthProvider";
import { ApiError, fetchPrivateEvidence } from "../../../lib/api/client";
import { EvidenceModal, type EvidenceDetails } from "../../../features/shared/EvidenceViewer";

export default function EvidencePage() {
  const router = useRouter();
  const params = useParams<{ event_id: string }>();
  const eventId = params.event_id;
  const { status, me, session, refresh } = useAuth();
  const [evidenceUrl, setEvidenceUrl] = useState<string | null>(null);
  const [details, setDetails] = useState<EvidenceDetails | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (status === "unauthenticated") router.replace(`/login?returnTo=/evidence/${eventId}`);
  }, [eventId, router, status]);

  useEffect(() => {
    if (status !== "authenticated" || !me || !session || !eventId || !["OWNER_ADMIN", "SUPERVISOR"].includes(me.role)) return;
    const currentSession = session;
    const currentRole = me.role;
    let active = true;
    async function load() {
      setLoading(true);
      setError("");
      const endpoint = currentRole === "OWNER_ADMIN" ? "reports" : "supervisor";
      try {
        let result;
        try {
          result = await fetchPrivateEvidence(`/api/v1/${endpoint}/events/${eventId}/evidence`, currentSession.access_token);
        } catch (caught) {
          if (!(caught instanceof ApiError) || caught.status !== 401) throw caught;
          const renewed = await refresh();
          if (!renewed) throw caught;
          result = await fetchPrivateEvidence(`/api/v1/${endpoint}/events/${eventId}/evidence`, renewed.access_token);
        }
        if (active) {
          setEvidenceUrl(result.url);
          setDetails({ ...result.metadata, eventId });
        } else {
          URL.revokeObjectURL(result.url);
        }
      } catch (caught) {
        if (active) setError(caught instanceof Error ? caught.message : "Evidence could not be loaded.");
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => { active = false; };
  }, [eventId, me, refresh, session, status]);

  useEffect(() => () => { if (evidenceUrl) URL.revokeObjectURL(evidenceUrl); }, [evidenceUrl]);

  if (status === "restoring") return <main className="auth-shell"><section className="auth-card">Restoring secure browser session…</section></main>;
  if (status === "unauthenticated") return null;
  if (!me || !["OWNER_ADMIN", "SUPERVISOR"].includes(me.role)) return <AccessDenied message="Only an authorized Owner or Supervisor may view operational evidence." />;
  if (loading) return <main className="auth-shell"><section className="auth-card">Loading private evidence…</section></main>;
  if (error || !evidenceUrl || !details) return <main className="auth-shell"><section className="auth-card"><h1>Evidence unavailable</h1><div className="notice error">{error || "This event has no available evidence."}</div><button className="secondary" onClick={() => router.back()} type="button">Close</button></section></main>;
  return <main className="evidence-route"><EvidenceModal details={details} onClose={() => router.back()} url={evidenceUrl} /></main>;
}
