/** Client de l'endpoint GET /api/v1/system/status, tolérant aux pannes et aux réponses invalides. */

export type DependencyState = "ok" | "unavailable";

export type PlatformStatus =
  | { kind: "reachable"; overall: "ok" | "degraded"; version: string; database: DependencyState }
  | { kind: "unreachable" };

export const UNREACHABLE: PlatformStatus = { kind: "unreachable" };

const STATUS_PATH = "/api/v1/system/status";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** Valide la forme de la réponse : on ne fait jamais confiance à un JSON distant. */
export function parseStatus(payload: unknown): PlatformStatus {
  if (!isRecord(payload)) return UNREACHABLE;
  const { status, database, version } = payload;
  if ((status !== "ok" && status !== "degraded") || typeof version !== "string") {
    return UNREACHABLE;
  }
  if (database !== "ok" && database !== "unavailable") return UNREACHABLE;
  return { kind: "reachable", overall: status, version, database };
}

export interface FetchStatusOptions {
  /** Origine de l'API (ex. http://127.0.0.1:8000). Vide = même origine (proxy Next). */
  baseUrl?: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

export async function fetchStatus(options: FetchStatusOptions = {}): Promise<PlatformStatus> {
  const { baseUrl = "", timeoutMs = 3000, fetchImpl = fetch } = options;
  try {
    const response = await fetchImpl(`${baseUrl}${STATUS_PATH}`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!response.ok) return UNREACHABLE;
    return parseStatus(await response.json());
  } catch {
    return UNREACHABLE;
  }
}
