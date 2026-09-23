import { describe, expect, it } from "vitest";
import { workspaceHintLabel } from "./LoginWorkspace";

describe("login workspace hint", () => {
  it("maps only known QA context values to cosmetic labels", () => {
    expect(workspaceHintLabel("owner")).toBe("OWNER TEST WORKSPACE");
    expect(workspaceHintLabel("supervisor")).toBe("SUPERVISOR TEST WORKSPACE");
    expect(workspaceHintLabel("driver-test")).toBe("DRIVER QA TEST WORKSPACE");
    expect(workspaceHintLabel("admin")).toBeNull();
    expect(workspaceHintLabel(null)).toBeNull();
  });
});
