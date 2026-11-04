# Sécurité — exigences, état et limites

Légende : ✅ en place et testé · 🟡 partiel · 📐 conçu, pas construit.

## Contrôles en place (Phase 2)

| Exigence | État | Détail / test |
|---|---|---|
| Validation des entrées | ✅ | Pydantic ; les erreurs 422 ne renvoient **jamais la valeur saisie** (`test_validation_error_never_echoes_submitted_value`, mutation vérifiée) |
| Erreurs sans fuite | ✅ | Un 5xx renvoie un message générique + identifiant de requête ; le détail reste dans les journaux (`test_unhandled_exception_returns_generic_500_with_headers`) |
| Secrets hors du code | ✅ | `.env` ignoré par git ; mot de passe BD **généré aléatoirement** par `make setup` ; aucune valeur sensible par défaut ; `SecretStr` |
| Secrets hors des journaux | 🟡 | Masquage par clé et par motif (URL avec mot de passe, `Bearer`, `clé=valeur`, clés `sk-…`), y compris dans les traces d'exception ; la query string n'est jamais journalisée. **Best effort** : la règle reste de ne jamais journaliser un secret |
| Rate limiting | 🟡 | Seau à jetons par adresse client sur `/api/*`, 429 + `Retry-After`. **Limites** : état par processus, et derrière un proxy il faut `--proxy-headers` + `--forwarded-allow-ips` (sinon tous les clients partagent l'IP du proxy). Redis requis en multi-instances |
| En-têtes de sécurité | ✅ | API : `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, `Cache-Control: no-store`, HSTS en production. Web : mêmes bases. `server:` et `x-powered-by` supprimés |
| CORS | ✅ | Origines explicites ; `*` **refusé en production** par validation de la configuration |
| Identifiants de requête | ✅ | Un identifiant entrant n'est repris que s'il est court et sûr (anti-injection de journaux) |
| Base de données | ✅ | Port lié à `127.0.0.1` ; contraintes `CHECK`/`UNIQUE`/clés étrangères testées |
| Conteneurs | ✅ | Processus non-root (uid 10001 / 1000), images multi-étapes |
| Garde-fou destructeur | ✅ | Les tests refusent de toucher une base dont le nom ne finit pas par `_test` ; `make db-reset` demande confirmation |

## Non construit — à ne pas supposer acquis

| Exigence | État |
|---|---|
| Authentification, sessions, rôles appliqués, isolation inter-utilisateurs/organisations | 📐 Phase 3/4 |
| Journaux d'audit | 📐 Phase 4 |
| Coffre de secrets (chiffrement au repos) | 📐 Phase 4+ |
| Contrôle des fichiers importés (taille, type, anti zip-bomb, chemins) | 📐 Phase 4 |
| CSP à nonces (Next.js) | 📐 avec Monaco / React Flow (Phase 6-7) |
| Isolation d'exécution (sandbox), limites de ressources, réseau refusé par défaut | 📐 Phase 9 |
| Agent local : appairage, jetons révocables, liste blanche d'opérations | 📐 Phase 8 |

**Règle ferme** : tant que la Phase 9 n'est pas terminée **et** qu'un niveau d'isolation de production
(gVisor / micro-VM) n'est pas en place, aucune exécution de code d'utilisateur tiers ne sera exposée.

## Risques acceptés

| Risque | Décision |
|---|---|
| 15 alertes `npm audit` modérées (`minimatch`, ReDoS) | Outillage de lint **uniquement** ; absent de l'arbre de production (`npm ls --omit=dev` vide). Ne pas utiliser `npm audit fix --force` (rétrogradations absurdes). Voir [00-AUDIT.md](00-AUDIT.md) |
| Réécritures Next figées au build | Dev uniquement ; en production un reverse proxy route `/api` |

## Signalement

Projet privé en développement : aucune politique de divulgation publique n'est définie à ce stade.
