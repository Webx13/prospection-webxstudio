import type { Messages } from "./types";

export const fr: Messages = {
  brand: {
    name: "BLACKFORGE",
    tagline: "Forgez vos bots, scripts et automatisations.",
  },
  home: {
    title: "Forgez vos bots, scripts et automatisations.",
    lead: "Plateforme de création, de test et d'exécution isolée pour bots, agents IA et workflows.",
    phaseNote: "Socle technique — l'interface complète arrive avec la phase suivante.",
  },
  status: {
    heading: "État de la plateforme",
    api: "API",
    database: "Base de données",
    version: "Version",
    refresh: "Actualiser",
    refreshing: "Vérification…",
    checkedAt: "Vérifié à",
    states: {
      ok: "Opérationnel",
      degraded: "Dégradé",
      unavailable: "Indisponible",
      unreachable: "Injoignable",
    },
    summary: {
      ok: "Tous les services répondent.",
      degraded: "L'API répond, mais une dépendance est indisponible.",
      unreachable: "L'API ne répond pas. Vérifiez qu'elle est démarrée.",
    },
  },
};
