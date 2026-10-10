import type { MetadataRoute } from "next";

import { publicRoutes, publicSiteUrl } from "../features/marketing/content";

export default function sitemap(): MetadataRoute.Sitemap {
  return publicRoutes.map((route, index) => ({
    url: `${publicSiteUrl}${route === "/" ? "" : route}`,
    changeFrequency: index === 0 ? "weekly" : "monthly",
    priority: index === 0 ? 1 : route === "/contact" ? 0.8 : 0.7,
  }));
}
