"use client";

import { useEffect, type ReactNode } from "react";

type StatusTone = "positive" | "warning" | "neutral" | "danger" | "info";

const statusTone: Record<string, StatusTone> = {
  ACTIVE: "positive",
  INVITED: "warning",
  INACTIVE: "neutral",
  DEACTIVATED: "neutral",
  ON_DUTY: "positive",
  ASSIGNED: "info",
  AVAILABLE: "neutral",
  DEPLOYED: "positive",
  UNDEPLOYED: "warning",
  OWNED: "info",
  RENTED: "warning",
};

export function StatusChip({
  status,
  label,
  tone,
}: {
  status: string;
  label?: string;
  tone?: StatusTone;
}) {
  const resolved = tone ?? statusTone[status] ?? "neutral";
  return (
    <span className={`owner-status-chip owner-status-chip--${resolved}`}>
      <span aria-hidden="true" />
      {label ?? status.replaceAll("_", " ")}
    </span>
  );
}

export function PanelHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="owner-section-heading">
      <div>
        {eyebrow && <p className="owner-section-eyebrow">{eyebrow}</p>}
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
      {action && <div className="owner-section-action">{action}</div>}
    </div>
  );
}

export function FilterToolbar({ children }: { children: ReactNode }) {
  return <div className="owner-toolbar">{children}</div>;
}

export function OperationsTable({
  label,
  children,
  variant = "default",
}: {
  label: string;
  children: ReactNode;
  variant?: "default" | "fleet";
}) {
  return (
    <div className={`owner-table-shell ${variant === "fleet" ? "owner-table-shell--fleet" : ""}`}>
      <table aria-label={label} className={`owner-table ${variant === "fleet" ? "owner-table--fleet" : ""}`}>
        {children}
      </table>
    </div>
  );
}

export function SortButton({
  label,
  active,
  direction,
  onClick,
}: {
  label: string;
  active: boolean;
  direction: "asc" | "desc";
  onClick: () => void;
}) {
  return (
    <button
      aria-label={`Sort by ${label}`}
      className="owner-sort"
      onClick={onClick}
      type="button"
    >
      {label}
      <span aria-hidden="true">{active ? (direction === "asc" ? "↑" : "↓") : "↕"}</span>
    </button>
  );
}

export function EmptyTableRow({
  colSpan,
  title,
  detail,
}: {
  colSpan: number;
  title: string;
  detail?: string;
}) {
  return (
    <tr>
      <td colSpan={colSpan}>
        <div className="owner-empty-state">
          <span aria-hidden="true" className="owner-empty-route" />
          <strong>{title}</strong>
          {detail && <small>{detail}</small>}
        </div>
      </td>
    </tr>
  );
}

export function InlineFeedback({
  error,
  success,
}: {
  error?: string;
  success?: string;
}) {
  if (!error && !success) return null;
  return (
    <div
      className={`owner-feedback ${error ? "owner-feedback--error" : "owner-feedback--success"}`}
      role={error ? "alert" : "status"}
    >
      {error || success}
    </div>
  );
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  busy = false,
  confirmDisabled = false,
  children,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  busy?: boolean;
  confirmDisabled?: boolean;
  children?: ReactNode;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onCancel();
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [busy, onCancel, open]);

  if (!open) return null;
  return (
    <div className="owner-dialog-backdrop" role="presentation">
      <section
        aria-describedby="owner-confirm-description"
        aria-labelledby="owner-confirm-title"
        aria-modal="true"
        className="owner-dialog"
        role="dialog"
      >
        <p className="owner-section-eyebrow">Confirm operation</p>
        <h2 id="owner-confirm-title">{title}</h2>
        <p id="owner-confirm-description">{description}</p>
        {children}
        <div className="owner-dialog-actions">
          <button autoFocus className="secondary" disabled={busy} onClick={onCancel} type="button">
            Cancel
          </button>
          <button disabled={busy || confirmDisabled} onClick={onConfirm} type="button">
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
}

export function DetailsDialog({
  open,
  title,
  children,
  onClose,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [onClose, open]);

  if (!open) return null;
  return (
    <div className="owner-dialog-backdrop" role="presentation">
      <section aria-labelledby="owner-details-title" aria-modal="true" className="owner-dialog owner-dialog--wide" role="dialog">
        <div className="owner-dialog-heading">
          <h2 id="owner-details-title">{title}</h2>
          <button aria-label="Close details" className="owner-icon-button" onClick={onClose} type="button">×</button>
        </div>
        {children}
      </section>
    </div>
  );
}
