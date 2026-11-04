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

---

# Gaming AI (pilier stratégique) — état réel

Détail, interfaces, mesures et limites : [04-GAMING-ARCHITECTURE.md](04-GAMING-ARCHITECTURE.md).

| Étape | Intitulé | État |
|---|---|---|
| 1 | Audit | ✅ (capacités de la machine, licences : AGPL d'Ultralytics, versions macOS minimales) |
| 2 | Architecture gaming | ✅ moteurs indépendants, frontières vérifiées par test |
| 3 | Game Plugin SDK | 📐 conçu, non construit |
| 4 | Agent local macOS | 📐 (Phase 8 de la feuille de route générale) |
| 5 | Screen Capture Engine | ✅ prototype — **vérifié sur Linux/Xvfb ; jamais exécuté sur Mac** |
| 6 | Vision Engine | ✅ prototype (couleur, gabarit, adaptateur ONNX/YOLO) — **aucun modèle réel évalué** |
| 7 | OCR et suivi | 📐 |
| 8–13 | État du jeu, cerveau, comportements, actions, Training Lab, monitoring | 📐 (Training Lab : amorce enregistrement/rejeu + métriques) |
| 14 | Windows / NVIDIA | 📐 sélection du backend d'accélération codée, jamais exécutée sur GPU |

**Livré et vérifié** (Linux x86-64) : 97 tests unitaires + 8 tests de bout en bout sur une **vraie capture** (Xvfb +
Chromium jouant un jeu de test, vérité terrain exacte) ; ruff et mypy `--strict` propres ; frontières d'architecture
vérifiées ; 5 garanties de sécurité/exactitude éprouvées par mutation (consentement revérifié, arrêt d'urgence, cadence
maximale, résolution changée, décalage du letterbox).

**Réserves** : aucun contrôle de jeu (ni souris, ni clavier, ni manette) n'existe ; la détection n'a été mesurée que sur une
scène synthétique propre ; ≈ 100 ms par analyse complète 1280×720 sur ce CPU (trop lent pour du temps réel image par image,
d'où l'analyse événementielle) ; pas d'intégration à l'API, à l'interface web ni au WebSocket de monitoring.

**Prochaine étape** : vous exécutez `make gaming-probe` et `make gaming-selfcheck` sur votre Mac (5 minutes, voir le §7 du
document d'architecture), puis Plugin SDK (conformité encodée dans du code), puis OCR et suivi.
