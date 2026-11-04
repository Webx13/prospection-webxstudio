/** Contrat de traduction : chaque langue doit fournir exactement ces clés (vérifié à la compilation). */
export interface Messages {
  brand: {
    name: string;
    tagline: string;
  };
  home: {
    title: string;
    lead: string;
    phaseNote: string;
  };
  status: {
    heading: string;
    api: string;
    database: string;
    version: string;
    refresh: string;
    refreshing: string;
    checkedAt: string;
    states: {
      ok: string;
      degraded: string;
      unavailable: string;
      unreachable: string;
    };
    summary: {
      ok: string;
      degraded: string;
      unreachable: string;
    };
  };
}
