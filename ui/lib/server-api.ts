// Server-only: forwards browser requests to the private Cloud Run API.
// On Cloud Run the UI's service account mints a Google-signed ID token for the
// API's URL (audience), so the API never has to be public.
import { GoogleAuth } from "google-auth-library";

const API_URL = (process.env.API_URL || "http://localhost:8080").replace(/\/$/, "");
const USE_ID_TOKEN = API_URL.startsWith("https://") && process.env.API_AUTH !== "none";

let auth: GoogleAuth | null = null;

async function authHeader(): Promise<Record<string, string>> {
  if (!USE_ID_TOKEN) return {};
  auth ??= new GoogleAuth();
  const client = await auth.getIdTokenClient(API_URL);
  const headers: unknown = await client.getRequestHeaders();
  const value =
    headers instanceof Headers
      ? headers.get("authorization")
      : (headers as Record<string, string>)["Authorization"] ?? (headers as Record<string, string>)["authorization"];
  return value ? { Authorization: value } : {};
}

// Only these API paths are reachable through the proxy.
const ALLOWED = /^(health|transactions|analytics\/(categories|monthly)|budgets\/status|alerts|chat|categorize(\/accuracy)?|receipts)$/;

export async function forward(req: Request, path: string[]): Promise<Response> {
  const joined = path.join("/");
  if (!ALLOWED.test(joined)) {
    return Response.json({ detail: "Not found" }, { status: 404 });
  }
  const url = new URL(req.url);
  const target = `${API_URL}/${joined}${url.search}`;
  const headers: Record<string, string> = { ...(await authHeader()) };
  const contentType = req.headers.get("content-type");
  if (contentType) headers["Content-Type"] = contentType;

  const init: RequestInit = { method: req.method, headers, cache: "no-store" };
  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.arrayBuffer();
  }
  try {
    const res = await fetch(target, init);
    return new Response(res.body, {
      status: res.status,
      headers: { "Content-Type": res.headers.get("content-type") ?? "application/json" },
    });
  } catch (err) {
    console.error("API request failed", target, err);
    return Response.json({ detail: "The SmartSpend API is unreachable." }, { status: 502 });
  }
}
