"use client";

/* Blob URLs are private, already-authorized image bytes; next/image cannot optimize them. */
/* eslint-disable @next/next/no-img-element */

import type { EvidenceMetadata } from "../../lib/api/client";

export type EvidenceDetails = EvidenceMetadata & { eventId: string };

export function EvidenceModal({ url, details, onClose }: { url: string; details: EvidenceDetails; onClose: () => void }) {
  return <div className="evidence-backdrop" role="presentation" onClick={onClose}>
    <section aria-label="Operational evidence" aria-modal="true" className="evidence-modal" onClick={(event) => event.stopPropagation()} role="dialog">
      <div className="content-heading"><div><p className="eyebrow">Private evidence</p><h2>{details.eventType.replaceAll("_", " ")}</h2></div><button aria-label="Close evidence" className="secondary" onClick={onClose} type="button">Close</button></div>
      <dl className="evidence-details"><div><dt>Driver</dt><dd>{details.driverName}</dd></div><div><dt>Tipper</dt><dd>{details.tipperRegistrationNumber}</dd></div><div><dt>Captured</dt><dd>{details.deviceCreatedAt ? new Date(details.deviceCreatedAt).toLocaleString() : "Unavailable"}</dd></div><div><dt>Event ID</dt><dd>{details.eventId}</dd></div></dl>
      <img alt={`${details.eventType.replaceAll("_", " ")} evidence for ${details.tipperRegistrationNumber}`} className="evidence-image" src={url} />
      <a className="evidence-full-size" href={url} rel="noreferrer" target="_blank">Open full size</a>
    </section>
  </div>;
}
