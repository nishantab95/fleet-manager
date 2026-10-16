import type { Metadata } from "next";

import { PageHero } from "../../components/MarketingUi";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description: "How Fleet AI Systems handles personal and operational information.",
  alternates: { canonical: "/privacy" },
};

export default function PrivacyPage() {
  return (
    <main id="main-content">
      <PageHero
        eyebrow="Privacy"
        title={<>Clear information.<br /><em>Controlled access.</em></>}
        description="This notice explains the information Fleet AI Systems processes, why it is needed, and the choices available to users and company administrators."
      />
      <article className="marketing-policy marketing-container">
        <p className="marketing-policy__updated">Last updated: 16 October 2026</p>

        <h2>Who this notice covers</h2>
        <p>Fleet AI Systems is a business fleet-operations service used by authorised companies, Owners, Drivers, Operators, and Supervisors. The company that gives you access controls its workforce and operational records. Fleet AI Systems operates the application and public website. Privacy questions can be sent to <a href="mailto:hello@fleetaisystems.com">hello@fleetaisystems.com</a>.</p>

        <h2>Information processed</h2>
        <ul>
          <li>Account and access information, including name, phone number, company membership, authorised roles, assignments, installation and device identifiers, session records, and security audit events.</li>
          <li>Fleet operations entered by authorised users, including duty, trips, diesel, odometer or hour-meter readings, maintenance, emergencies, sites, assets, timestamps, review decisions, and photographs supplied as evidence.</li>
          <li>Public website contact requests, including contact details, company, fleet information, and the message submitted.</li>
          <li>Technical records needed to secure and operate the service, such as request identifiers, IP address in access logs, error records, backup records, and application version.</li>
        </ul>
        <p>The current application does not provide continuous GPS tracking and does not request location permission. Camera access is used only when a user chooses to capture evidence. Device biometric or screen-lock checks are performed by Android; Fleet AI Systems does not receive the biometric secret.</p>

        <h2>Why information is used</h2>
        <p>Information is used to activate authorised installations, authenticate users, enforce company, role, device, site, and assignment boundaries, deliver fleet workflows, preserve offline submissions, investigate incidents, maintain auditability, support customers, and protect and improve service reliability. It is not used for SMS authentication in the Google Play production application.</p>

        <h2>Hosting and service providers</h2>
        <p>The planned production service is hosted in Singapore and uses private database and evidence storage plus an independently encrypted backup location. Google Play distributes the Android application. Firebase compatibility code may remain in the software, but Firebase Phone Authentication is not initialised or required when the production application runs in company-PIN mode. Specific providers and locations may change under controlled operations without reducing the protections described here.</p>

        <h2>Retention and deletion</h2>
        <p>Operational records are retained under the deploying company&apos;s instructions and legitimate business, security, contractual, and legal needs. Backups expire under a controlled retention schedule, so deletion can take time to propagate through encrypted backup generations. Contact your company administrator first for a workforce or fleet record request, or email <a href="mailto:hello@fleetaisystems.com">hello@fleetaisystems.com</a>. Identity must be verified before access, correction, export, or deletion requests are fulfilled, and some records may be retained where legally required.</p>

        <h2>Security and access</h2>
        <p>Fleet AI Systems uses encrypted network transport, hashed PINs and activation secrets, time-limited single-use activation, device binding, lockouts, role and company checks, private evidence storage, audit logging, encrypted offsite backups, and restricted administrative routes. No system can guarantee absolute security; suspected security issues should be reported promptly to the contact above.</p>

        <h2>International processing and changes</h2>
        <p>When a company or user is outside Singapore, using the production service may involve an international transfer of information. The deploying company is responsible for confirming that its notices, authority, contracts, retention rules, and cross-border safeguards fit the people and jurisdictions involved. Material changes to this notice will be published on this page with a revised date.</p>
      </article>
    </main>
  );
}
