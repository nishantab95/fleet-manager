import type { NextConfig } from "next";

const developmentScriptPolicy = process.env.NODE_ENV === "development" ? " 'unsafe-eval'" : "";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          {
            key: "Content-Security-Policy",
            value: `default-src 'self'; connect-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'${developmentScriptPolicy}; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'`,
          },
        ],
      },
    ];
  },
};

export default nextConfig;
