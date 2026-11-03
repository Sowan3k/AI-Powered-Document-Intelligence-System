// Client for the DocIntel REST API. The browser calls the API directly
// (DECISIONS.md D14). NEXT_PUBLIC_API_BASE_URL is inlined at build time, so
// Vercel must have it set before it builds.

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"
).replace(/\/+$/, "");

export type HealthResponse = {
  status: "ok" | "degraded";
  database: "connected" | "unavailable";
  database_latency_ms: number | null;
  environment: string;
  version: string;
};

export type HealthResult =
  | { kind: "healthy"; body: HealthResponse }
  | { kind: "degraded"; body: HealthResponse }
  | { kind: "unreachable"; reason: string };

// A sleeping Render free instance can take close to a minute to wake up.
export const HEALTH_TIMEOUT_MS = 90_000;

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResult> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/health`, {
      cache: "no-store",
      signal,
    });
  } catch (error) {
    const aborted = error instanceof DOMException && error.name === "AbortError";
    return {
      kind: "unreachable",
      reason: aborted ? "The API did not answer in time." : "The API could not be reached.",
    };
  }

  // The API answers 503 with a JSON body when the database is down.
  if (response.status !== 200 && response.status !== 503) {
    return { kind: "unreachable", reason: `The API answered with status ${response.status}.` };
  }
  try {
    const body = (await response.json()) as HealthResponse;
    const healthy = body.status === "ok" && body.database === "connected";
    return healthy ? { kind: "healthy", body } : { kind: "degraded", body };
  } catch {
    return { kind: "unreachable", reason: "The API sent a response that is not valid JSON." };
  }
}
