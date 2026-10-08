"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  OwnerAsset,
  OwnerOperationAssetResolution,
  OwnerOperationIntent,
  OwnerOperationPlan,
  OwnerOperationResult,
  OwnerPerson,
  OwnerSite,
} from "../../lib/types";
import { ApiError } from "../../lib/api/client";
import { title } from "./catalogs";
import { InlineFeedback, StatusChip } from "./OwnerUi";

type WebRequest = <T>(path: string, options?: RequestInit) => Promise<T>;

type Props = {
  open: boolean;
  initialIntent: OwnerOperationIntent | null;
  assets: OwnerAsset[];
  people: OwnerPerson[];
  sites: OwnerSite[];
  apiRequest: WebRequest;
  onClose: () => void;
  onComplete: () => Promise<void>;
  onViewAssignments?: () => void;
};

type Step = 1 | 2 | 3 | 4;

type PreviewFailure = {
  kind: "server-update" | "missing-record" | "request";
  message: string;
};

const SERVER_UPDATE_MESSAGE = "This management action is not supported by the currently running Fleet Manager server. Update the Fleet Manager server and try again.";
const MISSING_RECORD_MESSAGE = "This record no longer exists or its state changed. Refresh and try again.";

function classifyPreviewFailure(caught: unknown): PreviewFailure {
  if (caught instanceof ApiError && caught.status === 404) {
    if (caught.code === "NOT_FOUND") {
      return { kind: "missing-record", message: MISSING_RECORD_MESSAGE };
    }
    const normalized = caught.message.trim().toLowerCase();
    if (!caught.code && !caught.context && (normalized === "not found" || normalized === "404 not found")) {
      return { kind: "server-update", message: SERVER_UPDATE_MESSAGE };
    }
    return { kind: "missing-record", message: MISSING_RECORD_MESSAGE };
  }
  return {
    kind: "request",
    message: caught instanceof Error ? caught.message : "Could not review this operation.",
  };
}

function assetLabel(asset: OwnerAsset) {
  return asset.short_name || asset.registration_number || asset.asset_code;
}

function siteLabel(site: OwnerSite) {
  return site.short_name || site.name;
}

function businessTitle(value: string) {
  return value.toLowerCase().replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function operationLabel(action: OwnerOperationIntent["action"]) {
  const labels: Record<OwnerOperationIntent["action"], string> = {
    ACTIVATE_PERSON: "Activate person",
    SET_SUPERVISOR_SITES: "Manage Site access",
    DEACTIVATE_PERSON: "Deactivate person",
    DEPLOY_ASSET: "Deploy asset",
    MOVE_DEPLOYMENT: "Move asset",
    REMOVE_DEPLOYMENT: "Remove asset from Site",
    ASSIGN_DRIVER: "Assign Driver / Operator",
    REASSIGN_DRIVER: "Change Driver / Operator",
    END_ASSIGNMENT: "End assignment",
    DEACTIVATE_ASSET: "Deactivate asset",
  FORCE_CLOSE_DUTY_AND_DEACTIVATE_ASSET: "Force close duty and deactivate asset",
    REACTIVATE_ASSET: "Reactivate asset",
    DEACTIVATE_SITE: "Deactivate Site",
    REACTIVATE_SITE: "Reactivate Site",
  };
  return labels[action];
}

function hasChoices(action: OwnerOperationIntent["action"]) {
  return new Set([
    "ACTIVATE_PERSON",
    "SET_SUPERVISOR_SITES",
    "DEPLOY_ASSET",
    "MOVE_DEPLOYMENT",
    "ASSIGN_DRIVER",
    "REASSIGN_DRIVER",
    "REACTIVATE_ASSET",
    "DEACTIVATE_SITE",
    "REACTIVATE_SITE",
  ]).has(action);
}

function operationButtonLabel(intent: OwnerOperationIntent, driver?: OwnerPerson) {
  if (intent.action === "REACTIVATE_ASSET") {
    return intent.site_id || intent.driver_membership_id ? "REACTIVATE & SET UP" : "REACTIVATE";
  }
  if ((intent.action === "ASSIGN_DRIVER" || intent.action === "REASSIGN_DRIVER") && driver?.status === "INACTIVE" && intent.activate_membership) {
    return "REACTIVATE & ASSIGN";
  }
  if (intent.action === "ACTIVATE_PERSON" && driver?.role === "DRIVER") {
    return intent.asset_id ? "REACTIVATE & ASSIGN" : "REACTIVATE";
  }
  if (intent.action === "ASSIGN_DRIVER") return "ASSIGN";
  return operationLabel(intent.action);
}

function wizardTitle(plan: OwnerOperationPlan | null, intent: OwnerOperationIntent, person?: OwnerPerson) {
  if (intent.action === "ACTIVATE_PERSON" && person?.role === "DRIVER") {
    return intent.asset_id ? `Assign ${person.display_name}` : `Reactivate ${person.display_name}`;
  }
  return plan?.title || operationLabel(intent.action);
}

type BodyProps = Omit<Props, "open" | "initialIntent"> & {
  initialIntent: OwnerOperationIntent;
};

function OwnerRelationshipWizardBody({
  initialIntent,
  assets,
  people,
  sites,
  apiRequest,
  onClose,
  onComplete,
  onViewAssignments,
}: BodyProps) {
  const [step, setStep] = useState<Step>(1);
  const [intent, setIntent] = useState<OwnerOperationIntent>(initialIntent);
  const [plan, setPlan] = useState<OwnerOperationPlan | null>(null);
  const [result, setResult] = useState<OwnerOperationResult | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [previewFailure, setPreviewFailure] = useState<PreviewFailure | null>(null);

  const activeSites = useMemo(
    () => sites.filter((site) => site.status === "ACTIVE"),
    [sites],
  );
  const activeAssets = useMemo(
    () => assets.filter((asset) => asset.status === "ACTIVE" && !asset.has_active_assignment),
    [assets],
  );
  const drivers = useMemo(
    () => people.filter((person) => person.role === "DRIVER"),
    [people],
  );
  const supervisors = useMemo(
    () => people.filter((person) => person.role === "SUPERVISOR" && person.status === "ACTIVE"),
    [people],
  );
  const selectedAsset = assets.find((asset) => asset.id === intent.asset_id);
  const selectedPerson = people.find((person) => person.membership_id === intent.person_membership_id);
  const selectedDriver = drivers.find((driver) => driver.membership_id === intent.driver_membership_id);
  const operationDriver = selectedDriver ?? (selectedPerson?.role === "DRIVER" ? selectedPerson : undefined);
  const structuredReview = intent.action === "REACTIVATE_ASSET" || intent.action === "ASSIGN_DRIVER" || (intent.action === "ACTIVATE_PERSON" && selectedPerson?.role === "DRIVER");

  const loadPreview = useCallback(async (nextIntent: OwnerOperationIntent) => {
    setBusy(true);
    setError("");
    setPreviewFailure(null);
    setPlan(null);
    try {
      const nextPlan = await apiRequest<OwnerOperationPlan>("/api/v1/owner/operations/preview", {
        method: "POST",
        body: JSON.stringify(nextIntent),
      });
      setPlan(nextPlan);
      return nextPlan;
    } catch (caught) {
      setPreviewFailure(classifyPreviewFailure(caught));
      return null;
    } finally {
      setBusy(false);
    }
  }, [apiRequest]);

  useEffect(() => {
    let cancelled = false;
    const refreshPreview = async () => {
      await Promise.resolve();
      if (cancelled) return;
      setBusy(true);
      setError("");
      setPreviewFailure(null);
      setPlan(null);
      try {
        const nextPlan = await apiRequest<OwnerOperationPlan>("/api/v1/owner/operations/preview", {
          method: "POST",
          body: JSON.stringify(initialIntent),
        });
        if (!cancelled) setPlan(nextPlan);
      } catch (caught) {
        if (!cancelled) setPreviewFailure(classifyPreviewFailure(caught));
      } finally {
        if (!cancelled) setBusy(false);
      }
    };
    void refreshPreview();
    return () => { cancelled = true; };
  }, [apiRequest, initialIntent]);

  useEffect(() => {
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onClose();
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [busy, onClose]);

  const review = async () => {
    const nextPlan = await loadPreview(intent);
    if (nextPlan) setStep(3);
    else setStep(1);
  };

  const execute = async () => {
    if (!plan?.can_execute) return;
    setBusy(true);
    setError("");
    try {
      const completed = await apiRequest<OwnerOperationResult>(
        "/api/v1/owner/operations/execute",
        {
          method: "POST",
          body: JSON.stringify({ ...intent, state_token: plan.state_token }),
        },
      );
      setResult(completed);
      await onComplete();
      setStep(4);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The operation failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="owner-dialog-backdrop" role="presentation">
      <section
        aria-labelledby="owner-operation-title"
        aria-modal="true"
        className="owner-dialog owner-dialog--wide owner-operation-wizard"
        role="dialog"
      >
        <div className="owner-dialog-heading">
          <div>
            <p className="owner-section-eyebrow">Relationship operation</p>
            <h2 id="owner-operation-title">{wizardTitle(plan, intent, selectedPerson)}</h2>
          </div>
          <button aria-label="Close operation" className="owner-icon-button" disabled={busy} onClick={onClose} type="button">×</button>
        </div>
        <ol aria-label="Operation progress" className="owner-wizard-steps">
          {["Current state", "Choose changes", "Review", "Result"].map((label, index) => (
            <li aria-current={step === index + 1 ? "step" : undefined} className={step >= index + 1 ? "is-active" : ""} key={label}><span>{index + 1}</span>{label}</li>
          ))}
        </ol>
        <InlineFeedback error={previewFailure?.kind === "request" ? previewFailure.message : error} />
        {previewFailure && previewFailure.kind !== "request" && (
          <div className="owner-blocker" role="alert">
            <strong>{previewFailure.kind === "server-update" ? "Server update required" : "Record unavailable"}</strong>
            <p>{previewFailure.message}</p>
          </div>
        )}
        {busy && !plan ? <div aria-busy="true" className="owner-skeleton-list"><span /><span /><span /></div> : null}

        {step === 1 && plan && (
          <div className="owner-wizard-body">
            <p>{plan.summary}</p>
            {intent.action === "REACTIVATE_ASSET" && selectedAsset ? <ReactivateAssetState asset={selectedAsset} plan={plan} /> : <>
              <OperationItems heading="Current state" items={plan.current_state} />
              <OperationItems heading="Active relationships" items={plan.dependencies} />
              {plan.dependencies.length === 0 && <p className="owner-dim">No dependent relationships.</p>}
            </>}
          </div>
        )}

        {step === 2 && (
          <div className="owner-wizard-body">
            <h3>Choose changes</h3>
            <OperationChoices
              activeAssets={activeAssets}
              activeSites={activeSites}
              assets={assets}
              drivers={drivers}
              intent={intent}
              people={people}
              plan={plan}
              setIntent={setIntent}
              supervisors={supervisors}
            />
          </div>
        )}

        {step === 3 && plan && (
          <div className="owner-wizard-body">
            <h3>{structuredReview ? "Review setup" : "Review"}</h3>
            {structuredReview ? <FinalStateReview assets={assets} intent={intent} people={people} sites={sites} /> : plan.planned_changes.length > 0 && <ol className="owner-change-list">{plan.planned_changes.map((change) => <li key={change}>{change}</li>)}</ol>}
            {error.toLowerCase().includes("state changed") && <button className="secondary" disabled={busy} onClick={() => void review()} type="button">Review again</button>}
            {plan.blocked_reasons.length > 0 && <div className="owner-blocker" role="alert"><strong>This operation cannot continue yet.</strong><ul>{plan.blocked_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>{onViewAssignments && plan.blocked_reasons.some((reason) => reason.toLowerCase().includes("duty")) && <button className="secondary" onClick={() => { onClose(); onViewAssignments(); }} type="button">View active assignment / duty</button>}</div>}
            {plan.warnings.length > 0 && <ul>{plan.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>}
          </div>
        )}

        {step === 4 && result && (
          <div className="owner-wizard-body owner-operation-result" role="status">
            <StatusChip label="Completed" status="ACTIVE" />
            <h3>{result.message}</h3>
            <ol className="owner-change-list">{result.completed_changes.map((change) => <li key={change}>{change}</li>)}</ol>
          </div>
        )}

        <div className="owner-dialog-actions">
          {previewFailure ? <><button className="secondary" disabled={busy} onClick={onClose} type="button">Close</button><button disabled={busy} onClick={() => void loadPreview(intent)} type="button">Retry</button></> : <>
            {step === 1 && <><button className="secondary" disabled={busy} onClick={onClose} type="button">Cancel</button><button disabled={busy || !plan} onClick={() => setStep(hasChoices(intent.action) ? 2 : 3)} type="button">Continue</button></>}
            {step === 2 && <><button className="secondary" disabled={busy} onClick={() => setStep(1)} type="button">Back</button><button disabled={busy} onClick={() => void review()} type="button">Review changes</button></>}
            {step === 3 && <><button className="secondary" disabled={busy} onClick={() => setStep(hasChoices(intent.action) ? 2 : 1)} type="button">Back</button><button disabled={busy || !plan?.can_execute} onClick={() => void execute()} type="button">{busy ? "Working…" : operationButtonLabel(intent, operationDriver)}</button></>}
            {step === 4 && <button onClick={onClose} type="button">Done</button>}
          </>}
        </div>
      </section>
    </div>
  );
}

export function OwnerRelationshipWizard(props: Props) {
  if (!props.open || !props.initialIntent) return null;
  const key = JSON.stringify(props.initialIntent);
  return <OwnerRelationshipWizardBody {...props} initialIntent={props.initialIntent} key={key} />;
}

function OperationItems({ heading, items }: { heading: string; items: OwnerOperationPlan["dependencies"] }) {
  if (items.length === 0) return null;
  return <section><h3>{heading}</h3><div className="owner-operation-items">{items.map((item) => <article key={`${item.kind}-${item.id}`}><div><strong>{item.label}</strong><small>{title(item.kind)}</small></div><StatusChip status={item.status} /></article>)}</div></section>;
}

function ReactivateAssetState({ asset, plan }: { asset: OwnerAsset; plan: OwnerOperationPlan }) {
  const previousRelationships = [...plan.current_state, ...plan.dependencies].filter((item) => item.kind === "PREVIOUS_SITE" || item.kind === "PREVIOUS_DRIVER");
  return <>
    <section aria-label="Asset current state">
      <h3>Current state</h3>
      <dl className="owner-detail-list">
        <div><dt>Asset</dt><dd>{assetLabel(asset)}</dd></div>
        <div><dt>Registration</dt><dd>{asset.registration_number || "Not applicable"}</dd></div>
        <div><dt>Type</dt><dd>{businessTitle(asset.asset_type)}</dd></div>
        <div><dt>Ownership</dt><dd>{businessTitle(asset.ownership_type)}</dd></div>
        <div><dt>Lifecycle</dt><dd>{businessTitle(asset.status)}</dd></div>
      </dl>
    </section>
    <OperationItems heading="Previous relationships" items={previousRelationships} />
  </>;
}

function FinalStateReview({
  intent,
  assets,
  people,
  sites,
}: {
  intent: OwnerOperationIntent;
  assets: OwnerAsset[];
  people: OwnerPerson[];
  sites: OwnerSite[];
}) {
  const asset = assets.find((item) => item.id === intent.asset_id);
  const driver = people.find((item) => item.membership_id === (intent.driver_membership_id || intent.person_membership_id));
  const siteId = intent.site_id || asset?.current_deployment?.site_id;
  const site = sites.find((item) => item.id === siteId);
  const reactivateRole = intent.action === "ACTIVATE_PERSON" || (driver?.status === "INACTIVE" && intent.activate_membership);

  if (intent.action === "REACTIVATE_ASSET") {
    return <dl aria-label="Final setup" className="owner-detail-list" role="group">
      <div><dt>Asset</dt><dd>{asset ? assetLabel(asset) : "Selected asset"} → Active</dd></div>
      <div><dt>Site</dt><dd>{site ? siteLabel(site) : "Leave undeployed"}</dd></div>
      <div><dt>Driver / Operator</dt><dd>{driver?.display_name || "Leave unassigned"}</dd></div>
      {reactivateRole && <div><dt>Role</dt><dd>Driver / Operator → Reactivate</dd></div>}
    </dl>;
  }

  return <dl aria-label="Final assignment" className="owner-detail-list" role="group">
    <div><dt>Person</dt><dd>{driver?.display_name || "Choose a Driver / Operator"}</dd></div>
    <div><dt>Role</dt><dd>{reactivateRole ? "Driver / Operator → Reactivate" : "Driver / Operator"}</dd></div>
    <div><dt>Asset</dt><dd>{asset ? `${assetLabel(asset)} · ${businessTitle(asset.asset_type)}` : intent.action === "ACTIVATE_PERSON" ? "Leave unassigned" : "Choose an asset"}</dd></div>
    <div><dt>Site</dt><dd>{site ? siteLabel(site) : intent.action === "ACTIVATE_PERSON" ? "No Site setup" : "Choose a Site"}</dd></div>
  </dl>;
}

function InactiveDriverRoleChoice({
  checked,
  context,
  onChange,
}: {
  checked: boolean;
  context: "assignment" | "setup";
  onChange: (checked: boolean) => void;
}) {
  return <fieldset>
    <legend>Role</legend>
    <p><strong>Driver / Operator</strong><br /><span className="owner-dim">Currently inactive</span></p>
    <label><input checked={checked} onChange={(event) => onChange(event.target.checked)} type="checkbox" /> Reactivate role as part of this {context}</label>
  </fieldset>;
}

function OperationChoices({
  intent,
  plan,
  assets,
  activeAssets,
  people,
  drivers,
  supervisors,
  activeSites,
  setIntent,
}: {
  intent: OwnerOperationIntent;
  plan: OwnerOperationPlan | null;
  assets: OwnerAsset[];
  activeAssets: OwnerAsset[];
  people: OwnerPerson[];
  drivers: OwnerPerson[];
  supervisors: OwnerPerson[];
  activeSites: OwnerSite[];
  setIntent: (intent: OwnerOperationIntent) => void;
}) {
  const person = people.find((item) => item.membership_id === intent.person_membership_id);
  const selectedAsset = assets.find((item) => item.id === intent.asset_id);
  const selectedDriver = drivers.find((item) => item.membership_id === intent.driver_membership_id);
  const assignmentDependency = plan?.dependencies.find((item) => item.kind === "ASSIGNMENT");
  const eligibleDrivers = [...drivers.filter((driver) => !driver.has_active_assignment)].sort((left, right) => {
    const statusOrder = { ACTIVE: 0, INVITED: 1, INACTIVE: 2 } as const;
    return statusOrder[left.status] - statusOrder[right.status] || left.display_name.localeCompare(right.display_name);
  });

  const toggleId = (field: "selected_site_ids" | "selected_supervisor_ids" | "selected_asset_ids", id: string) => {
    const current = new Set(intent[field] ?? []);
    if (current.has(id)) current.delete(id); else current.add(id);
    setIntent({ ...intent, [field]: [...current] });
  };

  const updateResolution = (assetId: string, change: Partial<OwnerOperationAssetResolution>) => {
    const current = intent.asset_resolutions ?? [];
    const existing = current.find((item) => item.asset_id === assetId);
    const next: OwnerOperationAssetResolution = {
      asset_id: assetId,
      action: existing?.action ?? "REMOVE",
      target_site_id: existing?.target_site_id ?? null,
      assignment_action: existing?.assignment_action ?? null,
      ...change,
    };
    setIntent({ ...intent, asset_resolutions: [...current.filter((item) => item.asset_id !== assetId), next] });
  };

  if (intent.action === "REACTIVATE_ASSET") {
    return <div className="owner-dialog-form">
      <fieldset><legend>Asset</legend><label><input checked readOnly type="checkbox" /> Reactivate asset</label></fieldset>
      <label>Site<select aria-label="Reactivation Site" onChange={(event) => setIntent({ ...intent, site_id: event.target.value || null })} value={intent.site_id ?? ""}><option value="">Leave undeployed</option>{activeSites.map((site) => <option key={site.id} value={site.id}>{siteLabel(site)}</option>)}</select></label>
      <label>Driver / Operator<select aria-label="Reactivation Driver / Operator" onChange={(event) => setIntent({ ...intent, driver_membership_id: event.target.value || null, activate_membership: false })} value={intent.driver_membership_id ?? ""}><option value="">Leave unassigned</option>{eligibleDrivers.map((driver) => <option key={driver.membership_id} value={driver.membership_id}>{driver.display_name} · Driver / Operator · {businessTitle(driver.status)} · Unassigned</option>)}</select></label>
      {intent.driver_membership_id && !intent.site_id && <p role="note">Choose a Site before assigning a Driver / Operator.</p>}
      {selectedDriver?.status === "INACTIVE" && <InactiveDriverRoleChoice checked={intent.activate_membership ?? false} context="setup" onChange={(checked) => setIntent({ ...intent, activate_membership: checked })} />}
    </div>;
  }

  if (intent.action === "MOVE_DEPLOYMENT") {
    return <div className="owner-dialog-form"><label>Destination Site<select aria-label="Destination Site" onChange={(event) => setIntent({ ...intent, target_site_id: event.target.value || null })} value={intent.target_site_id ?? ""}><option value="">Choose destination…</option>{activeSites.filter((site) => site.id !== selectedAsset?.current_deployment?.site_id).map((site) => <option key={site.id} value={site.id}>{siteLabel(site)}</option>)}</select></label>{assignmentDependency && <fieldset><legend>Current Driver / Operator</legend><label><input checked={intent.assignment_action === "KEEP"} name="assignment-action" onChange={() => setIntent({ ...intent, assignment_action: "KEEP" })} type="radio" /> Keep current Driver / Operator</label><label><input checked={intent.assignment_action === "END"} name="assignment-action" onChange={() => setIntent({ ...intent, assignment_action: "END" })} type="radio" /> End assignment</label></fieldset>}</div>;
  }

  if (intent.action === "DEACTIVATE_SITE") {
    const deployed = plan?.dependencies.filter((item) => item.kind === "DEPLOYED_ASSET") ?? [];
    return <div className="owner-resolution-list">{deployed.length === 0 ? <p>No deployed assets require a decision.</p> : deployed.map((item) => { const resolution = intent.asset_resolutions?.find((value) => value.asset_id === item.details.asset_id); const assetId = String(item.details.asset_id); return <fieldset key={item.id}><legend>{item.label} · {title(item.status)}</legend><label>Resolution<select aria-label={`Resolution for ${item.label}`} onChange={(event) => updateResolution(assetId, { action: event.target.value as "MOVE" | "REMOVE", target_site_id: null, assignment_action: null })} value={resolution?.action ?? ""}><option value="">Choose…</option><option value="REMOVE">Remove from Site</option><option value="MOVE">Move to another Site</option></select></label>{resolution?.action === "MOVE" && <label>Destination Site<select aria-label={`Destination for ${item.label}`} onChange={(event) => updateResolution(assetId, { target_site_id: event.target.value || null })} value={resolution.target_site_id ?? ""}><option value="">Choose destination…</option>{activeSites.filter((site) => site.id !== intent.site_id).map((site) => <option key={site.id} value={site.id}>{siteLabel(site)}</option>)}</select></label>}{resolution?.action === "MOVE" && item.status === "OFF_DUTY" && <label>Driver / Operator<select aria-label={`Assignment for ${item.label}`} onChange={(event) => updateResolution(assetId, { assignment_action: event.target.value as "KEEP" | "END" })} value={resolution.assignment_action ?? ""}><option value="">Choose…</option><option value="KEEP">Keep Driver / Operator</option><option value="END">End assignment</option></select></label>}</fieldset>; })}</div>;
  }

  if (intent.action === "SET_SUPERVISOR_SITES" || (intent.action === "ACTIVATE_PERSON" && person?.role === "SUPERVISOR")) {
    return <fieldset className="owner-check-grid"><legend>Supervisor Site access</legend>{activeSites.map((site) => <label key={site.id}><input checked={(intent.selected_site_ids ?? []).includes(site.id)} onChange={() => toggleId("selected_site_ids", site.id)} type="checkbox" /> {siteLabel(site)}</label>)}{activeSites.length === 0 && <p>No active Sites are available.</p>}</fieldset>;
  }

  if (intent.action === "ASSIGN_DRIVER" || (intent.action === "ACTIVATE_PERSON" && person?.role === "DRIVER")) {
    return <div className="owner-dialog-form">{intent.action === "ASSIGN_DRIVER" && !intent.driver_membership_id && <label>Driver / Operator<select aria-label="Wizard Driver / Operator" onChange={(event) => setIntent({ ...intent, driver_membership_id: event.target.value || null, activate_membership: false })} value={intent.driver_membership_id ?? ""}><option value="">Choose person…</option>{eligibleDrivers.map((driver) => <option key={driver.membership_id} value={driver.membership_id}>{driver.display_name} · {driver.status}</option>)}</select></label>}{intent.action === "ACTIVATE_PERSON" && person?.status === "INACTIVE" && <fieldset><legend>Role</legend><p><strong>Driver / Operator</strong><br /><span className="owner-dim">Currently inactive</span></p><label><input aria-readonly="true" checked readOnly type="checkbox" /> Reactivate role as part of this assignment</label></fieldset>}{!intent.asset_id && <label>Asset<select aria-label="Wizard asset" onChange={(event) => setIntent({ ...intent, asset_id: event.target.value || null, site_id: null })} value={intent.asset_id ?? ""}><option value="">Choose available asset…</option>{activeAssets.map((asset) => <option key={asset.id} value={asset.id}>{assetLabel(asset)} · {asset.current_deployment?.site_name || "Undeployed"}</option>)}</select></label>}{selectedAsset && !selectedAsset.current_deployment && <label>Deploy to<select aria-label="Deploy assignment asset to" onChange={(event) => setIntent({ ...intent, site_id: event.target.value || null })} value={intent.site_id ?? ""}><option value="">Choose Site…</option>{activeSites.map((site) => <option key={site.id} value={site.id}>{siteLabel(site)}</option>)}</select></label>}{selectedAsset?.current_deployment && <p><strong>Site:</strong> {selectedAsset.current_deployment.site_name} (derived from deployment)</p>}{intent.action === "ASSIGN_DRIVER" && selectedDriver?.status === "INACTIVE" && <InactiveDriverRoleChoice checked={intent.activate_membership ?? false} context="assignment" onChange={(checked) => setIntent({ ...intent, activate_membership: checked })} />}</div>;
  }

  if (intent.action === "REASSIGN_DRIVER") {
    const currentDriverId = assignmentDependency?.details.driver_membership_id;
    return <div className="owner-dialog-form"><label>New Driver / Operator<select aria-label="Replacement Driver / Operator" onChange={(event) => setIntent({ ...intent, driver_membership_id: event.target.value || null, activate_membership: false })} value={intent.driver_membership_id ?? ""}><option value="">Choose available person…</option>{eligibleDrivers.filter((driver) => driver.membership_id !== currentDriverId).map((driver) => <option key={driver.membership_id} value={driver.membership_id}>{driver.display_name} · {driver.status}</option>)}</select></label>{selectedDriver?.status === "INACTIVE" && <InactiveDriverRoleChoice checked={intent.activate_membership ?? false} context="assignment" onChange={(checked) => setIntent({ ...intent, activate_membership: checked })} />}</div>;
  }

  if (intent.action === "DEPLOY_ASSET") {
    return <label>Destination Site<select aria-label="Wizard destination Site" onChange={(event) => setIntent({ ...intent, site_id: event.target.value || null })} value={intent.site_id ?? ""}><option value="">Choose Site…</option>{activeSites.map((site) => <option key={site.id} value={site.id}>{siteLabel(site)}</option>)}</select></label>;
  }

  if (intent.action === "REACTIVATE_SITE") {
    return <div className="owner-dialog-form"><fieldset className="owner-check-grid"><legend>Optional Supervisor access</legend>{supervisors.map((supervisor) => <label key={supervisor.membership_id}><input checked={(intent.selected_supervisor_ids ?? []).includes(supervisor.membership_id)} onChange={() => toggleId("selected_supervisor_ids", supervisor.membership_id)} type="checkbox" /> {supervisor.display_name}</label>)}</fieldset><fieldset className="owner-check-grid"><legend>Optional undeployed assets</legend>{activeAssets.filter((asset) => !asset.current_deployment).map((asset) => <label key={asset.id}><input checked={(intent.selected_asset_ids ?? []).includes(asset.id)} onChange={() => toggleId("selected_asset_ids", asset.id)} type="checkbox" /> {assetLabel(asset)}</label>)}</fieldset></div>;
  }

  return <p>No additional choices are required. Continue to review.</p>;
}
