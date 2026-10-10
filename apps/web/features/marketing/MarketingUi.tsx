import Link from "next/link";
import type { ReactNode } from "react";

type IconName = "asset" | "audit" | "deploy" | "diesel" | "download" | "insight" | "maintenance" | "meter" | "mobile" | "people" | "review" | "shield" | "site" | "tipper" | "workflow";

export function MarketingIcon({ name }: { name: string }) {
  const paths: Record<IconName, ReactNode> = {
    asset: <><path d="M4 17h16M6 17l1-7h9l2 7M8 10l2-4h4l2 4"/><circle cx="8" cy="18" r="2"/><circle cx="17" cy="18" r="2"/></>,
    audit: <><path d="M6 3h12v18H6zM9 8h6M9 12h6M9 16h4"/><path d="m15 17 1.5 1.5L20 15"/></>,
    deploy: <><path d="M4 7h6v5H4zM14 12h6v5h-6zM7 12v5h4M17 7v5"/><circle cx="7" cy="19" r="2"/><circle cx="17" cy="5" r="2"/></>,
    diesel: <><path d="M6 3h9v18H6zM8 6h5v5H8zM15 7h2l2 3v8a2 2 0 0 1-2 2h-2"/></>,
    download: <><path d="M12 3v12m0 0 4-4m-4 4-4-4M5 21h14"/></>,
    insight: <><path d="M4 20V9m5 11V4m5 16v-7m5 7V7"/></>,
    maintenance: <><path d="m14 6 4-3 3 3-3 4m-4-4-8 8-3 7 7-3 8-8M6 15l3 3"/></>,
    meter: <><path d="M4 18a8 8 0 1 1 16 0H4Z"/><path d="m12 15 4-4M8 18h8"/></>,
    mobile: <><rect x="7" y="2" width="10" height="20" rx="2"/><path d="M10 5h4M11 18h2"/></>,
    people: <><circle cx="9" cy="8" r="3"/><path d="M3 20c0-4 2-7 6-7s6 3 6 7M16 6a3 3 0 0 1 0 6m1 2c2.5.7 4 2.8 4 6"/></>,
    review: <><path d="M5 4h14v16H5zM8 8h5M8 12h4"/><path d="m13 16 2 2 4-5"/></>,
    shield: <><path d="M12 3 20 6v6c0 5-3.5 8-8 10-4.5-2-8-5-8-10V6l8-3Z"/><path d="m8.5 12 2.2 2.2L16 9"/></>,
    site: <><path d="M4 21V9l8-6 8 6v12M8 21v-7h8v7M3 21h18"/></>,
    tipper: <><path d="M3 15h13l3-5h2v7h-2M5 15 3 8h11l2 7"/><circle cx="7" cy="18" r="2"/><circle cx="17" cy="18" r="2"/></>,
    workflow: <><circle cx="5" cy="6" r="2"/><circle cx="19" cy="6" r="2"/><circle cx="12" cy="18" r="2"/><path d="M7 6h10M6 8l5 8m7-8-5 8"/></>,
  };
  const path = paths[name as IconName] ?? paths.workflow;
  return <svg className="marketing-icon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7">{path}</svg>;
}
export function SectionHeading({ eyebrow, title, copy, align = "left" }: { eyebrow: string; title: string; copy?: string; align?: "left" | "center" }) {
  return <div className={`marketing-section-heading marketing-section-heading--${align}`}><span className="marketing-eyebrow">{eyebrow}</span><h2>{title}</h2>{copy && <p>{copy}</p>}</div>;
}

export function PageHero({ eyebrow, title, description, children }: { eyebrow: string; title: ReactNode; description: string; children?: ReactNode }) {
  return <section className="marketing-page-hero"><div className="marketing-orb marketing-orb--one" /><div className="marketing-orb marketing-orb--two" /><div className="marketing-container marketing-page-hero__inner"><span className="marketing-eyebrow marketing-eyebrow--light">{eyebrow}</span><h1>{title}</h1><p>{description}</p>{children}</div></section>;
}

export function CtaBand({ eyebrow = "Build a calmer operation", title = "See your fleet clearly before the next shift starts.", copy = "Tell us how your sites, assets, and teams work today. We’ll map a practical starting point without forcing a generic template." }: { eyebrow?: string; title?: string; copy?: string }) {
  return <section className="marketing-cta-band"><div className="marketing-container marketing-cta-band__inner"><div><span className="marketing-eyebrow marketing-eyebrow--amber">{eyebrow}</span><h2>{title}</h2><p>{copy}</p></div><div className="marketing-cta-band__actions"><Link className="marketing-link-button marketing-link-button--amber" href="/contact">Book a demo <span aria-hidden="true">↗</span></Link><Link className="marketing-text-link marketing-text-link--light" href="/features">Explore the platform <span aria-hidden="true">→</span></Link></div></div></section>;
}

export function OwnerInterfacePreview({ compact = false }: { compact?: boolean }) {
  return <div className={`product-window ${compact ? "product-window--compact" : ""}`} aria-label="Fleet AI Systems Owner operations interface preview" role="img">
    <div className="product-window__bar"><div className="product-window__dots"><i /><i /><i /></div><span>Owner operations</span><div className="product-window__secure"><span /> Secure</div></div>
    <div className="product-window__body">
      <aside><div className="product-mini-brand">FA</div>{["grid", "truck", "wrench", "people", "site", "chart"].map((item) => <span className={`product-nav-icon product-nav-icon--${item}`} key={item} />)}</aside>
      <div className="product-dashboard">
        <div className="product-dashboard__heading"><div><small>LIVE FLEET READINESS</small><strong>Fleet command centre</strong></div><span>10 Oct · Today</span></div>
        <div className="product-metrics"><div><small>Active assets</small><strong>24</strong><em>Across 4 sites</em></div><div><small>On duty</small><strong>18</strong><em className="positive">↑ Ready now</em></div><div><small>Pending review</small><strong>06</strong><em>Needs attention</em></div><div><small>Maintenance</small><strong>03</strong><em className="warning">Due soon</em></div></div>
        <div className="product-dashboard__content">
          <div className="product-panel product-panel--chart"><div className="product-panel__title"><strong>Operational pulse</strong><span>7 days</span></div><div className="product-chart"><i style={{height:"44%"}}/><i style={{height:"62%"}}/><i style={{height:"55%"}}/><i style={{height:"78%"}}/><i style={{height:"70%"}}/><i style={{height:"88%"}}/><i className="active" style={{height:"82%"}}/></div><div className="product-chart__labels"><span>M</span><span>T</span><span>W</span><span>T</span><span>F</span><span>S</span><span>S</span></div></div>
          <div className="product-panel product-panel--sites"><div className="product-panel__title"><strong>Site readiness</strong><span>Live</span></div><div className="product-site-row"><i className="ready"/><span><strong>North Quarry</strong><small>8 assets · 7 on duty</small></span><em>Ready</em></div><div className="product-site-row"><i className="attention"/><span><strong>Ring Road</strong><small>10 assets · 2 pending</small></span><em>Review</em></div><div className="product-site-row"><i className="ready"/><span><strong>River Works</strong><small>6 assets · 5 on duty</small></span><em>Ready</em></div></div>
        </div>
      </div>
    </div>
  </div>;
}

export function MobileInterfacePreview({ role = "driver" }: { role?: "driver" | "supervisor" }) {
  const supervisor = role === "supervisor";
  return <div className={`product-phone product-phone--${role}`} aria-label={`Fleet AI Systems ${supervisor ? "Supervisor" : "Driver"} mobile interface preview`} role="img"><div className="product-phone__speaker"/><div className="product-phone__screen"><div className="product-phone__status"><span>9:41</span><span>● ◒ ▰</span></div><div className="product-phone__brand"><span>FA</span><div><small>{supervisor ? "SUPERVISOR" : "DRIVER"}</small><strong>{supervisor ? "Ring Road" : "KA 01 AB 2481"}</strong></div><i /></div>{supervisor ? <><div className="phone-summary"><span><small>Pending</small><strong>06</strong></span><span><small>Approved</small><strong>18</strong></span></div><div className="phone-review"><small>METER READING</small><strong>Tipper 12 · Start duty</strong><p>KM 42,560 · HMR 3,214.6</p><div><button type="button" tabIndex={-1}>Review</button><span>10:14</span></div></div><div className="phone-review"><small>DIESEL ENTRY</small><strong>Excavator 04</strong><p>68 litres · proof attached</p><div><button type="button" tabIndex={-1}>Review</button><span>10:08</span></div></div></> : <><div className="phone-assignment"><small>CURRENT ASSIGNMENT</small><strong>North Quarry</strong><span>Supervisor · A. Kumar</span></div><div className="phone-duty"><i/><div><small>DUTY STATUS</small><strong>Active since 07:42</strong></div><span>SYNCED</span></div><div className="phone-actions"><button type="button" tabIndex={-1}><MarketingIcon name="tipper"/><span>TRIP COMPLETE</span></button><button type="button" tabIndex={-1}><MarketingIcon name="diesel"/><span>DIESEL</span></button><button className="emergency" type="button" tabIndex={-1}>EMERGENCY</button></div><div className="phone-end">END DUTY</div></>}</div></div>;
}
