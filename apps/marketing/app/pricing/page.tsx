import type { Metadata } from "next";
import Link from "next/link";

import { CtaBand, MarketingIcon, PageHero, SectionHeading } from "../../components/MarketingUi";

export const metadata: Metadata = {
  title: "Pricing",
  description: "Contact Fleet AI Systems for fleet operations pricing based on company scope, active assets, sites, onboarding, and rollout needs.",
  alternates: { canonical: "/pricing" },
};

const paths = [
  { name: "Pilot", label: "For small fleet testing", copy: "Put a focused group of assets and people through the complete field-to-report loop.", included: ["Company and role setup", "Pilot site onboarding", "Driver and Supervisor workflows", "Owner reporting review"], action: "Book a demo", featured: false },
  { name: "Business", label: "For operating fleets", copy: "Run a proven workflow across active sites, assigned teams, and mixed construction assets.", included: ["Active site and fleet scope", "Role-based operations", "Maintenance workflows", "Operational reports and exports"], action: "Talk to us", featured: true },
  { name: "Enterprise", label: "For larger / multi-site deployments", copy: "Plan controls, onboarding, and support for broader operational scale and required integrations.", included: ["Multi-site rollout planning", "Structured onboarding", "Integration scoping", "Support expectations"], action: "Talk to us", featured: false },
] as const;

export default function PricingPage() {
  return <main id="main-content"><PageHero eyebrow="Pricing" title={<>Scope first.<br /><em>Price the real operation.</em></>} description="Pricing is inquiry-based while deployment packages are finalized. We will not publish invented tiers or promise a price before understanding the fleet, sites, and onboarding work."><Link className="marketing-link-button marketing-link-button--amber" href="/contact">Request a scoped conversation <span aria-hidden="true">↗</span></Link></PageHero>
    <section className="marketing-section marketing-pricing"><div className="marketing-container"><SectionHeading align="center" eyebrow="Engagement paths" title="Start at the level that reduces uncertainty." copy="These paths describe the conversation—not fixed commercial packages. Final scope and pricing require direct confirmation."/><div className="marketing-pricing__grid">{paths.map((path) => <article className={path.featured ? "featured" : ""} key={path.name}>{path.featured && <span className="marketing-pricing__recommended">Recommended starting point</span>}<small>{path.label}</small><h2>{path.name}</h2><p>{path.copy}</p><div className="marketing-pricing__price">Contact <span>for pricing</span></div><ul>{path.included.map((item) => <li key={item}><span>✓</span>{item}</li>)}</ul><Link className={`marketing-link-button ${path.featured ? "marketing-link-button--primary" : "marketing-link-button--outline"}`} href="/contact">{path.action} <span aria-hidden="true">→</span></Link></article>)}</div></div></section>
    <section className="marketing-section marketing-price-drivers"><div className="marketing-container marketing-price-drivers__layout"><div><SectionHeading eyebrow="What shapes the scope" title="Transparent dimensions, confirmed together." copy="A useful quote should reflect the operation being supported—not hide the important work behind a low headline number."/></div><div className="marketing-price-drivers__list"><article><MarketingIcon name="people"/><div><strong>Company + onboarding</strong><span>Configuration, rollout support, and operating roles</span></div></article><article><MarketingIcon name="asset"/><div><strong>Active assets</strong><span>The machines using operational workflows</span></div></article><article><MarketingIcon name="site"/><div><strong>Active sites</strong><span>Current operating locations and Supervisor scope</span></div></article><article><MarketingIcon name="workflow"/><div><strong>Rollout needs</strong><span>Pilot, training, migration, and support expectations</span></div></article></div></div></section>
    <section className="marketing-section marketing-pricing-note"><div className="marketing-container"><div><span className="marketing-status-label"><i/> Current commercial status</span><h2>Pricing is not yet published as a fixed rate card.</h2><p>Pricing is based on fleet size and required integrations. Any commercial proposal remains subject to a confirmed scope; this page does not invent prices, discounts, or a binding offer.</p></div><Link className="marketing-text-link" href="/contact">Start a pricing conversation <span aria-hidden="true">→</span></Link></div></section>
    <CtaBand eyebrow="Bring the operating picture" title="Assets, sites, roles, and the current pain points are enough to begin." copy="We’ll turn those facts into a practical scope before any commercial commitment."/>
  </main>;
}
