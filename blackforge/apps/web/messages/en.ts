import type { Messages } from "./types";

export const en: Messages = {
  brand: {
    name: "BLACKFORGE",
    tagline: "Forge your bots, scripts and automations.",
  },
  home: {
    title: "Forge your bots, scripts and automations.",
    lead: "A platform to build, test and run bots, AI agents and workflows in isolated environments.",
    phaseNote: "Technical foundation — the full interface arrives in the next phase.",
  },
  status: {
    heading: "Platform status",
    api: "API",
    database: "Database",
    version: "Version",
    refresh: "Refresh",
    refreshing: "Checking…",
    checkedAt: "Checked at",
    states: {
      ok: "Operational",
      degraded: "Degraded",
      unavailable: "Unavailable",
      unreachable: "Unreachable",
    },
    summary: {
      ok: "All services are responding.",
      degraded: "The API is up, but a dependency is unavailable.",
      unreachable: "The API is not responding. Check that it is running.",
    },
  },
};
