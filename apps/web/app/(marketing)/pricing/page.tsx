import type { Metadata } from "next";
import Link from "next/link";

import { CtaBand, MarketingIcon, PageHero, SectionHeading } from "../../../features/marketing/MarketingUi";

export const metadata: Metadata = {
  title: "Pricing",
  description: "Contact Fleet AI Systems for fleet operations pricing based on company scope, active assets, sites, onboarding, and rollout needs.",
  alternates: { canonical: "/pricing" },
};

const paths = [
  { name: "Discovery", label: "Workflow fit", copy: "Map one real operation before discussing a software commitment.", included: ["Current workflow review", "Fleet and role mapping", "Implementation fit assessment", "Recommended pilot scope"], action: "Book discovery", featured: false },
  { name: "Guided pilot", label: "Controlled start", copy: "Put a focused group of assets and people through the complete field-to-report loop.", included: ["Company and role setup", "Pilot site onboarding", "Driver and Supervisor workflows", "Owner reporting review"], action: "Plan a pilot", featured: true },
  { name: "Production rollout", label: "Operational scale", copy: "Expand a proven workflow across the agreed fleet, sites, and support model.", included: ["Rollout planning", "Active asset and site scope", "Operational onboarding", "Support expectations"], action: "Discuss rollout", featured: false },
] as const;

export default function PricingPage() {
  return <main id="main-content"><PageHero eyebrow="Pricing" title={<>Scope first.<br /><em>Price the real operation.</em></>} description="Pricing is inquiry-based while deployment packages are finalized. We will not publish invented tiers or promise a price before understanding the fleet, sites, and onboarding work."><Link className="marketing-link-button marketing-link-button--amber" href="/contact">Request a scoped conversation <span aria-hidden="true">↗</span></Link></PageHero>
    <section className="marketing-section marketing-pricing"><div className="marketing-container"><SectionHeading align="center" eyebrow="Engagement paths" title="Start at the level that reduces uncertainty." copy="These paths describe the conversation—not fixed commercial packages. Final scope and pricing require direct confirmation."/><div className="marketing-pricing__grid">{paths.map((path) => <article className={path.featured ? "featured" : ""} key={path.name}>{path.featured && <span className="marketing-pricing__recommended">Recommended starting point</span>}<small>{path.label}</small><h2>{path.name}</h2><p>{path.copy}</p><div className="marketing-pricing__price">Contact <span>for pricing</span></div><ul>{path.included.map((item) => <li key={item}><span>✓</span>{item}</li>)}</ul><Link className={`marketing-link-button ${path.featured ? "marketing-link-button--primary" : "marketing-link-button--outline"}`} href="/contact">{path.action} <span aria-hidden="true">→</span></Link></article>)}</div></div></section>
    <section className="marketing-section marketing-price-drivers"><div className="marketing-container marketing-price-drivers__layout"><div><SectionHeading eyebrow="What shapes the scope" title="Transparent dimensions, confirmed together." copy="A useful quote should reflect the operation being supported—not hide the important work behind a low headline number."/></div><div className="marketing-price-drivers__list"><article><MarketingIcon name="people"/><div><strong>Company + onboarding</strong><span>Configuration, rollout support, and operating roles</span></div></article><article><MarketingIcon name="asset"/><div><strong>Active assets</strong><span>The machines using operational workflows</span></div></article><article><MarketingIcon name="site"/><div><strong>Active sites</strong><span>Current operating locations and Supervisor scope</span></div></article><article><MarketingIcon name="workflow"/><div><strong>Rollout needs</strong><span>Pilot, training, migration, and support expectations</span></div></article></div></div></section>
    <section className="marketing-section marketing-pricing-note"><div className="marketing-container"><div><span className="marketing-status-label"><i/> Current commercial status</span><h2>Pricing is not yet published as a fixed rate card.</h2><p>The product supports controlled pilot and production-oriented workflows, but any commercial proposal remains subject to a confirmed scope. No price shown on this page is a binding offer.</p></div><Link className="marketing-text-link" href="/contact">Start a pricing conversation <span aria-hidden="true">→</span></Link></div></section>
    <CtaBand eyebrow="Bring the operating picture" title="Assets, sites, roles, and the current pain points are enough to begin." copy="We’ll turn those facts into a practical scope before any commercial commitment."/>
  </main>;
}
