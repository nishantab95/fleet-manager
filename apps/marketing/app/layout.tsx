import type { Metadata } from "next";
import type { ReactNode } from "react";

import { PageFrame } from "../components/MarketingChrome";
import "./marketing.css";

const siteUrl = "https://fleetaisystems.com";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "Fleet AI Systems | Construction Fleet Management Software",
    template: "%s | Fleet AI Systems",
  },
  description:
    "Construction fleet management for tippers and machinery, connecting Owners, Drivers, Supervisors, maintenance, sites, and daily operations.",
  applicationName: "Fleet AI Systems",
  keywords: [
    "construction fleet management",
    "tipper fleet software",
    "construction machinery maintenance",
    "driver operations",
    "supervisor approvals",
    "multi-site fleet operations",
  ],
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    locale: "en_IN",
    siteName: "Fleet AI Systems",
    url: siteUrl,
    title: "Fleet AI Systems | Construction Fleet Management Software",
    description:
      "Coordinate Owners, Drivers, Supervisors, Sites, and Machines in one operational workflow.",
  },
  twitter: {
    card: "summary_large_image",
    title: "Fleet AI Systems | Construction Fleet Management Software",
    description:
      "Coordinate Owners, Drivers, Supervisors, Sites, and Machines in one operational workflow.",
  },
};

export default function MarketingLayout({ children }: { children: ReactNode }) {
  const structuredData = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        "@id": `${siteUrl}/#organization`,
        name: "Fleet AI Systems",
        url: siteUrl,
        logo: `${siteUrl}/icon.svg`,
      },
      {
        "@type": "SoftwareApplication",
        "@id": `${siteUrl}/#software`,
        name: "Fleet AI Systems",
        applicationCategory: "BusinessApplication",
        operatingSystem: "Web, Android",
        description:
          "Construction fleet operations software for Owners, Drivers, Supervisors, Sites, machines, maintenance, and reporting.",
        url: siteUrl,
        publisher: { "@id": `${siteUrl}/#organization` },
      },
    ],
  };

  return (
    <html lang="en">
      <body>
        <PageFrame>{children}</PageFrame>
        <script
          dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData).replace(/</g, "\\u003c") }}
          type="application/ld+json"
        />
      </body>
    </html>
  );
}
