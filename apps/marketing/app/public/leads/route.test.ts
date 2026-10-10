import { describe, expect, it } from "vitest";

import { POST } from "./route";

function leadRequest(
  body: BodyInit,
  headers: Record<string, string> = {},
): Request {
  return new Request("https://fleetaisystems.com/public/leads", {
    method: "POST",
    body,
    headers: {
      "content-type": "application/json",
      origin: "https://fleetaisystems.com",
      "x-real-ip": `test-${crypto.randomUUID()}`,
      ...headers,
    },
  });
}

describe("public lead route controls", () => {
  it("rejects foreign browser origins before parsing", async () => {
    const response = await POST(
      leadRequest("{}", { origin: "https://attacker.example" }),
    );
    expect(response.status).toBe(403);
  });

  it("rejects declared and streamed oversized bodies", async () => {
    const declared = await POST(
      leadRequest("{}", { "content-length": "9000" }),
    );
    expect(declared.status).toBe(413);

    const streamed = await POST(leadRequest(JSON.stringify({ data: "x".repeat(9_000) })));
    expect(streamed.status).toBe(413);
  });

  it("rejects a filled honeypot without touching storage", async () => {
    const response = await POST(
      leadRequest(
        JSON.stringify({
          name: "Anita Rao",
          company: "Rao Earthworks",
          phone: "+91 98765 43210",
          email: "anita@example.com",
          fleetSize: "11-30",
          fleetType: "mixed",
          message: "Daily site and maintenance coordination.",
          website: "https://bot.example",
        }),
      ),
    );
    expect(response.status).toBe(422);
  });

  it("rate-limits a repeated source without logging its address", async () => {
    const headers = { "x-real-ip": "rate-limit-fixture" };
    for (let attempt = 0; attempt < 5; attempt++) {
      expect((await POST(leadRequest("{}", headers))).status).toBe(422);
    }
    const limited = await POST(leadRequest("{}", headers));
    expect(limited.status).toBe(429);
    expect(limited.headers.get("retry-after")).toBe("600");
  });
});
