import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: {
    default: "Fleet AI Systems | Private operations",
    template: "%s | Fleet AI Systems",
  },
  description: "Private Fleet AI Systems operations workspace.",
  applicationName: "Fleet AI Systems",
  robots: { index: false, follow: false, nocache: true },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body><Providers>{children}</Providers></body>
    </html>
  );
}
