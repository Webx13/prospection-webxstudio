# Phase 1 — Audit initial

Date : 2026-11-04.

## 1. État du dépôt

| Constat | Détail |
|---|---|
| Dépôt | `webx13/prospection-webxstudio`, branche de travail `claude/adoring-wright-ry1bxx` |
| Historique | 1 commit : « Ajoute l'app de prospection » |
| Contenu | **un seul fichier**, `index.html` (1 065 lignes, JS vanilla) |
| Dossier BLACKFORGE | **inexistant** dans ce dépôt |

`index.html` est un outil interne **sans rapport avec BLACKFORGE** : « Prospection locale — WebXStudio »
(balayage Google Maps de commerces sans site web, scoring, suivi d'appels). Il n'a **pas été modifié**.
Observations rapides, hors périmètre : la clé Google Maps est saisie par l'utilisateur et stockée dans
`localStorage` (elle doit être restreinte par référent HTTP côté Google) ; les polices viennent de
Google Fonts (appel externe).

**Décision (information manquante, solution temporaire documentée).** La demande supposait un dossier
BLACKFORGE existant. N'en trouvant aucun ici, BLACKFORGE est créé dans un sous-dossier autonome
`blackforge/` de ce dépôt, sans toucher à `index.html`. Si un projet BLACKFORGE existe déjà sur votre
Mac, il n'a pas pu être audité : il faudra le rapprocher de ce socle. À terme, BLACKFORGE devrait avoir
son propre dépôt (je ne peux pas en créer un à votre place).

## 2. Environnement d'exécution — ce que j'ai pu et n'ai pas pu vérifier

La demande portait sur « les outils présents sur mon Mac ». Je travaille dans un **conteneur Linux
x86-64 dans le cloud, pas sur votre Mac** : je n'ai donc rien pu inventorier sur votre machine.

| Outil (dans ce conteneur) | Version |
|---|---|
| Node.js / npm | 22.23 / 10.9 |
| Python / uv | 3.13.18 / 0.11.32 |
| Docker / Compose | 29.9 / 5.6 (démon démarré manuellement) |
| PostgreSQL (serveur + client) | 16.15 |
| git, make, curl | 2.43, 4.3, 8.5 |

Conséquence : **la compatibilité Apple Silicon est préparée mais non éprouvée** (voir le README,
section « Compatibilité Apple Silicon »).

## 3. Versions retenues (vérifiées sur les registres, puis à l'usage)

| Composant | Version | Remarque |
|---|---|---|
| Next.js / React | 16.4.5 / 19.3.1 | Turbopack par défaut |
| Tailwind CSS | 4.3.4 | via `@tailwindcss/postcss` |
| TypeScript | **5.9.3** (pas 7.0) | TS 7 (portage natif) trop récent pour l'API compilateur utilisée par Next 16 : prudence |
| ESLint | **10.14** | essayé aussi en 9.39 (signalé « non supporté ») ; les deux passent avec `eslint-config-next` 16.4.5 ; 10 retenu car supporté, et vérifié par une faute volontaire que le linter détecte |
| Vitest / Vite | 5.1 / 8 | requis par `@vitejs/plugin-react` 6 |
| FastAPI / Starlette | 0.162 / 1.10 | |
| Pydantic / pydantic-settings | 2.14 / 2.16 | |
| SQLAlchemy / Alembic | 2.1.8 / 1.20 | |
| Pilote PostgreSQL | psycopg 3.3 | un seul pilote pour l'async (app) et le sync (Alembic) |
| Python | ≥ 3.12 (testé 3.13) | |

## 4. Problèmes identifiés

| # | Problème | Gravité | Statut |
|---|---|---|---|
| 1 | Aucun dossier BLACKFORGE dans le dépôt | Info | Contourné (voir §1) |
| 2 | Environnement ≠ Mac de l'utilisateur | Moyen | Mitigé (verrous multi-arch vérifiés), **non éprouvé** |
| 3 | `npm audit` : 15 alertes modérées | Faible | **Acceptée**, voir ci-dessous |
| 4 | Docker Hub : 429 (limite anonyme) pendant les tests | Info | Environnement ; documenté |
| 5 | Build Docker : proxy HTTPS auto-signé de la sandbox | Info | Environnement ; contourné hors dépôt (aucun changement aux Dockerfiles) |

**Détail #3.** Les 15 alertes sont toutes dans la chaîne ESLint (`minimatch < 11.0.1`, déni de service par
amplification de motifs globaux, GHSA-g3hv-75wg-m249). `npm ls minimatch --omit=dev` est **vide** :
aucune de ces dépendances n'est livrée en production, et les motifs analysés sont ceux de notre propre
configuration. Les « correctifs » proposés par `npm audit fix --force` (`eslint@4`, `eslint-config-next@0.2.4`)
sont des rétrogradations absurdes : **ne pas les appliquer**. À réévaluer à chaque mise à jour d'`eslint-config-next`.

## 5. Bugs trouvés et corrigés pendant la construction

Chacun a été détecté par un test réel, pas par relecture :

1. **Noms de contraintes `CHECK` doublement préfixés** en base (`ck_memberships_ck_memberships_role_allowed`) :
   la convention de nommage SQLAlchemy s'applique aussi dans les migrations → `op.f()`. Alembic ne comparant
   pas les `CHECK`, un test compare désormais les noms en base à ceux des modèles (échec confirmé par mutation).
2. **Test de schéma trompeur** : une base déjà migrée masquait un défaut de migration → le schéma est
   désormais reconstruit de zéro à chaque session de tests.
3. **Image Docker de l'API inutilisable** : `uv sync` installait le projet en mode éditable, l'image finale
   ne contenant pas `/app/src` → `ModuleNotFoundError` au démarrage. Corrigé par `--no-editable`.
4. **Heure affichée dans la langue du navigateur** au lieu de celle de l'application → `toLocaleTimeString(locale)`.
5. **En-tête `server: uvicorn`** divulgué → `--no-server-header`.
