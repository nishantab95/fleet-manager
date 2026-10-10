import type { ReactNode } from "react";

import { PageFrame } from "../../features/marketing/MarketingChrome";
import "./marketing.css";

export default function MarketingLayout({ children }: { children: ReactNode }) {
  return <PageFrame>{children}</PageFrame>;
}
