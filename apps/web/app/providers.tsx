"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";
import { AuthProvider } from "../features/auth/AuthProvider";

export function Providers({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const needsOperationsSession = ["/login", "/owner", "/supervisor", "/driver-test", "/lab", "/evidence"].some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
  return needsOperationsSession ? <AuthProvider>{children}</AuthProvider> : children;
}
