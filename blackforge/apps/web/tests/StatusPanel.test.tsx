import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StatusPanel } from "@/components/StatusPanel";
import { getMessages } from "@/lib/i18n";
import { UNREACHABLE, type PlatformStatus } from "@/lib/status";

const t = getMessages("fr").status;

const OK: PlatformStatus = { kind: "reachable", overall: "ok", version: "0.1.0", database: "ok" };
const DEGRADED: PlatformStatus = {
  kind: "reachable",
  overall: "degraded",
  version: "0.1.0",
  database: "unavailable",
};

afterEach(() => vi.unstubAllGlobals());

function stubFetchWith(body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("StatusPanel", () => {
  it("affiche l'état opérationnel, la version et le résumé", () => {
    render(<StatusPanel initial={OK} messages={t} locale="fr" />);
    expect(screen.getByText(t.summary.ok)).toBeInTheDocument();
    expect(screen.getByText("0.1.0")).toBeInTheDocument();
    expect(screen.getAllByText(t.states.ok)).toHaveLength(2); // API + base de données
  });

  it("affiche l'état dégradé quand la base est indisponible", () => {
    render(<StatusPanel initial={DEGRADED} messages={t} locale="fr" />);
    expect(screen.getByText(t.states.degraded)).toBeInTheDocument();
    expect(screen.getByText(t.states.unavailable)).toBeInTheDocument();
    expect(screen.getByText(t.summary.degraded)).toBeInTheDocument();
  });

  it("affiche « injoignable » sans inventer de version ni d'état de base", () => {
    render(<StatusPanel initial={UNREACHABLE} messages={t} locale="fr" />);
    expect(screen.getByText(t.states.unreachable)).toBeInTheDocument();
    expect(screen.getByText(t.summary.unreachable)).toBeInTheDocument();
    expect(screen.getAllByText("—")).toHaveLength(2);
  });

  it("le bouton Actualiser interroge réellement l'API et met l'affichage à jour", async () => {
    const fetchMock = stubFetchWith({
      status: "ok",
      version: "9.9.9",
      database: "ok",
      service: "blackforge-api",
      api_version: "v1",
    });
    render(<StatusPanel initial={UNREACHABLE} messages={t} locale="fr" />);

    await userEvent.click(screen.getByRole("button", { name: t.refresh }));

    await waitFor(() => expect(screen.getByText("9.9.9")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/system/status");
    expect(screen.getByText(t.summary.ok)).toBeInTheDocument();
    expect(screen.getByText(new RegExp(t.checkedAt))).toBeInTheDocument();
  });

  it("repasse en « injoignable » si l'API tombe pendant l'actualisation", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));
    render(<StatusPanel initial={OK} messages={t} locale="fr" />);

    await userEvent.click(screen.getByRole("button", { name: t.refresh }));

    await waitFor(() => expect(screen.getByText(t.summary.unreachable)).toBeInTheDocument());
  });

  it("désactive le bouton pendant la vérification", async () => {
    let release: (response: Response) => void = () => {};
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>((resolve) => (release = resolve))),
    );
    render(<StatusPanel initial={OK} messages={t} locale="fr" />);

    await userEvent.click(screen.getByRole("button", { name: t.refresh }));
    expect(screen.getByRole("button", { name: t.refreshing })).toBeDisabled();

    release(new Response("{}", { status: 500 }));
    await waitFor(() => expect(screen.getByRole("button", { name: t.refresh })).toBeEnabled());
  });
});
