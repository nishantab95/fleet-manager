import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

import { assetTypes, workflowSteps } from "../components/content";
import { CtaBand, MarketingIcon, SectionHeading } from "../components/MarketingUi";

export const metadata: Metadata = {
  title: "Clearer construction fleet operations | Fleet AI Systems",
  description: "One operational system for construction fleet Owners, Drivers, Operators, and Supervisors—from field capture to maintenance and reports.",
  alternates: { canonical: "/" },
};

const valueStrip = [
  ["01", "Fleet visibility", "Know where assets, people, and work stand."],
  ["02", "Field workflows", "Keep capture simple for Drivers and Operators."],
  ["03", "Supervisor review", "Turn field events into verified records."],
  ["04", "Maintenance readiness", "See due work before it stops the shift."],
  ["05", "Reporting", "Export operational records without rebuilding the day."],
] as const;

const featureCards = [
  { icon: "asset", label: "Owner operations", title: "One command view for the working fleet", copy: "Manage sites, assets, people, deployments, assignments, and operational exceptions from one structured workspace.", tone: "teal" },
  { icon: "mobile", label: "Driver mobile", title: "Fast field capture, even when signal is not", copy: "Duty, trip, diesel, emergency, and meter workflows stay focused and queue safely when connectivity drops.", tone: "steel" },
  { icon: "review", label: "Supervisor control", title: "Review the evidence, not a chain of phone calls", copy: "Site-scoped review brings pending trips, readings, diesel, emergencies, and maintenance proof into one flow.", tone: "amber" },
  { icon: "maintenance", label: "Maintenance", title: "Make service readiness part of daily operations", copy: "Plan intervals, submit proof, preserve history, and keep current-company responsibility clear for owned and rented assets.", tone: "green" },
  { icon: "download", label: "Reports + Excel", title: "Operational records that leave the screen cleanly", copy: "Generate site- and asset-level reports and practical workbook exports without rebuilding the day by hand.", tone: "slate" },
  { icon: "shield", label: "Role-based operations", title: "The right view for each person", copy: "Owner, Supervisor, and Driver access stays company-scoped, assignment-aware, and backed by server-side authorization.", tone: "dark" },
] as const;

const outcomes = [
  ["Fewer", "coordination calls", "because assignments and readiness are visible"],
  ["Faster", "field review", "because evidence arrives with the event"],
  ["Cleaner", "daily closure", "because missing work becomes explicit"],
  ["Stronger", "maintenance readiness", "because service history stays connected"],
] as const;

export default function MarketingHomePage() {
  return <main id="main-content">
    <section className="marketing-hero">
      <div className="marketing-hero__grid" aria-hidden="true" />
      <div className="marketing-orb marketing-orb--hero-one" />
      <div className="marketing-orb marketing-orb--hero-two" />
      <div className="marketing-container marketing-hero__inner">
        <div className="marketing-hero__copy marketing-reveal">
          <span className="marketing-pill"><i /> Built for tippers, machinery, and the people running them</span>
          <h1>Run the field.<br /><em>Read the fleet.</em></h1>
          <p>Fleet AI Systems connects Owner control, mobile field capture, Supervisor review, maintenance, and reporting—without adding more operational noise.</p>
          <div className="marketing-hero__actions"><Link className="marketing-link-button marketing-link-button--amber" href="/contact">Book a working session <span aria-hidden="true">↗</span></Link><Link className="marketing-text-link marketing-text-link--light" href="/how-it-works">See the workflow <span aria-hidden="true">→</span></Link></div>
          <div className="marketing-hero__proof"><div><strong>Offline-first</strong><span>Field capture</span></div><div><strong>Role-based</strong><span>Operational control</span></div><div><strong>Evidence-backed</strong><span>Review + history</span></div></div>
        </div>
        <div className="marketing-hero__visual marketing-reveal marketing-reveal--delay">
          <div className="marketing-hero__halo" />
          <div className="marketing-hero-product">
            <span>ACTUAL PRODUCT · REPRESENTATIVE DATA</span>
            <div className="marketing-product-screenshot"><div className="marketing-product-screenshot__bar"><i/><i/><i/><span>Fleet AI Systems · Owner operations</span></div><Image alt="Fleet AI Systems Owner operations dashboard" height={800} priority sizes="(max-width: 900px) 92vw, 650px" src="/product/owner-operations.png" width={1280}/></div>
          </div>
          <div className="marketing-float-card marketing-float-card--sync"><span className="marketing-float-card__icon"><MarketingIcon name="asset" /></span><div><small>EXAMPLE LIVE VIEW</small><strong>24 assets active</strong></div><i>DEMO</i></div>
          <div className="marketing-float-card marketing-float-card--asset"><span className="marketing-float-card__icon marketing-float-card__icon--amber"><MarketingIcon name="maintenance" /></span><div><small>EXAMPLE STATUS</small><strong>3 services due</strong></div></div>
        </div>
      </div>
      <div className="marketing-hero__edge" aria-hidden="true" />
    </section>

    <section className="marketing-value-strip" aria-label="Platform value">
      <div className="marketing-container marketing-value-strip__grid">{valueStrip.map(([number, title, copy]) => <article key={number}><span>{number}</span><div><strong>{title}</strong><p>{copy}</p></div></article>)}</div>
    </section>

    <section className="marketing-section marketing-features-intro">
      <div className="marketing-container">
        <SectionHeading eyebrow="One operational system" title="The day moves through one connected workflow." copy="Fleet work rarely happens at a desk. The platform keeps each role focused while preserving one trustworthy operational record." />
        <div className="marketing-feature-grid">{featureCards.map((feature) => <article className={`marketing-feature-card marketing-feature-card--${feature.tone}`} key={feature.title}><span className="marketing-feature-card__icon"><MarketingIcon name={feature.icon} /></span><small>{feature.label}</small><h3>{feature.title}</h3><p>{feature.copy}</p><Link href="/features" aria-label={`Explore ${feature.label}`}>Explore capability <span aria-hidden="true">→</span></Link></article>)}</div>
      </div>
    </section>

    <section className="marketing-section marketing-workflow-preview">
      <div className="marketing-container">
        <div className="marketing-workflow-preview__heading"><SectionHeading eyebrow="From setup to close-out" title="A workflow that follows the real day." copy="Start with relationships—site, asset, and person—then keep every field event attached to the operational context that created it." /><Link className="marketing-text-link" href="/how-it-works">Explore the full workflow <span aria-hidden="true">→</span></Link></div>
        <div className="marketing-workflow-line">{workflowSteps.map((step, index) => <article key={step.number}><span className="marketing-workflow-line__number">{step.number}</span><span className="marketing-workflow-line__icon"><MarketingIcon name={step.icon} /></span><h3>{step.title}</h3><p>{step.description}</p>{index < workflowSteps.length - 1 && <i aria-hidden="true" />}</article>)}</div>
      </div>
    </section>

    <section className="marketing-section marketing-showcase">
      <div className="marketing-container">
        <SectionHeading align="center" eyebrow="Owner Operations" title="See the whole working fleet without chasing the day." copy="The Owner workspace connects active assets, assignments, service readiness, operational exceptions, and practical next actions. This is the working product with representative data, never customer records." />
        <div className="marketing-showcase__stage">
          <div className="marketing-showcase__desktop"><span className="marketing-showcase__label">Owner workspace <i>Actual product · representative data</i></span><div className="marketing-product-screenshot"><div className="marketing-product-screenshot__bar"><i/><i/><i/><span>Owner operations</span></div><Image alt="Fleet AI Systems Owner operations overview showing active assets, assignments, maintenance alerts, and quick actions" height={800} priority sizes="(max-width: 640px) 142vw, (max-width: 1120px) 82vw, 760px" src="/product/owner-operations.png" width={1280}/></div></div>
        </div>
        <div className="marketing-showcase__notes"><div><MarketingIcon name="mobile" /><span><strong>Designed for the field</strong>Large actions and role-specific decisions.</span></div><div><MarketingIcon name="shield" /><span><strong>Built around authority</strong>The backend—not the screen—enforces access.</span></div><div><MarketingIcon name="audit" /><span><strong>History stays connected</strong>Assignments and events retain context over time.</span></div></div>
      </div>
    </section>

    <section className="marketing-section marketing-role-showcase">
      <div className="marketing-container">
        <SectionHeading eyebrow="Field operations" title="Focused screens for Drivers and Supervisors." copy="Each mobile role gets the decisions it needs, sized for the field and connected to the same company-scoped record." />
        <div className="marketing-role-showcase__grid">
          <article>
            <div className="marketing-role-showcase__copy"><span>DRIVER / OPERATOR</span><h3>Capture the shift where it happens.</h3><p>Start Duty with meter readings, record trips and diesel, raise emergencies, submit maintenance proof, and keep queued work safe when connectivity drops.</p></div>
            <div className="marketing-phone-pair"><figure><Image alt="Actual Fleet AI Systems Driver on-duty screen using representative data" height={3000} sizes="(max-width: 700px) 62vw, 290px" src="/product/driver-operations.png" width={1170}/><figcaption>On-duty actions</figcaption></figure><figure><Image alt="Actual Fleet AI Systems Start Duty reading workflow using representative data" height={3000} sizes="(max-width: 700px) 62vw, 290px" src="/product/driver-start-duty.png" width={1170}/><figcaption>Start Duty readings</figcaption></figure></div>
          </article>
          <article>
            <div className="marketing-role-showcase__copy"><span>SUPERVISOR</span><h3>Review what needs attention now.</h3><p>A compact site inbox keeps emergency, diesel, trip, meter, and maintenance decisions visible without burying the shift in a general-purpose dashboard.</p></div>
            <figure className="marketing-phone-single"><Image alt="Actual Fleet AI Systems Supervisor review screen using representative data" height={3000} sizes="(max-width: 700px) 72vw, 330px" src="/product/supervisor-review.png" width={1170}/><figcaption>Site-scoped attention inbox</figcaption></figure>
          </article>
        </div>
      </div>
    </section>

    <section className="marketing-section marketing-operations-showcase">
      <div className="marketing-container marketing-operations-showcase__grid">
        <article><div><span>MAINTENANCE</span><h2>Proof, review, and service history stay connected.</h2><p>Drivers submit evidence against due work. Supervisors review it. Owners retain a structured history and a clearer picture of service readiness.</p><Link className="marketing-text-link marketing-text-link--light" href="/features#maintenance">Explore maintenance <span aria-hidden="true">→</span></Link></div><figure><Image alt="Actual Fleet AI Systems maintenance proof review screen using representative data" height={3000} sizes="(max-width: 800px) 72vw, 330px" src="/product/maintenance-review.png" width={1170}/><figcaption>Actual product · representative data</figcaption></figure></article>
        <article className="marketing-reporting-card"><div><span>REPORTING &amp; EXPORTS</span><h2>Turn the operational record into a usable handoff.</h2><p>Build site- and asset-level views, keep pending exceptions visible, and export practical Excel workbooks for management and reconciliation.</p><Link className="marketing-text-link marketing-text-link--light" href="/features#reports">Explore reporting <span aria-hidden="true">→</span></Link></div><div className="marketing-report-sheet" aria-label="Illustration of an operational workbook export"><span>MANAGEMENT SUMMARY</span><strong>Daily fleet operations</strong><div><i>Assets</i><b>24 active</b></div><div><i>Trips</i><b>Verified</b></div><div><i>Diesel</i><b>Reconciled</b></div><div><i>Exceptions</i><b>Visible</b></div><small>.XLSX EXPORT</small></div></article>
      </div>
    </section>

    <section className="marketing-section marketing-fleet-section">
      <div className="marketing-container marketing-fleet-section__grid">
        <div className="marketing-fleet-section__visual" aria-hidden="true"><div className="industrial-sun"/><div className="industrial-ground"/><div className="industrial-machine industrial-machine--excavator"><span/><i/><b/></div><div className="industrial-machine industrial-machine--tipper"><span/><i/><b/></div><div className="industrial-data-card"><small>ASSET MIX</small><strong>Owned + rented</strong><span>One operational view</span></div></div>
        <div className="marketing-fleet-section__copy"><SectionHeading eyebrow="Mixed fleet, clear responsibility" title="From road-going tippers to site machinery." copy="Capability-aware workflows show the actions and readings each asset needs—without pretending every machine works the same way." /><div className="marketing-asset-chips">{assetTypes.map((asset) => <span key={asset}>{asset}<i>✓</i></span>)}</div><p className="marketing-fleet-section__note"><MarketingIcon name="maintenance" /><span><strong>Maintenance responsibility stays explicit.</strong> Rented assets remain operational while service ownership remains with the rental owner when configured that way.</span></p><Link className="marketing-text-link" href="/solutions">See where Fleet AI Systems fits <span aria-hidden="true">→</span></Link></div>
      </div>
    </section>

    <section className="marketing-section marketing-outcomes">
      <div className="marketing-container"><SectionHeading align="center" eyebrow="Operational outcomes" title="Less chasing. More knowing." copy="A useful system should reduce ambiguity before it adds analysis." /><div className="marketing-outcomes__grid">{outcomes.map(([lead, title, copy], index) => <article key={title}><span>0{index + 1}</span><h3><em>{lead}</em> {title}</h3><p>{copy}</p></article>)}</div></div>
    </section>

    <CtaBand />
  </main>;
}
