import Link from "next/link";
import type { ReactNode } from "react";

import { primaryNavigation } from "./content";

export function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <span className="marketing-brand" aria-label="Fleet AI Systems">
      <span aria-hidden="true" className="marketing-brand__mark">
        <svg viewBox="0 0 48 48" role="img">
          <path d="M8 34.5V15.2L24 6l16 9.2v18.4L24 42 8 34.5Z" />
          <path d="M16 30.5V18.8L24 14l8 4.8v11.7L24 35l-8-4.5Z" />
          <path d="M8 24h8m16 0h8M24 6v8m0 21v7" />
        </svg>
      </span>
      {!compact && (
        <span className="marketing-brand__type">
          <strong>Fleet AI</strong>
          <span>Systems</span>
        </span>
      )}
    </span>
  );
}
export function MarketingHeader() {
  return (
    <header className="marketing-header">
      <div className="marketing-container marketing-header__inner">
        <Link className="marketing-header__brand" href="/" aria-label="Fleet AI Systems home">
          <BrandMark />
        </Link>
        <nav className="marketing-nav marketing-nav--desktop" aria-label="Primary navigation">
          {primaryNavigation.map((item) => <Link href={item.href} key={item.href}>{item.label}</Link>)}
        </nav>
        <div className="marketing-header__actions">
          <Link className="marketing-link-button marketing-link-button--quiet marketing-header__login" href="/login?workspace=owner">Open operations</Link>
          <Link className="marketing-link-button marketing-link-button--primary" href="/contact">Book a demo <span aria-hidden="true">↗</span></Link>
        </div>
        <details className="marketing-menu">
          <summary aria-label="Open navigation menu"><span /><span /><span /></summary>
          <nav aria-label="Mobile navigation">
            {primaryNavigation.map((item) => <Link href={item.href} key={item.href}>{item.label}</Link>)}
            <Link href="/contact">Book a demo</Link>
            <Link href="/login?workspace=owner">Open operations</Link>
          </nav>
        </details>
      </div>
    </header>
  );
}

export function MarketingFooter() {
  return (
    <footer className="marketing-footer">
      <div className="marketing-container marketing-footer__top">
        <div className="marketing-footer__intro">
          <BrandMark />
          <p>Clearer field operations for construction fleets that move real work.</p>
        </div>
        <div className="marketing-footer__links">
          <div><strong>Platform</strong><Link href="/features">Features</Link><Link href="/how-it-works">How it works</Link><Link href="/solutions">Solutions</Link></div>
          <div><strong>Company</strong><Link href="/pricing">Pricing</Link><Link href="/contact">Contact</Link><Link href="/contact">Book a demo</Link></div>
          <div><strong>Operations</strong><Link href="/login?workspace=owner">Owner access</Link><Link href="/login?workspace=supervisor">Supervisor access</Link></div>
        </div>
      </div>
      <div className="marketing-container marketing-footer__bottom">
        <span>© {new Date().getFullYear()} Fleet AI Systems</span>
        <span>fleetaisystems.com</span>
        <span>Privacy and terms available before public launch</span>
      </div>
    </footer>
  );
}

export function PageFrame({ children }: { children: ReactNode }) {
  return <div className="marketing-site"><a className="marketing-skip-link" href="#main-content">Skip to content</a><MarketingHeader />{children}<MarketingFooter /></div>;
}
