# Feuille de route — état réel

| Phase | Intitulé | État |
|---|---|---|
| 1 | Audit du projet | ✅ terminée — [00-AUDIT.md](00-AUDIT.md) |
| 2 | Socle fonctionnel | ✅ terminée (hors réserves ci-dessous) |
| 3 | Interface premium | ⬜ à faire |
| 4 | Gestion des projets | ⬜ à faire |
| 5 | AI Builder | ⬜ à faire |
| 6 | Code Studio | ⬜ à faire |
| 7 | Visual Builder | ⬜ à faire |
| 8 | Agent local | ⬜ à faire |
| 9 | Runtime | ⬜ à faire |
| 10 | Préparation SaaS | ⬜ à faire |

## Phase 2 — ce qui est réellement livré

**Vérifié** (exécuté dans cette session, Linux x86-64) :

* API FastAPI : configuration stricte, journaux JSON/texte avec masquage des secrets, enveloppe d'erreur
  sans fuite, identifiant de requête, en-têtes de sécurité, CORS restreint, rate limiting, `/healthz`,
  `/readyz`, `/api/v1/system/status`, OpenAPI. **43 tests** (dont 8 d'intégration sur PostgreSQL réel).
* Base : migration Alembic `0001` (organisations, utilisateurs, appartenances), cycle
  upgrade → downgrade → upgrade testé, aucune dérive modèles/schéma.
* Web : Next.js, thème BLACKFORGE, i18n fr/en typée, page d'état avec rendu serveur et bouton
  « Actualiser » réel. **25 tests**. Vérifié dans Chromium dans 3 états *provoqués pour de vrai* (tout va
  bien, base arrêtée, API arrêtée), sur desktop et mobile 390 px, sans erreur console.
* Docker : images `api` et `web` construites depuis les Dockerfiles du projet, pile complète démarrée
  (`db` → `migrate` → `api` → `web`), healthchecks verts, processus **non-root**.
* Lint et typage : `ruff`, `mypy --strict`, `eslint`, `tsc --strict` propres.

**Réserves — non vérifié ou non fait :**

* **Jamais exécuté sur Mac Apple Silicon.** Seuls les verrous et les images multi-arch ont été contrôlés.
* `make up` n'a pas été exécuté tel quel : le build BuildKit échouait dans cette sandbox (proxy TLS) ; les
  images ont été construites avec le constructeur classique, puis la pile lancée avec `--no-build`.
  Les Dockerfiles sont identiques. Sur votre machine, `make up` devrait fonctionner mais **n'est pas confirmé**.
* Pas d'intégration continue (aucun workflow GitHub Actions n'a été ajouté).
* Pas d'authentification : l'API n'a aucune route protégée car aucune route ne manipule de données.
* Le thème et le logo sont **provisoires** ; la landing et le dashboard sont en Phase 3.

## Prochaine étape — Phase 3 (interface premium)

1. Choix du routage i18n (`/fr`, `/en`) et mise en place.
2. Landing page, navigation, système de composants (boutons, cartes, champs, états vides).
3. Authentification Supabase (inscription, connexion, session, routes protégées) — dépend de la décision 4
   des [questions ouvertes](01-ARCHITECTURE.md#questions-ouvertes-pour-vous).
4. Dashboard et liste/création de projets (interface ; la persistance est la Phase 4).

Chaque bouton aura une action réelle ; ce qui n'est pas construit sera absent, pas simulé.
