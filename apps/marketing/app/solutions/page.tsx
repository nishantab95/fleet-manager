import type { Metadata } from "next";
import Link from "next/link";

import { CtaBand, MarketingIcon, PageHero, SectionHeading } from "../../components/MarketingUi";

export const metadata: Metadata = {
  title: "Solutions",
  description: "Fleet operations software for tippers, construction machinery, mixed owned and rented fleets, site coordination, and growing contractors.",
  alternates: { canonical: "/solutions" },
};

const solutions = [
  { icon: "tipper", label: "Tipper fleets", title: "Keep every run tied to the right Driver, asset, and site.", copy: "Capture duty, trips, diesel, odometer and hour-meter evidence, then move verified activity into daily reporting.", points: ["Trip and diesel workflows", "Combined KM + HMR capture", "Site/day reporting"] },
  { icon: "maintenance", label: "Excavators + machinery", title: "Operate machines without forcing a tipper workflow onto them.", copy: "Capability-aware actions support tracked and non-trip machinery while keeping meter and maintenance history intact.", points: ["HMR-first workflows", "No fabricated trip action", "Service readiness"] },
  { icon: "asset", label: "Mixed fleets", title: "See owned and rented assets in one operational picture.", copy: "Track work consistently while keeping ownership, rental contacts, and maintenance responsibility explicit.", points: ["Owned + rented status", "Shared operational controls", "Clear responsibility"] },
  { icon: "site", label: "Site coordination", title: "Put the site at the centre of daily control.", copy: "Deploy assets, scope Supervisors, review exceptions, and close the day against the work that belongs there.", points: ["Deployment visibility", "Supervisor site access", "Daily closure"] },
  { icon: "people", label: "Growing contractors", title: "Replace memory and message threads with a repeatable system.", copy: "Give a lean operations team practical control without demanding an enterprise transformation before day one.", points: ["Focused onboarding", "Role-based workspaces", "Excel-ready outputs"] },
  { icon: "workflow", label: "Multi-role operations", title: "Connect the office, site, and field without mixing their decisions.", copy: "Each role works in its own view while events, evidence, and approvals form one reliable record.", points: ["Owner command", "Driver simplicity", "Supervisor verification"] },
] as const;

export default function SolutionsPage() {
  return <main id="main-content"><PageHero eyebrow="Built around the work" title={<>For fleets that build,<br /><em>move, grade, and dig.</em></>} description="Fleet AI Systems is designed for construction operators who coordinate people and mixed assets across active sites—not generic last-mile delivery."><Link className="marketing-link-button marketing-link-button--amber" href="/contact">Talk through your operation <span aria-hidden="true">↗</span></Link></PageHero>
    <section className="marketing-section marketing-solutions"><div className="marketing-container"><SectionHeading eyebrow="Real operating scenarios" title="A better fit for the fleet you actually run." copy="Start with the operational problem, then apply only the workflows each asset and role needs."/><div className="marketing-solutions__grid">{solutions.map((solution, index) => <article key={solution.label}><div className="marketing-solutions__top"><span><MarketingIcon name={solution.icon}/></span><i>0{index + 1}</i></div><small>{solution.label}</small><h2>{solution.title}</h2><p>{solution.copy}</p><ul>{solution.points.map((point) => <li key={point}>✓ {point}</li>)}</ul></article>)}</div></div></section>
    <section className="marketing-section marketing-fit"><div className="marketing-container marketing-fit__layout"><div><SectionHeading eyebrow="A practical fit check" title="Designed for operational discipline—not surveillance." copy="The platform records work events and relationships. It does not claim continuous GPS tracking, predictive maintenance, payroll, accounting, or emergency-response guarantees."/><Link className="marketing-text-link" href="/features">See available and roadmap capability <span aria-hidden="true">→</span></Link></div><div className="marketing-fit__card"><small>STRONGEST FIT</small><h3>Construction fleet Owners and contractors</h3><ul><li><span>01</span>Multiple active sites</li><li><span>02</span>Drivers, Operators, and Supervisors</li><li><span>03</span>Mixed owned and rented assets</li><li><span>04</span>Evidence and daily reporting needs</li></ul></div></div></section><CtaBand eyebrow="Start with one real site" title="Map the workflow before choosing the rollout." copy="We’ll use your current fleet mix, roles, and daily controls to identify the right first deployment."/></main>;
}
