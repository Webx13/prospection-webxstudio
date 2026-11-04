# BLACKFORGE

Plateforme SaaS de création, de test et d'exécution isolée de bots, scripts, agents IA et automatisations.

> **État : Phase 2 terminée (socle technique) + prototype de perception Gaming AI.** Ce dépôt contient une API FastAPI, une base
> PostgreSQL migrée, une interface Next.js et l'outillage Docker. Les fonctionnalités produit
> (AI Builder, Visual Builder, Code Studio, runtime, agent local…) **ne sont pas encore construites** :
> voir la [feuille de route](docs/02-ROADMAP.md) pour l'état réel de chaque phase.

## Prérequis

| Outil | Version | Rôle |
|---|---|---|
| Docker (Desktop sur Mac) | Compose v2 (testé : Docker 29, Compose 5) | PostgreSQL local, pile complète |
| [uv](https://docs.astral.sh/uv/) | 0.11+ | Python et dépendances de l'API (installe Python 3.12+ si absent) |
| Node.js | 22+ | Interface web |
| make, openssl | — | Commandes raccourcies |

Mac Apple Silicon : voir [Compatibilité](#compatibilité-apple-silicon).

## Démarrage rapide

```bash
cd blackforge
make setup     # crée .env (mot de passe BD aléatoire) + installe les dépendances
make db-up     # PostgreSQL 16 dans Docker (port 5432, boucle locale uniquement)
make migrate   # applique les migrations Alembic

make api       # terminal 1 → http://127.0.0.1:8000   (docs : /api/v1/docs)
make web       # terminal 2 → http://localhost:3000
```

Ou toute la pile en conteneurs : `make up` (db + migrations + api + web), `make down` pour l'arrêter.

`make help` liste toutes les commandes.

## Gaming AI (prototype de perception)

Capture d'écran soumise à consentement + détection visuelle, indépendants de l'API. **Rien n'agit sur un jeu.**

```bash
make gaming-probe                                            # capacités réelles de votre machine
make gaming-selfcheck ARGS="--i-consent --out ~/check.png"   # capture UNE image de votre écran
make test-gaming                                             # 105 tests (écran réel : Linux + Xvfb + Chromium)
```

Jamais exécuté sur Mac à ce jour : lancez ces trois commandes et signalez le résultat. Détails, mesures et limites :
[docs/04-GAMING-ARCHITECTURE.md](docs/04-GAMING-ARCHITECTURE.md).

## Vérifier que tout fonctionne

```bash
make test      # API (43 tests, dont intégration sur PostgreSQL réel) + web (25) + gaming (105)
make lint      # ruff, mypy strict, eslint, tsc
```

Points de contrôle manuels :

| URL | Attendu |
|---|---|
| `http://127.0.0.1:8000/healthz` | `{"status":"ok"}` — le processus répond (sans base) |
| `http://127.0.0.1:8000/readyz` | `200` si la base répond, `503` sinon |
| `http://127.0.0.1:8000/api/v1/system/status` | version + état de la base |
| `http://127.0.0.1:8000/api/v1/docs` | documentation OpenAPI interactive |
| `http://localhost:3000` | page d'accueil avec l'état de la plateforme (bouton « Actualiser » réel) |

## Structure

```
blackforge/
├── apps/
│   ├── api/    FastAPI · Pydantic v2 · SQLAlchemy 2 async · Alembic · PostgreSQL
│   └── web/    Next.js 16 · React 19 · Tailwind 4 · TypeScript strict
├── packages/
│   └── gaming/ Gaming AI : capture d'écran (consentement), vision, perception (prototype)
├── docs/       audit, architecture, feuille de route, sécurité, architecture gaming
├── docker-compose.yml
├── Makefile
└── .env.example
```

## Configuration

Toute la configuration passe par des variables d'environnement (`.env`, jamais commité).
Référence complète et commentée : [`.env.example`](.env.example). Aucune clé de fournisseur d'IA
n'est requise à ce stade ; le mode démo (Phase 5) fonctionnera sans clé.

## Compatibilité Apple Silicon

Le projet est conçu pour être développé sur Mac Apple Silicon. **Il n'a pas encore été exécuté sur
un Mac** (le développement initial s'est fait dans un conteneur Linux x86-64). Ce qui a été vérifié :

* `uv.lock` contient des roues macOS arm64 pour toutes les dépendances natives (psycopg-binary,
  pydantic-core, uvloop, httptools, watchfiles…) ;
* `package-lock.json` contient les binaires darwin-arm64 et linux-arm64 de Next, Tailwind, lightningcss ;
* les images de base (`postgres:16-alpine`, `python:3.13-slim`, `node:22-bookworm-slim`) sont multi-architectures.

Si un problème apparaît au premier lancement sur Mac, c'est un défaut à corriger : merci de le signaler.

## Dépannage

* **`make db-up` : port 5432 occupé** — un PostgreSQL local tourne déjà (ex. Homebrew). Arrêtez-le ou
  changez `POSTGRES_PORT` **et** les URLs dans `.env`.
* **`.env contient encore __GENERATE__`** — supprimez `.env` et relancez `make setup`.
* **`docker pull` : 429 Too Many Requests** — limite anonyme de Docker Hub ; connectez-vous
  (`docker login`) ou patientez.
* **`make up` : le web affiche « Injoignable »** — l'URL de l'API est figée au *build* de l'image web
  (`API_INTERNAL_URL`, voir [architecture](docs/01-ARCHITECTURE.md#frontières-et-flux-de-requêtes)).
