import type { Metadata } from "next";
import Link from "next/link";

import { availableFeatures } from "../../../features/marketing/content";
import { CtaBand, MarketingIcon, PageHero, SectionHeading } from "../../../features/marketing/MarketingUi";

export const metadata: Metadata = {
  title: "Features",
  description: "Explore Fleet AI Systems capabilities for Owners, Drivers, Operators, Supervisors, maintenance, reporting, and role-based fleet operations.",
  alternates: { canonical: "/features" },
};

const groups = [
  { key: "owner", index: "01", eyebrow: "Owner / Admin", title: "A command layer for the whole operation", copy: "Structure fleet relationships, understand readiness, and move from today’s exceptions to tomorrow’s plan.", icon: "insight", aside: ["Fleet command centre", "People + Sites", "Reports + workbooks"] },
  { key: "driver", index: "02", eyebrow: "Driver / Operator", title: "Field capture made deliberately simple", copy: "The mobile workflow follows duty state and asset capability, with durable offline capture for the moments when coverage disappears.", icon: "mobile", aside: ["Duty-aware actions", "One meter photo", "Offline safe retry"] },
  { key: "supervisor", index: "03", eyebrow: "Supervisor", title: "Site review without crossing access boundaries", copy: "Each Supervisor sees permitted sites and the field events that need an operational decision—not an unrestricted company view.", icon: "review", aside: ["Site-scoped access", "Evidence review", "Daily completeness"] },
  { key: "intelligence", index: "04", eyebrow: "Operations intelligence", title: "History that explains how the day happened", copy: "Effective-dated relationships, evidence, and verification history keep reports connected to the real assignment context.", icon: "audit", aside: ["Assignment history", "Tenant isolation", "Auditable decisions"] },
] as const;

const currentCapabilities = [
  ["Fleet relationships", "Sites, assets, people, deployments, and assignments share one operational context.", "workflow"],
  ["Capability-aware meters", "Wheeled assets capture KM and HMR together; tracked machinery captures the readings it actually supports.", "meter"],
  ["Maintenance operations", "Intervals, due state, proof submission, Supervisor review, and immutable service history.", "maintenance"],
  ["Excel-ready reporting", "Management and site workbooks generated from the same reporting rules as the application.", "download"],
] as const;

const roadmap = [
  ["Document connectors", "DigiLocker and entity document workflows are roadmap items, not live integrations."],
  ["Telematics", "Vehicle and machine telemetry can extend the operational record after the core workflow is proven."],
  ["Compliance automation", "Future document and compliance reminders will build on the existing identity and audit model."],
] as const;

export default function FeaturesPage() {
  return <main id="main-content">
    <PageHero eyebrow="Platform capabilities" title={<>Purpose-built for every role.<br /><em>Connected by the operation.</em></>} description="Fleet AI Systems gives each person the decisions they need while the platform preserves company scope, assignment context, and evidence behind the scenes."><Link className="marketing-link-button marketing-link-button--amber" href="/contact">See it with your fleet <span aria-hidden="true">↗</span></Link></PageHero>
    <section className="marketing-section marketing-feature-groups"><div className="marketing-container">{groups.map((group) => <article className="marketing-feature-group" key={group.key}><div className="marketing-feature-group__index">{group.index}</div><div className="marketing-feature-group__copy"><span className="marketing-eyebrow">{group.eyebrow}</span><h2>{group.title}</h2><p>{group.copy}</p><ul>{availableFeatures[group.key].map((feature) => <li key={feature}><span>✓</span>{feature}</li>)}</ul></div><div className="marketing-feature-group__aside"><span><MarketingIcon name={group.icon} /></span>{group.aside.map((item, index) => <div key={item}><i>0{index + 1}</i><strong>{item}</strong></div>)}</div></article>)}</div></section>
    <section className="marketing-section marketing-capability-status"><div className="marketing-container"><SectionHeading eyebrow="Clear product truth" title="Available now, with the roadmap kept honest." copy="We separate working capability from future direction so every product conversation starts from the same facts." /><div className="marketing-capability-status__layout"><div className="marketing-status-column"><span className="marketing-status-label marketing-status-label--live"><i /> Available now</span>{currentCapabilities.map(([title, copy, icon]) => <article key={title}><span><MarketingIcon name={icon} /></span><div><h3>{title}</h3><p>{copy}</p></div></article>)}</div><div className="marketing-status-column marketing-status-column--roadmap"><span className="marketing-status-label"><i /> Roadmap</span>{roadmap.map(([title, copy]) => <article key={title}><span>→</span><div><h3>{title}</h3><p>{copy}</p></div></article>)}</div></div></div></section>
    <CtaBand eyebrow="See the working platform" title="Bring one real workflow. We’ll walk it end to end." copy="A practical demo is the fastest way to see where Fleet AI Systems fits—and where it should stay out of the way." />
  </main>;
}
