import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  metadataBase: new URL("https://fleetaisystems.com"),
  title: {
    default: "Fleet AI Systems | Construction fleet operations",
    template: "%s | Fleet AI Systems",
  },
  description: "Connected construction fleet operations for Owners, Drivers, Operators, and Supervisors—from field capture to maintenance and reporting.",
  applicationName: "Fleet AI Systems",
  keywords: ["construction fleet management", "tipper fleet operations", "machinery operations", "fleet maintenance", "driver workflow"],
  openGraph: {
    type: "website",
    locale: "en_IN",
    siteName: "Fleet AI Systems",
    url: "https://fleetaisystems.com",
    title: "Fleet AI Systems | Clearer construction fleet operations",
    description: "Owner control, field capture, Supervisor review, maintenance, and reporting in one operational system.",
  },
  twitter: {
    card: "summary_large_image",
    title: "Fleet AI Systems | Clearer construction fleet operations",
    description: "Owner control, field capture, Supervisor review, maintenance, and reporting in one operational system.",
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body><Providers>{children}</Providers></body>
    </html>
  );
}
