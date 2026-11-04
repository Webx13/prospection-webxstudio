# Game Plugin SDK

Ajouter un jeu à BLACKFORGE = fournir un **dossier de données** validé, sans toucher au cœur.
Code : [`packages/gaming/src/blackforge_gaming/plugin`](../packages/gaming/src/blackforge_gaming/plugin).
Exemple réel et validé : [`packages/gaming/plugins/blackforge-test-game`](../packages/gaming/plugins/blackforge-test-game).

```bash
uv run blackforge-gaming plugin validate plugins/blackforge-test-game        # code retour 0 = accepté
uv run blackforge-gaming plugin validate mon-plugin --json                   # sortie machine
```

## 1. Principes

1. **Un plugin est de la donnée, pas du code.** `plugin.json` + fichiers référencés (gabarits PNG, modèles ONNX).
   Le charger n'exécute **aucun** code tiers (testé : un `evil.py` placé dans le dossier n'est ni importé ni exécuté).
2. **Vocabulaire fermé.** Capacités, méthodes de capture, actions et permissions viennent d'énumérations. Il n'existe
   aucune valeur pour « lire la mémoire », « injecter », « contourner un anti-cheat » ou « masquer l'automatisation » :
   elles **ne peuvent pas s'exprimer**, un manifeste qui les mentionne est refusé. Un test garantit qu'aucun terme de ce type
   n'entre un jour dans le vocabulaire.
3. **Structure stricte.** Champ inconnu = refus ; types non coercés (`"30"` n'est pas `30`) ; formats et plafonds vérifiés.
4. **Politique de conformité** évaluée avant tout usage (règles ci-dessous).
5. **Intégrité.** Chaque fichier référencé est scellé par son SHA-256, confiné au dossier du plugin (pas de `..`, de chemin
   absolu ni de lien symbolique sortant) et de taille bornée.

## 2. Contenu du manifeste (`plugin.json`)

| Section | Champs | Rôle |
|---|---|---|
| Identité | `manifest_version` (=1), `id` (`editeur.nom-du-jeu`), `name`, `version` (X.Y.Z), `publisher` (auteur du plugin), `description` | Qui est le plugin |
| `game` | `title`, `publisher?`, `platforms` (windows/macos/linux/web), `mode`, `competitive`, `anti_cheat` (none/present/unknown) | Quel jeu, dans quel contexte |
| `authorization` | `kind`, `evidence?` | **Pourquoi** automatiser ce jeu est légitime (déclaratif) |
| `capabilities` | `detect_objects`, `recognize_interface`, `read_text`, `track_objects` | Ce que le plugin utilise |
| `apis` | `name`, `kind` (official / local_test_harness), `url?` | APIs disponibles |
| `capture_methods` | `display`, `screen_region`, `official_api`, `replay_file` | Comment observer |
| `actions` | `type`, `max_per_minute` (≤ 300), `confirm_in_supervised` | Actions permises |
| `permissions` | `capture.screen`, `input.mouse`, `input.keyboard`, `input.gamepad`, `network.official_api`, `storage.recordings` | Permissions requises |
| `limits` | `max_session_seconds` (≤ 4 h), `max_fps` (≤ 60), `max_actions_per_minute` (≤ 300), `autonomous_allowed`, `default_autonomy` | Limites d'utilisation |
| `vision` | `regions` (normalisées), `detectors` (color / template / onnx), `change_threshold`, `max_stale_frames` | Quoi détecter, où |
| `files` | `{chemin relatif: sha256}` | Scellé des gabarits et modèles |

`mode` : `single_player`, `test_environment`, `user_developed`, `private_server`, `online_multiplayer`.
`authorization.kind` : `own_game`, `offline_single_player`, `test_environment`, `private_server_operator`,
`publisher_permission`, `terms_permit_automation`.

## 3. Règles de conformité

**Refus (bloquant)**

| Code | Règle |
|---|---|
| P001 | L'autorisation doit être compatible avec le mode (ex. un jeu `user_developed` n'admet que `own_game`) |
| P002 | `private_server_operator`, `publisher_permission` et `terms_permit_automation` exigent une **preuve** (`evidence`) |
| P003 | Multijoueur en ligne : seule une permission de l'éditeur ou des CGU autorisant explicitement l'automatisation |
| P004 | Jeu compétitif : permission explicite de l'éditeur (`publisher_permission`) |
| P005 | Jeu compétitif : mode autonome **interdit** |
| P006 | Anti-cheat présent **ou inconnu** : permission explicite de l'éditeur avec preuve ; BLACKFORGE ne contourne ni ne neutralise aucun anti-cheat |
| P007 | Anti-cheat présent ou inconnu : mode autonome interdit |
| P008 | Chaque action et chaque méthode de capture exige sa permission déclarée |
| P009 | `test_harness_command` réservé aux modes `test_environment` et `user_developed` |
| P010 | Le débit d'une action ne peut dépasser la limite globale |
| P011 | `default_autonomy = autonomous` exige `autonomous_allowed` |
| P012 | Un profil de vision exige une capacité de vision déclarée |
| P013 | Tout fichier référencé doit être scellé (SHA-256) |
| P014 | Aucun fichier scellé sans référence (surface inutile) |

**Intégrité et chargement** : S001 manifeste trop gros · S002 JSON invalide · S003 structure invalide · S004 `plugin.json`
introuvable · S005 chemin hors du dossier · S006 fichier introuvable · S007 fichier trop gros · S008 empreinte différente
(fichier altéré).

**Avertissements** : W001 capacité déclarée mais pas encore fournie par les moteurs (`read_text`, `track_objects`) ·
W002 permission déclarée mais inutilisée (moindre privilège) · W003 saisie en mode autonome à vérifier.

## 4. Autonomie par projet

Le manifeste fixe ce qui est **permis** ; chaque projet choisit son mode dans cette limite.
`resolve_autonomy(manifest, demandé)` retourne le mode effectif et **lève `PolicyDeniedError`** si l'autonomie est demandée
sur un plugin qui ne l'autorise pas : jamais de dégradation silencieuse. Un projet peut toujours être plus strict
(supervisé) que le plugin.

## 5. Du plugin au pipeline

```python
plugin = load_plugin(Path("plugins/blackforge-test-game"))        # valide, applique la politique, vérifie les SHA-256
pipeline = build_pipeline(plugin)                                 # détecteurs et régions construits depuis la donnée
consent = CaptureConsent.grant(..., max_fps=plugin.manifest.limits.max_fps)   # la cadence suit les limites du plugin
```
Vérifié de bout en bout sur une **capture réelle** (Xvfb + Chromium) : le pipeline construit uniquement depuis le plugin
retrouve la vérité terrain (précision et rappel 1,0 sur les trois détecteurs).

## 6. Limites — à lire

* **L'autorisation est déclarative.** BLACKFORGE ne peut pas vérifier qu'un éditeur a donné sa permission, qu'un jeu n'a
  pas d'anti-cheat, ni qu'un serveur est bien privé. La politique impose une déclaration explicite, cohérente, assortie
  d'une preuve et journalisable — pas qu'elle soit vraie. La responsabilité d'usage reste à l'utilisateur.
* **Le scellé SHA-256 détecte l'altération, pas la malveillance.** Un éditeur de plugin malhonnête scelle ses propres
  fichiers. Une vraie confiance exige des signatures et un registre revu humainement : **non construits**.
* **Les actions déclarées sont inertes.** Il n'existe pas encore d'Action Engine : aucun plugin ne peut déclencher la
  moindre souris, touche ou manette. Les déclarations (actions, permissions, limites de débit) sont validées et prêtes pour
  le jour où il existera. L'interface d'octroi de permissions par l'utilisateur n'existe pas non plus.
* Un plugin ne peut pas ajouter de **nouveau type de détecteur** ni de comportement : il configure ceux qui existent
  (couleur, gabarit, ONNX). C'est le prix de « donnée seulement » ; des plugins avec code exigeraient un bac à sable.
* Un modèle `.onnx` scellé reste un graphe exécuté par ONNX Runtime : ne l'utiliser que si sa provenance est maîtrisée.
* Les plafonds du SDK (300 actions/min, 60 images/s, 4 h) sont des choix prudents, non dérivés d'une mesure.

## 7. Garanties éprouvées par mutation

Chaque protection a été désactivée volontairement pour vérifier qu'un test échoue : règle anti-cheat (P006), règle
multijoueur (P003), rejet des `..`, confinement après résolution (liens symboliques), contrôle d'empreinte, refus
d'autonomie (pas de dégradation silencieuse), champs inconnus, ajout d'une notion interdite au vocabulaire. Deux de ces
vérifications ont d'abord **survécu** (couche redondante non testée isolément ; bytecode périmé faussant un résultat) :
elles ont été corrigées avant de conclure.
