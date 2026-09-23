import { describe, expect, it } from "vitest";
import { isPcRoleLabEnabled, workspaceForRole } from "../../lib/auth/config";

describe("role workspace routing", () => {
  it("routes owner and supervisor memberships to their dedicated workspaces", () => {
    expect(workspaceForRole("OWNER_ADMIN", false)).toBe("/owner");
    expect(workspaceForRole("SUPERVISOR", false)).toBe("/supervisor");
  });

  it("only routes drivers to the explicitly enabled QA workspace", () => {
    expect(workspaceForRole("DRIVER", false)).toBeNull();
    expect(workspaceForRole("DRIVER", true)).toBe("/driver-test");
  });

  it("keeps the PC Test Lab disabled in production", () => {
    expect(isPcRoleLabEnabled(true, "production")).toBe(false);
    expect(isPcRoleLabEnabled(true, "development")).toBe(true);
    expect(isPcRoleLabEnabled(false, "development")).toBe(false);
  });
});
