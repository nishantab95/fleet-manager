"use client";

import { useMemo, useState } from "react";

type FormValues = {
  name: string;
  company: string;
  phone: string;
  email: string;
  fleetSize: string;
  fleetType: string;
  message: string;
  website: string;
};

type SubmissionState =
  | { kind: "idle" }
  | { kind: "sending" }
  | { kind: "success"; reference: string }
  | { kind: "error"; message: string; emailFallback: boolean };

const emptyValues: FormValues = {
  name: "",
  company: "",
  phone: "",
  email: "",
  fleetSize: "",
  fleetType: "",
  message: "",
  website: "",
};

export function ContactForm() {
  const [values, setValues] = useState<FormValues>(emptyValues);
  const [submission, setSubmission] = useState<SubmissionState>({ kind: "idle" });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const emailHref = useMemo(() => {
    const subject = `Demo request · ${values.company || values.name || "Fleet enquiry"}`;
    const body = [
      `Name: ${values.name}`,
      `Company: ${values.company}`,
      `Phone: ${values.phone}`,
      `Email: ${values.email}`,
      `Fleet size: ${values.fleetSize || "Not specified"}`,
      `Fleet type: ${values.fleetType || "Not specified"}`,
      "",
      values.message,
    ].join("\n");
    return `mailto:hello@fleetaisystems.com?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  }, [values]);

  const update = (key: keyof FormValues, value: string) => {
    setValues((current) => ({ ...current, [key]: value }));
    setFieldErrors((current) => {
      const next = { ...current };
      delete next[key];
      return next;
    });
    setSubmission({ kind: "idle" });
  };

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmission({ kind: "sending" });
    setFieldErrors({});
    try {
      const response = await fetch("/public/leads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
      });
      const body = (await response.json().catch(() => ({}))) as {
        error?: string;
        fields?: Record<string, string>;
        reference?: string;
      };
      if (response.status === 201 && body.reference) {
        setSubmission({ kind: "success", reference: body.reference });
        setValues(emptyValues);
        return;
      }
      if (body.fields) setFieldErrors(body.fields);
      setSubmission({
        kind: "error",
        message: body.error || "The request could not be sent. Please try again.",
        emailFallback: response.status >= 500,
      });
    } catch {
      setSubmission({
        kind: "error",
        message: "The request could not reach the website. You can send the same details by email.",
        emailFallback: true,
      });
    }
  }

  const error = (field: keyof FormValues) => fieldErrors[field];

  return (
    <form className="marketing-contact-form" onSubmit={submit}>
      <div className="marketing-form-grid">
        <label>
          Full name
          <input aria-describedby={error("name") ? "lead-name-error" : undefined} aria-invalid={Boolean(error("name"))} autoComplete="name" maxLength={80} minLength={2} onChange={(event) => update("name", event.target.value)} placeholder="Your name" required value={values.name} />
          {error("name") && <span className="marketing-field-error" id="lead-name-error">{error("name")}</span>}
        </label>
        <label>
          Company
          <input aria-describedby={error("company") ? "lead-company-error" : undefined} aria-invalid={Boolean(error("company"))} autoComplete="organization" maxLength={120} minLength={2} onChange={(event) => update("company", event.target.value)} placeholder="Company or contractor" required value={values.company} />
          {error("company") && <span className="marketing-field-error" id="lead-company-error">{error("company")}</span>}
        </label>
        <label>
          Phone
          <input aria-describedby={error("phone") ? "lead-phone-error" : undefined} aria-invalid={Boolean(error("phone"))} autoComplete="tel" inputMode="tel" maxLength={24} onChange={(event) => update("phone", event.target.value)} placeholder="+91 98765 43210" required value={values.phone} />
          {error("phone") && <span className="marketing-field-error" id="lead-phone-error">{error("phone")}</span>}
        </label>
        <label>
          Email
          <input aria-describedby={error("email") ? "lead-email-error" : undefined} aria-invalid={Boolean(error("email"))} autoComplete="email" maxLength={254} onChange={(event) => update("email", event.target.value)} placeholder="you@company.com" required type="email" value={values.email} />
          {error("email") && <span className="marketing-field-error" id="lead-email-error">{error("email")}</span>}
        </label>
        <label>
          Fleet size
          <select aria-describedby={error("fleetSize") ? "lead-size-error" : undefined} aria-invalid={Boolean(error("fleetSize"))} onChange={(event) => update("fleetSize", event.target.value)} required value={values.fleetSize}>
            <option value="">Select a range</option>
            <option value="1-10">1–10 assets</option>
            <option value="11-30">11–30 assets</option>
            <option value="31-75">31–75 assets</option>
            <option value="76+">76+ assets</option>
          </select>
          {error("fleetSize") && <span className="marketing-field-error" id="lead-size-error">{error("fleetSize")}</span>}
        </label>
        <label>
          Primary fleet type
          <select aria-describedby={error("fleetType") ? "lead-type-error" : undefined} aria-invalid={Boolean(error("fleetType"))} onChange={(event) => update("fleetType", event.target.value)} required value={values.fleetType}>
            <option value="">Select the closest fit</option>
            <option value="tippers">Primarily tippers</option>
            <option value="earthmoving">Excavators / machinery</option>
            <option value="mixed">Mixed fleet</option>
            <option value="other">Other construction fleet</option>
          </select>
          {error("fleetType") && <span className="marketing-field-error" id="lead-type-error">{error("fleetType")}</span>}
        </label>
        <label className="marketing-form-grid__message">
          What would you like to improve?
          <textarea aria-describedby={error("message") ? "lead-message-error" : undefined} aria-invalid={Boolean(error("message"))} maxLength={1000} minLength={20} onChange={(event) => update("message", event.target.value)} placeholder="Tell us about your sites, fleet mix, and current workflow." required rows={5} value={values.message} />
          {error("message") && <span className="marketing-field-error" id="lead-message-error">{error("message")}</span>}
        </label>
        <label className="marketing-honeypot" aria-hidden="true">
          Website
          <input autoComplete="off" name="website" onChange={(event) => update("website", event.target.value)} tabIndex={-1} value={values.website} />
        </label>
      </div>
      <div className="marketing-contact-form__submit">
        <button className="marketing-link-button marketing-link-button--primary" disabled={submission.kind === "sending"} type="submit">
          {submission.kind === "sending" ? "Sending…" : "Request a demo"} <span aria-hidden="true">→</span>
        </button>
        <p>Sent only to the isolated Fleet AI Systems website lead store. It cannot read Fleet operations, users, assets, or evidence.</p>
      </div>
      {submission.kind === "success" && (
        <div className="marketing-contact-form__ready" role="status">
          <div><strong>Request received.</strong><span>Reference {submission.reference}. We’ll use your details only to respond to this enquiry.</span></div>
        </div>
      )}
      {submission.kind === "error" && (
        <div className="marketing-contact-form__error" role="alert">
          <div><strong>We could not submit the request.</strong><span>{submission.message}</span></div>
          {submission.emailFallback && <a className="marketing-link-button marketing-link-button--outline" href={emailHref}>Use email instead <span aria-hidden="true">↗</span></a>}
        </div>
      )}
    </form>
  );
}
