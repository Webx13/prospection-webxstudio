# Architecture

Légende : ✅ construit et testé · 📐 conçu, **pas construit**.

## Principes

1. **Le code utilisateur et le code généré par IA sont non fiables.** Ils ne s'exécutent jamais dans le
   processus de l'API (📐 imposé par l'architecture du runtime, ci-dessous).
2. **Isolation par organisation dès le schéma** : toute table métier portera `organization_id`.
3. **Aucun fournisseur d'IA codé en dur** ; le mode démo fonctionne sans clé.
4. **Local d'abord, gratuit d'abord** : tout se développe sans service payant ni compte externe.
5. **Pas de fausse fonctionnalité** : un module non construit n'a ni bouton ni route.

## Vue d'ensemble

```
                 ┌────────────── cloud (ou local en dev) ───────────────┐
 navigateur ───► │ web (Next.js) ──► api (FastAPI) ──► PostgreSQL        │ ✅
                 │                      │                                │
                 │                      ├──► couche IA multi-fournisseurs │ 📐 Phase 5
                 │                      └──► service runtime (isolé)      │ 📐 Phase 9
                 └──────────────────────────▲───────────────────────────┘
                                            │ connexion SORTANTE (TLS)
                              agent local BLACKFORGE (Mac, puis Windows) 📐 Phase 8
```

## Frontières et flux de requêtes

* **Navigateur → web** : pages Next.js. Le web n'a **aucun secret** et ne parle pas à la base.
* **Navigateur → API** : en développement, via les réécritures Next `/api/v1/* → API` (même origine, pas de
  CORS). Ces réécritures sont **figées au build** (`API_INTERNAL_URL`) — d'où l'argument de build dans
  `apps/web/Dockerfile`. En production, un reverse proxy (Caddy/nginx) routera `/api` vers l'API et `/` vers
  le web ; les réécritures ne serviront plus.
* **Web (serveur) → API** : rendu serveur de l'état de la plateforme, via `API_INTERNAL_URL` lue à l'exécution.
* **API → PostgreSQL** : SQLAlchemy 2 async + psycopg 3, pool avec `pre_ping`.

Sondes : `/healthz` (liveness, sans dépendance) et `/readyz` (readiness : 503 si la base ne répond pas),
hors `/api/v1` et **non soumises au rate limiting**. `/api/v1/system/status` alimente l'interface.

## Décisions

| # | Décision | Alternative écartée | Raison |
|---|---|---|---|
| D1 | Monorepo `apps/api` + `apps/web` | Deux dépôts | Un seul contexte pour un projet porté par une personne |
| D2 | psycopg 3 (async + sync) | asyncpg + psycopg2 | Un seul pilote ; Alembic reste synchrone et simple |
| D3 | Alembic, migrations écrites à la main, noms de contraintes explicites | Autogénération aveugle | Revue possible ; schéma = contrat (test de dérive + test de noms) |
| D4 | `pydantic-settings`, aucune valeur sensible par défaut, `SecretStr` | Défauts « de dev » dans le code | Un défaut finit en production |
| D5 | Middlewares ASGI purs | `BaseHTTPMiddleware` | Pas de défauts avec flux/tâches de fond ; le filet 500 doit vivre *dans* la pile pour porter les en-têtes |
| D6 | Rate limiting en mémoire (seau à jetons) | Redis dès maintenant | Zéro dépendance pour démarrer ; limites connues (voir 03-SECURITY) |
| D7 | i18n : catalogues typés `fr`/`en`, parité vérifiée à la compilation | `next-intl` immédiatement | Choix du routage par locale repoussé à la Phase 3 (landing) |
| D8 | UUID générés par PostgreSQL (`gen_random_uuid()`) | UUID côté app | Pas de dépendance à l'application pour l'identité |
| D9 | Rôles par `CHECK` sur texte | Type ENUM PostgreSQL | Les ENUM sont pénibles à migrer |
| D10 | Pas de CSP pour l'instant | CSP stricte immédiate | Monaco/React Flow injectent styles et workers : CSP à nonces à introduire avec eux |

## Modèle de données

✅ Migration `0001` : `organizations`, `users` (e-mail unique insensible à la casse, `auth_subject` pour
Supabase), `memberships` (rôle `owner|admin|member|viewer`, unique par couple organisation/utilisateur,
suppression en cascade).

📐 Phase 4 et suivantes : `projects`, `project_files`, `project_versions`, `executions`, `execution_logs`,
`connectors`, `secrets` (chiffrés, jamais renvoyés en clair), `quotas`, `subscriptions`, `audit_logs`,
`machines` (agent local).

## Composants à construire — conception

### Authentification (📐 Phase 3/4)
Supabase Auth (gratuit en local via la CLI Supabase). L'API **vérifie** les JWT (signature, expiration,
audience) et mappe `sub` → `users.auth_subject`. Mode « développement » à définir sans Supabase (jeton de
dev signé localement, désactivé en production par validation de configuration). Autorisation :
appartenance + rôle vérifiés côté API sur chaque requête ; jamais déléguée au front.

### Couche IA (📐 Phase 5)
Interface `LLMProvider` (génération, flux, outils) avec adaptateurs Anthropic, OpenAI, Ollama et un
`DemoProvider` déterministe (aucune clé, aucun réseau). Clés lues côté serveur uniquement. **Le code généré
est traité comme non fiable** : analyse statique et revue avant toute exécution ; l'IA ne prétend jamais
qu'un projet fonctionne sans l'avoir testé dans le runtime.

### Runtime d'exécution (📐 Phase 9)
Service **séparé** de l'API (autre processus, autre réseau), interrogé via une file de tâches. Par exécution :
environnement éphémère, limites CPU / mémoire / durée / processus, système de fichiers dédié, **réseau
refusé par défaut** (autorisation explicite par exécution), journaux structurés, arrêt d'urgence, destruction
de l'environnement. **Docker seul n'est pas une frontière de sécurité** : le contrat du runtime est une
interface `Sandbox` avec une implémentation conteneur durcie (utilisateur non-root, `no-new-privileges`,
capabilities supprimées, seccomp, système de fichiers en lecture seule) pour le développement, et un
emplacement prévu pour gVisor ou Firecracker (micro-VM) en production. Tant que le niveau d'isolation de
production n'est pas en place, l'exécution de code tiers ne sera **pas** exposée à d'autres utilisateurs.

### Agent local (📐 Phase 8)
Binaire pour macOS arm64 (Windows ensuite) qui n'écoute **sur aucun port**. Appairage par code à usage
unique affiché dans l'interface et saisi dans l'agent → jeton d'appareil révocable et limité à une
organisation. Connexion **sortante** TLS vers l'API ; réception de tâches **dont le type appartient à une
liste blanche** ; aucun shell distant ; exécution via le même contrat `Sandbox` avec limites de ressources ;
journaux masqués (`core/redaction.py` déjà en place côté API) ; aucun envoi de fichier hors dossier de tâche.

### Hybride cloud / PC
Le cloud porte interface, API, comptes, projets. Le PC porte l'agent, les modèles locaux (Ollama) et les
exécutions autorisées. Aucun achat de matériel requis : tout est développable sur le Mac seul ; le support
Windows 11 / GPU NVIDIA est une cible de l'agent, pas un prérequis.

## Questions ouvertes (pour vous)

1. BLACKFORGE doit-il rester dans ce dépôt (`blackforge/`) ou avoir son propre dépôt ?
2. Existe-t-il déjà un dossier BLACKFORGE sur votre Mac à intégrer ?
3. Hébergement cible de la production (le budget de 100 € oriente le choix : VPS vs services managés) ?
4. Supabase : projet cloud gratuit, ou instance locale uniquement pendant le développement ?
