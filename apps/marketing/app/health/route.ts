export const dynamic = "force-dynamic";

export async function GET() {
  return Response.json(
    { status: "ok", service: "fleet-ai-systems-marketing" },
    {
      headers: {
        "Cache-Control": "no-store",
      },
    },
  );
}
