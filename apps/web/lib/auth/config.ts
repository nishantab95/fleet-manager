import type { MembershipRole } from "../types";

export const driverQaEnabled = process.env.NEXT_PUBLIC_ENABLE_DRIVER_QA === "true";
export function isPcRoleLabEnabled(enableDriverQa: boolean, nodeEnvironment: string | undefined): boolean {
  return enableDriverQa && nodeEnvironment !== "production";
}

export const pcRoleLabEnabled = isPcRoleLabEnabled(driverQaEnabled, process.env.NODE_ENV);

export function workspaceForRole(role: MembershipRole, enableDriverQa = driverQaEnabled): string | null {
  if (role === "OWNER_ADMIN") return "/owner";
  if (role === "SUPERVISOR") return "/supervisor";
  return enableDriverQa ? "/driver-test" : null;
}
