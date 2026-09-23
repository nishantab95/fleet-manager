import type { MembershipRole } from "../types";

export const driverQaEnabled = process.env.NEXT_PUBLIC_ENABLE_DRIVER_QA === "true";

export function workspaceForRole(role: MembershipRole, enableDriverQa = driverQaEnabled): string | null {
  if (role === "OWNER_ADMIN") return "/owner";
  if (role === "SUPERVISOR") return "/supervisor";
  return enableDriverQa ? "/driver-test" : null;
}
