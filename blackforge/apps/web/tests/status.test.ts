import { describe, expect, it, vi } from "vitest";

import { fetchStatus, parseStatus, UNREACHABLE } from "@/lib/status";

const OK_PAYLOAD = {
  service: "blackforge-api",
  version: "0.1.0",
  api_version: "v1",
  status: "ok",
  database: "ok",
};

function jsonResponse(body: unknown, init?: ResponseInit): Response {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

describe("parseStatus", () => {
  it("accepte une réponse valide", () => {
    expect(parseStatus(OK_PAYLOAD)).toEqual({
      kind: "reachable",
      overall: "ok",
      version: "0.1.0",
      database: "ok",
    });
  });

  it("accepte l'état dégradé", () => {
    expect(parseStatus({ ...OK_PAYLOAD, status: "degraded", database: "unavailable" })).toEqual({
      kind: "reachable",
      overall: "degraded",
      version: "0.1.0",
      database: "unavailable",
    });
  });

  it.each([
    ["null", null],
    ["une chaîne", "ok"],
    ["un statut inconnu", { ...OK_PAYLOAD, status: "great" }],
    ["une version manquante", { status: "ok", database: "ok" }],
    ["une base inconnue", { ...OK_PAYLOAD, database: "maybe" }],
    ["une version non textuelle", { ...OK_PAYLOAD, version: 1 }],
  ])("rejette %s", (_label, payload) => {
    expect(parseStatus(payload)).toEqual(UNREACHABLE);
  });
});

describe("fetchStatus", () => {
  it("appelle l'endpoint versionné sans cache", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(OK_PAYLOAD));
    await fetchStatus({ baseUrl: "http://api:8000", fetchImpl });
    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api:8000/api/v1/system/status");
    expect(init.cache).toBe("no-store");
  });

  it("utilise la même origine quand baseUrl est vide", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(OK_PAYLOAD));
    await fetchStatus({ fetchImpl });
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("/api/v1/system/status");
  });

  it("retourne l'état lu quand tout va bien", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(OK_PAYLOAD));
    expect(await fetchStatus({ fetchImpl })).toMatchObject({ kind: "reachable", overall: "ok" });
  });

  it("retourne « injoignable » sur erreur réseau", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError("fetch failed"));
    expect(await fetchStatus({ fetchImpl })).toEqual(UNREACHABLE);
  });

  it("retourne « injoignable » sur statut HTTP d'erreur", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ error: {} }, { status: 502 }));
    expect(await fetchStatus({ fetchImpl })).toEqual(UNREACHABLE);
  });

  it("retourne « injoignable » sur JSON invalide", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response("<html>oops</html>", { status: 200 }));
    expect(await fetchStatus({ fetchImpl })).toEqual(UNREACHABLE);
  });

  it("abandonne après le délai imparti", async () => {
    const fetchImpl = vi.fn(
      (_input: RequestInfo | URL, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => reject(new DOMException("timeout")));
        }),
    );
    const result = await fetchStatus({ fetchImpl, timeoutMs: 20 });
    expect(result).toEqual(UNREACHABLE);
  });
});
