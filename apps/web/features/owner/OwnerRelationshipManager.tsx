"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";

import { ApiError, type WebRequest } from "../../lib/api/client";
import type {
  OwnerAsset,
  OwnerOperationIntent,
  OwnerOperationPlan,
  OwnerOperationResult,
  OwnerPerson,
  OwnerSite,
} from "../../lib/types";
import { title } from "./catalogs";
import { InlineFeedback, StatusChip } from "./OwnerUi";

export type OwnerAssetManagerAction =
  | "DEPLOY_ASSET"
  | "MOVE_DEPLOYMENT"
  | "REMOVE_DEPLOYMENT"
  | "ASSIGN_DRIVER"
  | "REASSIGN_DRIVER"
  | "END_ASSIGNMENT"
  | "DEACTIVATE_ASSET"
  | "REACTIVATE_ASSET";

export type OwnerRelationshipTarget =
  | {
      kind: "asset";
      assetId: string;
      focus?: "driver" | "site" | "lifecycle";
      presetSiteId?: string | null;
      presetDriverId?: string | null;
      presetRegularDutyMinutes?: number;
      initialAction?: OwnerAssetManagerAction;
    }
  | {
      kind: "person";
      membershipId: string;
      presetAssetId?: string | null;
      presetSiteId?: string | null;
    };

export type OwnerRelationshipManagerProps = {
  target: OwnerRelationshipTarget | null;
  assets: OwnerAsset[];
  people: OwnerPerson[];
  sites: OwnerSite[];
  apiRequest: WebRequest;
  onClose: () => void;
  onComplete: (message: string) => void;
  onViewActiveDuty?: (assetId: string) => void;
  onViewAssetHistory?: (assetId: string) => void;
  onForceCloseDutyAndDeactivate?: (assetId: string, reason: string) => Promise<string>;
};

type ConfirmationCopy = {
  title: string;
  description: string;
  confirmLabel: string;
};

type Confirmation = ConfirmationCopy & {
  intent: OwnerOperationIntent;
  plan: OwnerOperationPlan;
};

function assetLabel(asset: OwnerAsset) {
  return asset.short_name || asset.registration_number || "Unnamed asset";
}

function subtitleForAsset(asset: OwnerAsset) {
  return [asset.registration_number, title(asset.asset_type), title(asset.ownership_type)].filter(Boolean).join(" · ");
}

function siteLabel(site: OwnerSite) {
  return site.short_name || site.name;
}

function personRoleLabel(person: OwnerPerson) {
  return person.role === "DRIVER" ? "Driver / Operator" : title(person.role);
}

function operationError(caught: unknown) {
  if (caught instanceof ApiError) {
    if (caught.status === 409 || caught.code === "CONFLICT") {
      return "State changed. Refresh and try again.";
    }
    if (caught.status === 404 && caught.code === "NOT_FOUND") {
      return "This record is no longer available. Refresh and try again.";
    }
    if (caught.status === 404 && !caught.code) {
      return "The Fleet Manager server must be updated before this action can be used.";
    }
  }
  return caught instanceof Error ? caught.message : "The request could not be completed.";
}

function appendError(current: string | undefined, next: string) {
  return current ? `${current} ${next}` : next;
}

function dateTime(value: string | null) {
  if (!value) return "Start time unavailable";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Start time unavailable";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(parsed);
}

function initialAssetSite(target: Extract<OwnerRelationshipTarget, { kind: "asset" }>, asset?: OwnerAsset) {
  if (target.presetSiteId !== undefined) return target.presetSiteId ?? "";
  if (target.initialAction === "REMOVE_DEPLOYMENT") return "";
  return asset?.current_deployment?.site_id ?? "";
}

function initialAssetDriver(target: Extract<OwnerRelationshipTarget, { kind: "asset" }>, asset?: OwnerAsset) {
  if (target.presetDriverId !== undefined) return target.presetDriverId ?? "";
  if (target.initialAction === "REMOVE_DEPLOYMENT" || target.initialAction === "END_ASSIGNMENT") return "";
  return asset?.active_assignment?.driver_membership_id ?? "";
}

function defaultAssetFocus(target: Extract<OwnerRelationshipTarget, { kind: "asset" }>) {
  if (target.focus) return target.focus;
  if (["DEPLOY_ASSET", "MOVE_DEPLOYMENT", "REMOVE_DEPLOYMENT"].includes(target.initialAction ?? "")) return "site";
  if (["ASSIGN_DRIVER", "REASSIGN_DRIVER", "END_ASSIGNMENT"].includes(target.initialAction ?? "")) return "driver";
  if (["DEACTIVATE_ASSET", "REACTIVATE_ASSET"].includes(target.initialAction ?? "")) return "lifecycle";
  return undefined;
}

function useOperationRunner({ apiRequest, onClose, onComplete }: Pick<OwnerRelationshipManagerProps, "apiRequest" | "onClose" | "onComplete">) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);

  const preview = async (intent: OwnerOperationIntent) => {
    setBusy(true);
    setError("");
    try {
      return await apiRequest<OwnerOperationPlan>("/api/v1/owner/operations/preview", {
        method: "POST",
        body: JSON.stringify(intent),
      });
    } catch (caught) {
      setError(operationError(caught));
      return null;
    } finally {
      setBusy(false);
    }
  };

  const execute = async (intent: OwnerOperationIntent, stateToken: string) => {
    setBusy(true);
    setError("");
    try {
      const completed = await apiRequest<OwnerOperationResult>("/api/v1/owner/operations/execute", {
        method: "POST",
        body: JSON.stringify({ ...intent, state_token: stateToken }),
      });
      onComplete(completed.message);
      onClose();
    } catch (caught) {
      setConfirmation(null);
      setError(operationError(caught));
    } finally {
      setBusy(false);
    }
  };

  return {
    busy,
    confirmation,
    error,
    preview,
    execute,
    setError,
    confirm: (intent: OwnerOperationIntent, plan: OwnerOperationPlan, copy: ConfirmationCopy) => setConfirmation({ intent, plan, ...copy }),
    cancelConfirmation: () => setConfirmation(null),
  };
}

function ManagerShell({
  busy,
  children,
  eyebrow,
  onDismiss,
  subtitle,
  title: heading,
}: {
  busy: boolean;
  children: ReactNode;
  eyebrow: string;
  onDismiss: () => void;
  subtitle?: string;
  title: string;
}) {
  useEffect(() => {
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onDismiss();
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [busy, onDismiss]);

  return <div className="owner-dialog-backdrop" role="presentation">
    <section aria-labelledby="owner-relationship-manager-title" aria-modal="true" className="owner-dialog owner-dialog--wide owner-relationship-manager" role="dialog">
      <div className="owner-dialog-heading">
        <div className="owner-manager-identity">
          <p className="owner-section-eyebrow">{eyebrow}</p>
          <h2 id="owner-relationship-manager-title">{heading}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        <button aria-label="Close management form" className="owner-icon-button" disabled={busy} onClick={onDismiss} type="button">×</button>
      </div>
      {children}
    </section>
  </div>;
}

function ConfirmationView({ runner }: { runner: ReturnType<typeof useOperationRunner> }) {
  const confirmation = runner.confirmation;
  if (!confirmation) return null;
  return <>
    <InlineFeedback error={runner.error} />
    <div className="owner-manager-confirmation">
      <p>{confirmation.description}</p>
      {confirmation.plan.planned_changes.length > 0 && <ul className="owner-manager-change-list">{confirmation.plan.planned_changes.map((change) => <li key={change}>{change}</li>)}</ul>}
      {confirmation.plan.warnings.length > 0 && <ul className="owner-manager-warnings">{confirmation.plan.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>}
    </div>
    <div className="owner-dialog-actions">
      <button className="secondary" disabled={runner.busy} onClick={runner.cancelConfirmation} type="button">Cancel</button>
      <button disabled={runner.busy} onClick={() => void runner.execute(confirmation.intent, confirmation.plan.state_token)} type="button">{runner.busy ? "Working…" : confirmation.confirmLabel}</button>
    </div>
  </>;
}

function AssetManager(props: OwnerRelationshipManagerProps & { target: Extract<OwnerRelationshipTarget, { kind: "asset" }> }) {
  const { target, assets, people, sites, apiRequest, onClose, onComplete, onForceCloseDutyAndDeactivate, onViewActiveDuty, onViewAssetHistory } = props;
  const asset = assets.find((item) => item.id === target.assetId);
  const [siteId, setSiteId] = useState(() => initialAssetSite(target, asset));
  const [driverId, setDriverId] = useState(() => initialAssetDriver(target, asset));
  const [activateDriverRole, setActivateDriverRole] = useState(false);
  const [siteError, setSiteError] = useState("");
  const [driverError, setDriverError] = useState("");
  const [formError, setFormError] = useState("");
  const [dutyStartedAt, setDutyStartedAt] = useState<string | null>(null);
  const [forceStage, setForceStage] = useState<"idle" | "warning" | "reason" | "confirm">("idle");
  const [forceReason, setForceReason] = useState("");
  const [forceBusy, setForceBusy] = useState(false);
  const [forceError, setForceError] = useState("");
  const runner = useOperationRunner(props);

  const currentDriverId = asset?.active_assignment?.driver_membership_id ?? "";
  const currentSiteId = asset?.current_deployment?.site_id ?? "";
  const currentDriver = people.find((person) => person.membership_id === currentDriverId);
  const selectedDriver = people.find((person) => person.membership_id === driverId);
  const onDuty = Boolean(currentDriver?.has_active_duty);
  const activeSites = useMemo(() => sites.filter((site) => site.status === "ACTIVE"), [sites]);
  const driverOptions = useMemo(() => {
    const statusOrder = { ACTIVE: 0, INVITED: 1, INACTIVE: 2 } as const;
    return people
      .filter((person) => person.role === "DRIVER" && (person.membership_id === currentDriverId || !person.has_active_assignment))
      .sort((left, right) => {
        if (left.membership_id === currentDriverId) return -1;
        if (right.membership_id === currentDriverId) return 1;
        return statusOrder[left.status] - statusOrder[right.status] || left.display_name.localeCompare(right.display_name);
      });
  }, [currentDriverId, people]);
  const focus = defaultAssetFocus(target);

  useEffect(() => {
    if (!asset || !onDuty) return;
    let cancelled = false;
    void apiRequest<OwnerOperationPlan>("/api/v1/owner/operations/preview", {
      method: "POST",
      body: JSON.stringify({ action: "DEACTIVATE_ASSET", asset_id: asset.id }),
    }).then((plan) => {
      if (cancelled) return;
      const duty = [...plan.current_state, ...plan.dependencies].find((item) => item.kind === "DUTY");
      const startedAt = duty?.details.started_at;
      setDutyStartedAt(typeof startedAt === "string" ? startedAt : null);
    }).catch(() => {
      if (!cancelled) setDutyStartedAt(null);
    });
    return () => { cancelled = true; };
  }, [apiRequest, asset, onDuty]);

  const clearErrors = () => {
    setSiteError("");
    setDriverError("");
    setFormError("");
    runner.setError("");
  };

  const applyBlockedReasons = (reasons: string[]) => {
    let nextSiteError = "";
    let nextDriverError = "";
    const remaining: string[] = [];
    for (const reason of reasons) {
      const normalized = reason.toLowerCase();
      if (normalized.includes("site") || normalized.includes("deploy") || normalized.includes("destination")) {
        nextSiteError = appendError(nextSiteError, reason);
      } else if (normalized.includes("driver") || normalized.includes("operator") || normalized.includes("assignment")) {
        nextDriverError = appendError(nextDriverError, reason);
      } else {
        remaining.push(reason);
      }
    }
    setSiteError(nextSiteError);
    setDriverError(nextDriverError);
    setFormError(remaining.join(" "));
  };

  const prepare = async (intent: OwnerOperationIntent, confirmation?: ConfirmationCopy) => {
    clearErrors();
    const plan = await runner.preview(intent);
    if (!plan) return;
    if (!plan.can_execute) {
      const duty = [...plan.current_state, ...plan.dependencies].find((item) => item.kind === "DUTY");
      if (intent.action === "DEACTIVATE_ASSET" && duty) {
        const startedAt = duty.details.started_at;
        setDutyStartedAt(typeof startedAt === "string" ? startedAt : null);
        setForceStage("warning");
        return;
      }
      applyBlockedReasons(plan.blocked_reasons.length ? plan.blocked_reasons : ["This change is not available in the current state."]);
      return;
    }
    if (confirmation) runner.confirm(intent, plan, confirmation);
    else await runner.execute(intent, plan.state_token);
  };

  const requireDriverRoleActivation = () => {
    if (selectedDriver?.status === "INACTIVE" && !activateDriverRole) {
      setDriverError("Include Driver / Operator role reactivation in this setup.");
      return true;
    }
    return false;
  };

  const reactivate = async (withSetup: boolean) => {
    clearErrors();
    if (withSetup && !siteId && !driverId) {
      setSiteError("Choose a Site for setup, or use Reactivate only.");
      return;
    }
    if (withSetup && driverId && !siteId) {
      setSiteError("Choose a Site before assigning a Driver / Operator.");
      return;
    }
    if (withSetup && requireDriverRoleActivation()) return;
    await prepare({
      action: "REACTIVATE_ASSET",
      asset_id: target.assetId,
      site_id: withSetup ? siteId || null : null,
      driver_membership_id: withSetup ? driverId || null : null,
      activate_membership: withSetup && selectedDriver?.status === "INACTIVE" ? activateDriverRole : false,
      regular_duty_minutes: asset?.active_assignment?.regular_duty_minutes ?? target.presetRegularDutyMinutes ?? 600,
    });
  };

  const save = async () => {
    clearErrors();
    if (!asset) return;
    if (onDuty) {
      setFormError("Changes are unavailable while this duty is active.");
      return;
    }
    if (driverId && !siteId) {
      setSiteError("Choose a Site before assigning a Driver / Operator.");
      return;
    }
    if (requireDriverRoleActivation()) return;

    const regularDutyMinutes = asset.active_assignment?.regular_duty_minutes ?? target.presetRegularDutyMinutes ?? 600;
    let intent: OwnerOperationIntent | null = null;
    let confirmation: ConfirmationCopy | undefined;

    if (!currentSiteId && siteId) {
      if (driverId) {
        intent = { action: "ASSIGN_DRIVER", asset_id: asset.id, site_id: siteId, driver_membership_id: driverId, activate_membership: activateDriverRole, regular_duty_minutes: regularDutyMinutes };
      } else {
        intent = { action: "DEPLOY_ASSET", asset_id: asset.id, site_id: siteId };
      }
    } else if (currentSiteId && !siteId) {
      intent = { action: "REMOVE_DEPLOYMENT", asset_id: asset.id };
      confirmation = { title: `Remove ${assetLabel(asset)} from Site?`, description: "This ends the current deployment and any off-duty assignment together while preserving history.", confirmLabel: "Remove from Site" };
    } else if (currentSiteId && siteId !== currentSiteId) {
      if (driverId !== currentDriverId && driverId) {
        setDriverError("Save the Site move first, then change the Driver / Operator.");
        return;
      }
      if (!currentDriverId && driverId) {
        setDriverError("Save the Site move first, then assign the Driver / Operator.");
        return;
      }
      intent = { action: "MOVE_DEPLOYMENT", asset_id: asset.id, target_site_id: siteId, assignment_action: currentDriverId ? (driverId ? "KEEP" : "END") : null, regular_duty_minutes: regularDutyMinutes };
      confirmation = { title: `Move ${assetLabel(asset)}?`, description: currentDriverId && driverId ? `${currentDriver?.display_name ?? "The current Driver / Operator"} will remain assigned at the new Site.` : "The current deployment will end and a new historical deployment will begin.", confirmLabel: "Move Asset" };
    } else if (siteId === currentSiteId && driverId !== currentDriverId) {
      if (!currentDriverId && driverId) {
        intent = { action: "ASSIGN_DRIVER", asset_id: asset.id, site_id: siteId, driver_membership_id: driverId, activate_membership: activateDriverRole, regular_duty_minutes: regularDutyMinutes };
      } else if (currentDriverId && !driverId) {
        intent = { action: "END_ASSIGNMENT", asset_id: asset.id };
        confirmation = { title: "End Driver / Operator assignment?", description: `${currentDriver?.display_name ?? "The current Driver / Operator"} will be unassigned from ${assetLabel(asset)}. History will remain available.`, confirmLabel: "End assignment" };
      } else if (driverId) {
        intent = { action: "REASSIGN_DRIVER", asset_id: asset.id, driver_membership_id: driverId, activate_membership: activateDriverRole, regular_duty_minutes: regularDutyMinutes };
        confirmation = { title: "Change Driver / Operator?", description: `${assetLabel(asset)} will change from ${currentDriver?.display_name ?? "the current Driver / Operator"} to ${selectedDriver?.display_name ?? "the selected Driver / Operator"}.`, confirmLabel: "Change Driver" };
      }
    }

    if (!intent) {
      setFormError("No relationship changes are selected.");
      return;
    }
    await prepare(intent, confirmation);
  };

  const deactivate = async () => {
    if (!asset) return;
    if (onDuty) {
      clearErrors();
      setForceError("");
      setForceReason("");
      setForceStage("warning");
      return;
    }
    await prepare(
      { action: "DEACTIVATE_ASSET", asset_id: asset.id },
      { title: `Deactivate ${assetLabel(asset)}?`, description: "The off-duty assignment and Site deployment will end together. Relationship history will be preserved.", confirmLabel: "Deactivate" },
    );
  };

  const continueForceClose = () => {
    setForceError("");
    if (!forceReason.trim()) {
      setForceError("Enter a reason for force-closing this duty.");
      return;
    }
    setForceStage("confirm");
  };

  const forceCloseAndDeactivate = async () => {
    if (!asset) return;
    if (!onForceCloseDutyAndDeactivate) {
      setForceStage("warning");
      setForceError("Force-close is not available on the currently running Fleet Manager server.");
      return;
    }
    setForceBusy(true);
    setForceError("");
    try {
      const message = await onForceCloseDutyAndDeactivate(asset.id, forceReason.trim());
      onComplete(message);
      onClose();
    } catch (caught) {
      setForceStage("warning");
      setForceError(operationError(caught));
    } finally {
      setForceBusy(false);
    }
  };

  if (!asset) {
    return <ManagerShell busy={false} eyebrow="Manage asset" onDismiss={onClose} title="Asset unavailable"><InlineFeedback error="This asset is no longer available. Refresh and try again." /></ManagerShell>;
  }
  const endMeterLabel = asset.asset_type === "TIPPER" ? "END KM" : "END HMR";

  if (runner.confirmation) {
    return <ManagerShell busy={runner.busy} eyebrow="Confirm operation" onDismiss={runner.cancelConfirmation} title={runner.confirmation.title}><ConfirmationView runner={runner} /></ManagerShell>;
  }

  if (forceStage === "warning") {
    return <ManagerShell busy={forceBusy} eyebrow="Active duty warning" onDismiss={() => setForceStage("idle")} subtitle={subtitleForAsset(asset)} title={`Deactivate ${assetLabel(asset)}`}>
      <InlineFeedback error={forceError} />
      <div className="owner-manager-force-warning">
        <StatusChip label="On duty" status="ON_DUTY" />
        <h3>This asset currently has an active duty.</h3>
        <p>This Owner-only action closes the live duty and deactivates the Asset. It does not invent an END KM or HMR reading.</p>
        <dl className="owner-detail-list">
          <div><dt>Driver / Operator</dt><dd>{currentDriver?.display_name || "Unavailable"}</dd></div>
          <div><dt>Site</dt><dd>{asset.current_deployment?.site_name || "Unavailable"}</dd></div>
          <div><dt>Duty started</dt><dd>{dateTime(dutyStartedAt)}</dd></div>
        </dl>
      </div>
      <div className="owner-dialog-actions">
        <button className="secondary" disabled={forceBusy} onClick={() => setForceStage("idle")} type="button">Cancel</button>
        {onViewActiveDuty && <button className="secondary" onClick={() => { onClose(); onViewActiveDuty(asset.id); }} type="button">View duty</button>}
        <button disabled={forceBusy} onClick={() => { setForceError(""); setForceStage("reason"); }} type="button">Force close duty &amp; deactivate</button>
      </div>
    </ManagerShell>;
  }

  if (forceStage === "reason") {
    return <ManagerShell busy={forceBusy} eyebrow="Administrative resolution" onDismiss={() => setForceStage("warning")} subtitle={subtitleForAsset(asset)} title="Why must this duty be force-closed?">
      <InlineFeedback error={forceError} />
      <div className="owner-manager-force-warning">
        <p>Enter a short reason for the audit record. The duty will remain unchanged until you confirm the next screen.</p>
        <label>Reason *<textarea aria-label="Force-close reason" autoFocus maxLength={1000} onChange={(event) => { setForceReason(event.target.value); setForceError(""); }} placeholder="Driver forgot to end duty" required rows={3} value={forceReason} />{forceError && <span className="owner-field-error" role="alert">{forceError}</span>}</label>
      </div>
      <div className="owner-dialog-actions"><button className="secondary" disabled={forceBusy} onClick={() => setForceStage("warning")} type="button">Back</button><button disabled={forceBusy} onClick={continueForceClose} type="button">Continue</button></div>
    </ManagerShell>;
  }

  if (forceStage === "confirm") {
    return <ManagerShell busy={forceBusy} eyebrow="Final confirmation" onDismiss={() => setForceStage("reason")} subtitle={subtitleForAsset(asset)} title={`Force close duty & deactivate ${assetLabel(asset)}?`}>
      <InlineFeedback error={forceError} />
      <div className="owner-manager-confirmation owner-manager-confirmation--danger">
        <p>Fleet Manager will:</p>
        <ul className="owner-manager-change-list">
          <li>Force close {currentDriver?.display_name || "the Driver / Operator"}&apos;s active duty</li>
          <li>Mark {endMeterLabel} as missing when no legitimate end reading exists</li>
          <li>End the current Driver / Operator assignment</li>
          <li>Remove {assetLabel(asset)} from {asset.current_deployment?.site_name || "the current Site"}</li>
          <li>Deactivate {assetLabel(asset)}</li>
          <li>Preserve all existing history and evidence</li>
        </ul>
        <dl className="owner-detail-list"><div><dt>Duty started</dt><dd>{dateTime(dutyStartedAt)}</dd></div><div><dt>Reason</dt><dd>{forceReason.trim()}</dd></div></dl>
      </div>
      <div className="owner-dialog-actions"><button className="secondary" disabled={forceBusy} onClick={() => setForceStage("reason")} type="button">Cancel</button><button className="owner-danger-button" disabled={forceBusy} onClick={() => void forceCloseAndDeactivate()} type="button">{forceBusy ? "Working…" : "Force close & deactivate"}</button></div>
    </ManagerShell>;
  }

  const inactive = asset.status === "INACTIVE";
  const subtitle = subtitleForAsset(asset);
  return <ManagerShell busy={runner.busy} eyebrow={inactive ? "Reactivate asset" : "Manage asset"} onDismiss={onClose} subtitle={subtitle} title={assetLabel(asset)}>
    <InlineFeedback error={runner.error || formError} />
    <section aria-label="Asset activity" className={`owner-manager-activity ${onDuty ? "owner-manager-activity--locked" : ""}`}>
      <div><span>Activity</span><StatusChip label={inactive ? "Inactive" : onDuty ? "On duty" : "Off duty"} status={inactive ? "INACTIVE" : onDuty ? "ON_DUTY" : "AVAILABLE"} /></div>
      <dl>
        <div><dt>Driver / Operator</dt><dd>{currentDriver?.display_name || "Unassigned"}</dd></div>
        <div><dt>Site</dt><dd>{asset.current_deployment?.site_name || "Undeployed"}</dd></div>
        {onDuty && <div><dt>Duty started</dt><dd>{dateTime(dutyStartedAt)}</dd></div>}
      </dl>
      {onDuty && <div className="owner-manager-duty-lock"><p>Changes are unavailable while this duty is active.</p>{onViewActiveDuty && <button className="secondary" onClick={() => { onClose(); onViewActiveDuty(asset.id); }} type="button">VIEW ACTIVE DUTY</button>}</div>}
    </section>
    <div className="owner-dialog-form owner-manager-fields">
      <label>Driver / Operator<select aria-label="Driver / Operator" autoFocus={focus === "driver"} disabled={runner.busy || onDuty} onChange={(event) => { setDriverId(event.target.value); setActivateDriverRole(false); setDriverError(""); }} value={driverId}><option value="">No Driver / Operator</option>{driverOptions.map((driver) => <option key={driver.membership_id} value={driver.membership_id}>{driver.display_name} · {driver.membership_id === currentDriverId ? "Current" : `${title(driver.status)} · Unassigned`}</option>)}</select>{driverError && <span className="owner-field-error" role="alert">{driverError}</span>}</label>
      {selectedDriver?.status === "INACTIVE" && <label className="owner-manager-checkbox"><input checked={activateDriverRole} disabled={runner.busy || onDuty} onChange={(event) => { setActivateDriverRole(event.target.checked); setDriverError(""); }} type="checkbox" /> Include Driver / Operator role reactivation</label>}
      <label>Site<select aria-label="Site" autoFocus={focus === "site"} disabled={runner.busy || onDuty} onChange={(event) => { setSiteId(event.target.value); setSiteError(""); }} value={siteId}><option value="">Undeployed</option>{activeSites.map((site) => <option key={site.id} value={site.id}>{siteLabel(site)}</option>)}</select>{siteError && <span className="owner-field-error" role="alert">{siteError}</span>}</label>
    </div>
    <div className="owner-manager-actions">
      <div>{onViewAssetHistory && <button className="secondary" onClick={() => { onClose(); onViewAssetHistory(asset.id); }} type="button">View relationship history</button>}</div>
      <div>
        {!inactive && <button className="secondary owner-danger-button" disabled={runner.busy} onClick={() => void deactivate()} type="button">Deactivate asset</button>}
        {inactive ? <><button className="secondary" disabled={runner.busy} onClick={() => void reactivate(false)} type="button">REACTIVATE ONLY</button><button disabled={runner.busy || (!siteId && !driverId)} onClick={() => void reactivate(true)} type="button">REACTIVATE &amp; SET UP</button></> : <button autoFocus={focus === "lifecycle"} disabled={runner.busy || onDuty || (siteId === currentSiteId && driverId === currentDriverId)} onClick={() => void save()} type="button">Save changes</button>}
      </div>
    </div>
  </ManagerShell>;
}

function PersonManager(props: OwnerRelationshipManagerProps & { target: Extract<OwnerRelationshipTarget, { kind: "person" }> }) {
  const { target, assets, people, sites, onClose } = props;
  const person = people.find((item) => item.membership_id === target.membershipId);
  const [assetId, setAssetId] = useState(() => target.presetAssetId ?? person?.current_asset_id ?? "");
  const initialSelectedAsset = assets.find((asset) => asset.id === (target.presetAssetId ?? person?.current_asset_id));
  const [siteId, setSiteId] = useState(() => target.presetSiteId ?? initialSelectedAsset?.current_deployment?.site_id ?? person?.current_site_id ?? "");
  const initialSupervisorSites = person?.sites.map((site) => site.site_id) ?? [];
  const [selectedSiteIds, setSelectedSiteIds] = useState(() => target.presetSiteId && !initialSupervisorSites.includes(target.presetSiteId) ? [...initialSupervisorSites, target.presetSiteId] : initialSupervisorSites);
  const [assetError, setAssetError] = useState("");
  const [siteError, setSiteError] = useState("");
  const [formError, setFormError] = useState("");
  const runner = useOperationRunner(props);

  const selectedAsset = assets.find((asset) => asset.id === assetId);
  const activeSites = useMemo(() => sites.filter((site) => site.status === "ACTIVE"), [sites]);
  const availableAssets = useMemo(() => assets
    .filter((asset) => asset.status === "ACTIVE" && (!asset.has_active_assignment || asset.id === person?.current_asset_id))
    .sort((left, right) => assetLabel(left).localeCompare(assetLabel(right))), [assets, person?.current_asset_id]);

  const clearErrors = () => {
    setAssetError("");
    setSiteError("");
    setFormError("");
    runner.setError("");
  };

  const applyBlockedReasons = (reasons: string[]) => {
    let nextAssetError = "";
    let nextSiteError = "";
    const remaining: string[] = [];
    for (const reason of reasons) {
      const normalized = reason.toLowerCase();
      if (normalized.includes("site")) nextSiteError = appendError(nextSiteError, reason);
      else if (normalized.includes("asset") || normalized.includes("assignment") || normalized.includes("driver") || normalized.includes("operator")) nextAssetError = appendError(nextAssetError, reason);
      else remaining.push(reason);
    }
    setAssetError(nextAssetError);
    setSiteError(nextSiteError);
    setFormError(remaining.join(" "));
  };

  const prepare = async (intent: OwnerOperationIntent, confirmation?: ConfirmationCopy) => {
    clearErrors();
    const plan = await runner.preview(intent);
    if (!plan) return;
    if (!plan.can_execute) {
      applyBlockedReasons(plan.blocked_reasons.length ? plan.blocked_reasons : ["This change is not available in the current state."]);
      return;
    }
    if (confirmation) runner.confirm(intent, plan, confirmation);
    else await runner.execute(intent, plan.state_token);
  };

  const driverIntent = (activateOnly: boolean): OwnerOperationIntent | null => {
    if (!person) return null;
    if (activateOnly) return { action: "ACTIVATE_PERSON", person_membership_id: person.membership_id };
    if (!assetId || !selectedAsset) {
      setAssetError("Choose an Asset for this Driver / Operator.");
      return null;
    }
    if (person.has_active_assignment) {
      if (assetId !== person.current_asset_id) setAssetError("This Driver / Operator is already assigned. Manage the current Asset before choosing another one.");
      else setAssetError("This is already the current Asset assignment.");
      return null;
    }
    const selectedSiteId = selectedAsset.current_deployment?.site_id ?? siteId;
    if (!selectedSiteId) {
      setSiteError("Choose a Site before assigning this Driver / Operator.");
      return null;
    }
    if (person.status === "INACTIVE") {
      return { action: "ACTIVATE_PERSON", person_membership_id: person.membership_id, asset_id: selectedAsset.id, site_id: selectedSiteId, regular_duty_minutes: 600 };
    }
    return { action: "ASSIGN_DRIVER", asset_id: selectedAsset.id, driver_membership_id: person.membership_id, site_id: selectedSiteId, regular_duty_minutes: 600 };
  };

  const saveDriver = async (activateOnly = false) => {
    clearErrors();
    const intent = driverIntent(activateOnly);
    if (intent) await prepare(intent);
  };

  const saveSupervisor = async (activateOnly = false) => {
    if (!person) return;
    const intent: OwnerOperationIntent = person.status === "INACTIVE"
      ? { action: "ACTIVATE_PERSON", person_membership_id: person.membership_id, selected_site_ids: activateOnly ? [] : selectedSiteIds }
      : { action: "SET_SUPERVISOR_SITES", person_membership_id: person.membership_id, selected_site_ids: selectedSiteIds };
    await prepare(intent);
  };

  const deactivate = async () => {
    if (!person) return;
    if (person.has_active_duty) {
      setFormError("Changes are unavailable while this duty is active.");
      return;
    }
    await prepare(
      { action: "DEACTIVATE_PERSON", person_membership_id: person.membership_id },
      { title: `Deactivate ${person.display_name}'s ${personRoleLabel(person)} role?`, description: "Current off-duty relationships will end safely and historical records will remain available.", confirmLabel: "Deactivate role" },
    );
  };

  if (!person) {
    return <ManagerShell busy={false} eyebrow="Manage person" onDismiss={onClose} title="Person unavailable"><InlineFeedback error="This person is no longer available. Refresh and try again." /></ManagerShell>;
  }

  if (runner.confirmation) {
    return <ManagerShell busy={runner.busy} eyebrow="Confirm operation" onDismiss={runner.cancelConfirmation} title={runner.confirmation.title}><ConfirmationView runner={runner} /></ManagerShell>;
  }

  const inactive = person.status === "INACTIVE";
  const unsupported = person.role === "OWNER_ADMIN";
  return <ManagerShell busy={runner.busy} eyebrow={inactive ? "Reactivate person" : "Manage person"} onDismiss={onClose} subtitle={`${personRoleLabel(person)} · ${title(person.status)}`} title={person.display_name}>
    <InlineFeedback error={runner.error || formError} />
    <section aria-label="Person activity" className={`owner-manager-activity ${person.has_active_duty ? "owner-manager-activity--locked" : ""}`}>
      <div><span>Status</span><StatusChip label={person.has_active_duty ? "On duty" : person.has_active_assignment ? "Assigned · off duty" : title(person.status)} status={person.has_active_duty ? "ON_DUTY" : person.has_active_assignment ? "ASSIGNED" : person.status} /></div>
      <dl><div><dt>Role</dt><dd>{personRoleLabel(person)}</dd></div>{person.role === "DRIVER" && <><div><dt>Asset</dt><dd>{selectedAsset ? assetLabel(selectedAsset) : "Unassigned"}</dd></div><div><dt>Site</dt><dd>{selectedAsset?.current_deployment?.site_name || person.current_site_name || "Undeployed"}</dd></div></>}</dl>
      {person.has_active_duty && <p className="owner-manager-lock-message">Changes are unavailable while this duty is active.</p>}
    </section>
    {unsupported ? <InlineFeedback error="Owner roles are managed separately." /> : person.role === "SUPERVISOR" ? <fieldset className="owner-check-grid owner-manager-site-access"><legend>Site access</legend>{activeSites.map((site) => <label key={site.id}><input checked={selectedSiteIds.includes(site.id)} disabled={runner.busy} onChange={() => { setSelectedSiteIds((current) => current.includes(site.id) ? current.filter((id) => id !== site.id) : [...current, site.id]); setSiteError(""); }} type="checkbox" /> {siteLabel(site)}</label>)}{activeSites.length === 0 && <p>No active Sites are available.</p>}{siteError && <span className="owner-field-error" role="alert">{siteError}</span>}</fieldset> : <div className="owner-dialog-form owner-manager-fields">
      <label>Asset<select aria-label="Asset" disabled={runner.busy || person.has_active_duty || person.has_active_assignment} onChange={(event) => { const nextAsset = assets.find((asset) => asset.id === event.target.value); setAssetId(event.target.value); setSiteId(nextAsset?.current_deployment?.site_id ?? ""); setAssetError(""); setSiteError(""); }} value={assetId}><option value="">Select Asset…</option>{availableAssets.map((asset) => <option key={asset.id} value={asset.id}>{assetLabel(asset)} · {asset.current_deployment?.site_name || "Undeployed"}</option>)}</select>{assetError && <span className="owner-field-error" role="alert">{assetError}</span>}</label>
      {selectedAsset?.current_deployment ? <div className="owner-manager-derived-field"><span>Site</span><strong>{selectedAsset.current_deployment.site_name}</strong><small>Derived from Asset</small></div> : selectedAsset ? <label>Site<select aria-label="Assignment Site" disabled={runner.busy || person.has_active_duty} onChange={(event) => { setSiteId(event.target.value); setSiteError(""); }} value={siteId}><option value="">Select Site…</option>{activeSites.map((site) => <option key={site.id} value={site.id}>{siteLabel(site)}</option>)}</select>{siteError && <span className="owner-field-error" role="alert">{siteError}</span>}</label> : null}
    </div>}
    {!unsupported && <div className="owner-manager-actions"><div /><div>
      {!inactive && <button className="secondary owner-danger-button" disabled={runner.busy || person.has_active_duty} onClick={() => void deactivate()} type="button">Deactivate role</button>}
      {inactive ? <><button className="secondary" disabled={runner.busy} onClick={() => void (person.role === "SUPERVISOR" ? saveSupervisor(true) : saveDriver(true))} type="button">REACTIVATE ONLY</button><button disabled={runner.busy || person.has_active_duty || (person.role === "DRIVER" && !assetId)} onClick={() => void (person.role === "SUPERVISOR" ? saveSupervisor(false) : saveDriver(false))} type="button">{person.role === "SUPERVISOR" ? "REACTIVATE & SET UP" : "REACTIVATE & ASSIGN"}</button></> : person.role === "SUPERVISOR" ? <button disabled={runner.busy} onClick={() => void saveSupervisor(false)} type="button">Save access</button> : <button disabled={runner.busy || person.has_active_duty || person.has_active_assignment || !assetId} onClick={() => void saveDriver(false)} type="button">Save</button>}
    </div></div>}
  </ManagerShell>;
}

export function OwnerRelationshipManager(props: OwnerRelationshipManagerProps) {
  if (!props.target) return null;
  const key = JSON.stringify(props.target);
  return props.target.kind === "asset"
    ? <AssetManager {...props} key={key} target={props.target} />
    : <PersonManager {...props} key={key} target={props.target} />;
}
