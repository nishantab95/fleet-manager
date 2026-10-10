import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Fleet AI Systems",
    short_name: "Fleet AI",
    description: "Construction fleet operations software.",
    start_url: "/",
    display: "standalone",
    background_color: "#f5f7f4",
    theme_color: "#0b3a37",
    icons: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml" }],
  };
}
