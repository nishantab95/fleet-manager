"use client";

import { useMemo, useState } from "react";

type FormValues = { name: string; company: string; phone: string; email: string; fleetSize: string; message: string };
const emptyValues: FormValues = { name: "", company: "", phone: "", email: "", fleetSize: "", message: "" };

export function ContactForm() {
  const [values, setValues] = useState<FormValues>(emptyValues);
  const [ready, setReady] = useState(false);
  const emailHref = useMemo(() => {
    const subject = `Demo request · ${values.company || values.name || "Fleet enquiry"}`;
    const body = [`Name: ${values.name}`, `Company: ${values.company}`, `Phone: ${values.phone}`, `Email: ${values.email}`, `Fleet size: ${values.fleetSize || "Not specified"}`, "", values.message].join("\n");
    return `mailto:hello@fleetaisystems.com?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  }, [values]);
  const update = (key: keyof FormValues, value: string) => { setValues((current) => ({ ...current, [key]: value })); setReady(false); };
  return <form className="marketing-contact-form" onSubmit={(event) => { event.preventDefault(); setReady(true); }}>
    <div className="marketing-form-grid">
      <label>Full name<input autoComplete="name" onChange={(event) => update("name", event.target.value)} placeholder="Your name" required value={values.name} /></label>
      <label>Company<input autoComplete="organization" onChange={(event) => update("company", event.target.value)} placeholder="Company or contractor" required value={values.company} /></label>
      <label>Phone<input autoComplete="tel" inputMode="tel" onChange={(event) => update("phone", event.target.value)} placeholder="+91 98765 43210" required value={values.phone} /></label>
      <label>Email<input autoComplete="email" onChange={(event) => update("email", event.target.value)} placeholder="you@company.com" required type="email" value={values.email} /></label>
      <label>Fleet size<select onChange={(event) => update("fleetSize", event.target.value)} value={values.fleetSize}><option value="">Select a range</option><option>1–10 assets</option><option>11–30 assets</option><option>31–75 assets</option><option>76+ assets</option></select></label>
      <label className="marketing-form-grid__message">What would you like to improve?<textarea onChange={(event) => update("message", event.target.value)} placeholder="Tell us about your sites, fleet mix, and current workflow." required rows={5} value={values.message} /></label>
    </div>
    <div className="marketing-contact-form__submit"><button className="marketing-link-button marketing-link-button--primary" type="submit">Prepare demo request <span aria-hidden="true">→</span></button><p>No third-party form processor is connected. We prepare the message in your email app, and you choose when to send it.</p></div>
    {ready && <div className="marketing-contact-form__ready" role="status"><div><strong>Your request is ready.</strong><span>Continue in your email app to review and send it.</span></div><a className="marketing-link-button marketing-link-button--amber" href={emailHref}>Open email draft <span aria-hidden="true">↗</span></a></div>}
  </form>;
}
