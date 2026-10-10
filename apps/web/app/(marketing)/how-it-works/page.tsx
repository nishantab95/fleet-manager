import type { Metadata } from "next";
import Link from "next/link";

import { workflowSteps } from "../../../features/marketing/content";
import { CtaBand, MarketingIcon, MobileInterfacePreview, OwnerInterfacePreview, PageHero, SectionHeading } from "../../../features/marketing/MarketingUi";

export const metadata: Metadata = {
  title: "How it works",
  description: "See how Fleet AI Systems connects fleet setup, assignments, mobile field capture, Supervisor review, reporting, and maintenance.",
  alternates: { canonical: "/how-it-works" },
};

export default function HowItWorksPage() {
  return <main id="main-content">
    <PageHero eyebrow="The operational loop" title={<>From assignment to answer,<br /><em>without losing context.</em></>} description="The system follows how construction fleets actually work: relationships first, evidence in the field, review at the site, and a clearer view for the Owner."><Link className="marketing-link-button marketing-link-button--amber" href="#workflow">Walk through the flow <span aria-hidden="true">↓</span></Link></PageHero>
    <section className="marketing-section marketing-story" id="workflow"><div className="marketing-container marketing-story__layout"><div className="marketing-story__rail" aria-hidden="true"><span/><i/></div><div className="marketing-story__steps">{workflowSteps.map((step, index) => <article className="marketing-story-step" key={step.number}><div className="marketing-story-step__marker"><span>{step.number}</span></div><div className="marketing-story-step__copy"><span className="marketing-story-step__icon"><MarketingIcon name={step.icon} /></span><small>Step {index + 1}</small><h2>{step.title}</h2><p>{step.description}</p>{index === 0 && <div className="marketing-story-detail"><span>Site</span><i>→</i><span>Asset</span><i>→</i><span>Person</span></div>}{index === 1 && <div className="marketing-story-detail"><span>Deploy</span><i>→</i><span>Assign</span><i>→</i><span>Start</span></div>}{index === 2 && <div className="marketing-story-phone"><MobileInterfacePreview /></div>}{index === 3 && <div className="marketing-story-review"><div><span><i/>PENDING REVIEW</span><strong>Dashboard reading</strong><p>KM 42,560 · HMR 3,214.6</p></div><button type="button" tabIndex={-1}>Approve</button></div>}{index === 4 && <div className="marketing-story-dashboard"><OwnerInterfacePreview compact /></div>}</div></article>)}</div></div></section>
    <section className="marketing-section marketing-principles"><div className="marketing-container"><SectionHeading align="center" eyebrow="Quiet technology, strong controls" title="Complexity lives underneath—not in the cab." copy="The platform protects the operational record without asking field users to manage the machinery behind it." /><div className="marketing-principles__grid"><article><MarketingIcon name="mobile"/><h3>Offline-first capture</h3><p>Important actions stay queued with a client-generated identity until the server accepts them.</p></article><article><MarketingIcon name="shield"/><h3>Server-side authority</h3><p>Role, company, site, and assignment access are enforced beyond what the interface happens to show.</p></article><article><MarketingIcon name="audit"/><h3>Auditable history</h3><p>Corrections, approvals, assignments, and service events retain actors, timestamps, and context.</p></article></div></div></section>
    <CtaBand />
  </main>;
}
