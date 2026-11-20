import { auth0 } from "@/lib/auth0";

export async function GET(request: Request, context: { params: Promise<{ runId: string }> }) {
  const session = await auth0.getSession();
  if (!session) return new Response("Unauthorized", { status: 401 });
  const { token } = await auth0.getAccessToken();
  if (!token) return new Response("Missing API access token", { status: 401 });
  const { runId } = await context.params;
  const baseUrl = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1").replace(/\/+$/, "");
  const headers = new Headers({ Authorization: "Bearer " + token, Accept: "text/event-stream" });
  const lastEventId = request.headers.get("Last-Event-ID");
  if (lastEventId) headers.set("Last-Event-ID", lastEventId);
  const upstream = await fetch(baseUrl + "/analytics/runs/" + runId + "/stream", {
    headers, cache: "no-store",
  });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      "Connection": "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
