import type { MetadataRoute } from "next";

import { publicSiteUrl } from "../features/marketing/content";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: ["/", "/features", "/how-it-works", "/solutions", "/pricing", "/contact"],
      disallow: ["/api/", "/owner", "/supervisor", "/driver-test", "/lab", "/login", "/evidence/"],
    },
    sitemap: `${publicSiteUrl}/sitemap.xml`,
    host: publicSiteUrl,
  };
}
