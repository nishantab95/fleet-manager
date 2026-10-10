import type { Metadata } from "next";

import { ContactForm } from "../../../features/marketing/ContactForm";
import { MarketingIcon, PageHero } from "../../../features/marketing/MarketingUi";

export const metadata: Metadata = {
  title: "Contact",
  description: "Request a Fleet AI Systems demo and discuss your construction fleet, active sites, field workflows, maintenance, and reporting needs.",
  alternates: { canonical: "/contact" },
};

export default function ContactPage() {
  return <main id="main-content"><PageHero eyebrow="Book a demo" title={<>Bring us the operation<br /><em>you want to simplify.</em></>} description="Share the fleet mix, active sites, and the part of the day that creates the most uncertainty. We’ll make the first conversation practical."/>
    <section className="marketing-section marketing-contact"><div className="marketing-container marketing-contact__layout"><div className="marketing-contact__aside"><span className="marketing-eyebrow">What happens next</span><h2>A working conversation, not a generic tour.</h2><p>We’ll use the details you provide to focus the demo on actual field and Owner workflows.</p><ol><li><span>01</span><div><strong>We review the operating context</strong><p>Fleet mix, sites, roles, and current record keeping.</p></div></li><li><span>02</span><div><strong>We map one daily workflow</strong><p>From assignment and field capture through review and reporting.</p></div></li><li><span>03</span><div><strong>We identify the smallest useful start</strong><p>A controlled scope with clear success criteria.</p></div></li></ol><div className="marketing-contact__direct"><div><MarketingIcon name="mobile"/><span><small>EMAIL</small><a href="mailto:hello@fleetaisystems.com">hello@fleetaisystems.com</a></span></div><div><MarketingIcon name="people"/><span><small>WHATSAPP / PHONE</small><strong>Shared after first contact</strong></span></div><p>Contact channels are pre-launch placeholders and must be confirmed before public deployment.</p></div></div><div className="marketing-contact__form-wrap"><div className="marketing-contact__form-heading"><span>DEMO REQUEST</span><strong>Tell us about your fleet</strong><p>Required fields help us keep the first conversation useful.</p></div><ContactForm/></div></div></section>
  </main>;
}
