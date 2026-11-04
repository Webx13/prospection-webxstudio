# Gaming AI — architecture et état réel

Légende : ✅ construit et testé · 🟡 amorce / partiel · 📐 conçu, **pas construit**.
Code : [`packages/gaming`](../packages/gaming) — paquet Python **indépendant** de l'API (extras optionnels
`capture`, `vision`, `onnx`).

## 1. Règles de conformité (non négociables)

BLACKFORGE Gaming AI sert à construire des agents pour **vos propres jeux, jeux solo, environnements de
test, serveurs privés et intégrations expressément autorisées**. Le produit ne contient, et ne contiendra,
aucun mécanisme pour : contourner un anti-cheat, masquer une automatisation, lire ou modifier la mémoire
d'un jeu, voler un compte, exploiter une vulnérabilité, ni obtenir un avantage compétitif non autorisé.

| Règle | Comment c'est tenu aujourd'hui | Limite honnête |
|---|---|---|
| Perception uniquement par capture d'écran sanctionnée par l'OS | Seul backend : `mss` (API de capture de l'OS). Aucun accès mémoire, injection ni hook de processus dans le code | Une règle de conception, pas un contrôle technique : rien n'empêche un développeur d'ajouter un backend illicite — d'où la revue de code et le futur registre de plugins |
| Capture avec permission explicite | ✅ `CaptureConsent` obligatoire : un affichage précis (« tous les écrans » refusé), zone optionnelle, durée bornée, cadence max, auteur et finalité journalisés. Vérifié à l'ouverture **et à chaque lecture** | Le consentement est une porte de contrôle + piste d'audit, **pas une barrière contre du code malveillant déjà dans le processus**. Il doit être émis par l'application après confirmation humaine |
| Arrêt d'urgence | ✅ `KillSwitch` partagé, vérifié avant chaque capture ; reste actif jusqu'à `reset()` explicite | Interrompt la prochaine opération, pas une opération déjà en cours dans un détecteur |
| Mode supervisé / autonome, limites d'exécution, permissions d'actions | 📐 Action Engine et Plugin SDK (voir §5) | Rien n'agit encore sur un jeu : **le module ne contrôle ni souris ni clavier** |
| Pas de jeux compétitifs en ligne par défaut | 📐 le manifeste de plugin déclarera `multiplayer` / `competitive` ; l'autonomie sera refusée sans autorisation documentée | Un logiciel ne peut pas juger les CGU d'un jeu : la responsabilité d'usage reste à l'utilisateur. De nombreux jeux interdisent *toute* automatisation, même par capture d'écran |

## 2. Architecture : moteurs remplaçables

Chaque moteur n'implémente qu'un **protocole** défini dans `core` et ne connaît pas les autres moteurs.
Remplacer un moteur = fournir un autre objet respectant le protocole.

```
                      core  (contrats : Frame, Detection, Rect, FrameSource, Detector, KillSwitch)
                       ▲
     ┌─────────────────┼───────────────────┬─────────────────┐
  consent          capture             vision           perception
  (CaptureConsent) (écran, rejeu)  (couleur, gabarit,   (pipeline, ROI,
                                      ONNX/YOLO)         changement)
```

**Frontières vérifiées automatiquement** (`tests/test_replay_architecture_cli.py`, analyse AST du code) :
`vision` et `perception` n'importent que `core` ; `capture` n'importe que `core` et `consent` ; `core` et
`perception` n'importent ni OpenCV, ni mss, ni ONNX Runtime (importer `core`/`perception` ne charge aucune
bibliothèque lourde — testé dans un sous-processus). Seuls `probe.py` et `cli.py` (racine de composition)
assemblent plusieurs moteurs. Ajouter un moteur sans déclarer ses frontières fait échouer le test.

Conventions : image **BGR uint8** (ordre natif OpenCV) ; coordonnées de régions en points logiques,
pixels physiques dans l'image (`Frame.pixel_scale` : 2.0 sur Retina) ; régions d'intérêt en
coordonnées **normalisées** (valables à toute résolution) ; chaque détection porte `score_kind` :
`similarity` (corrélation de gabarit), `heuristic` (taux de remplissage) ou `model_score` (modèle appris,
non calibré) — **ce ne sont pas des probabilités**.

## 3. État des 14 composants demandés

| # | Composant | État | Contenu |
|---|---|---|---|
| 1 | Screen Capture Engine | ✅ prototype | `ScreenCaptureSource` (mss, consentement, cadence, arrêt d'urgence, zone), `ReplaySource` / `record_frames` (PNG sans perte) |
| 2 | Perception Engine | ✅ prototype | `PerceptionPipeline` : détecteurs injectés, régions d'intérêt, **analyse événementielle** (`ChangeDetector`), isolation des pannes de détecteur, latence par étape |
| 3 | Vision Engine | ✅ prototype | `ColorBlobDetector`, `TemplateDetector` (multi-échelle), `OnnxDetector` (famille YOLOv8/11 exportée en ONNX) |
| 4 | OCR Engine | 📐 | Étape suivante. RapidOCR (ONNX) plus léger que PaddleOCR (qui exige PaddlePaddle) : à trancher |
| 5 | Object Tracking | 📐 | `Detection.track_id` réservé ; ByteTrack ou suivi IoU simple à choisir |
| 6 | Game State Manager | 📐 | Consommera `Perception` |
| 7 | AI Game Brain | 📐 | Indépendant des LLM ; règles / machine à états / arbres de décision en local |
| 8 | Strategy Planner | 📐 | Les LLM n'interviennent que pour planifier, jamais par image |
| 9 | Behavior Engine | 📐 | |
| 10 | Action Engine | 📐 | Chaque action passera par un moteur de permissions ; **aucune action n'est implémentée** |
| 11 | Game Plugin System | 📐 | SDK conçu en §5 |
| 12 | Training Lab | 🟡 amorce | Enregistrement/rejeu + `match_boxes` (précision, rappel, IoU) — pour l'instant utilisés par les tests |
| 13 | Game Runtime | 📐 | |
| 14 | Live Monitoring | 📐 | La latence par étape et les erreurs de détecteur sont déjà exposées dans `Perception` |

## 4. Interfaces

```python
class FrameSource(Protocol):          # capture : écran, rejeu, émulateur…
    source_id: str
    def open(self) -> None; def read(self) -> Frame | None; def close(self) -> None   # + context manager

class Detector(Protocol):             # vision : couleur, gabarit, ONNX, votre propre modèle…
    name: str
    def detect(self, image: Image) -> Sequence[Detection]: ...
```

```python
consent = CaptureConsent.grant(purpose="tester mon jeu", granted_by="alice",
                               display_index=1, duration=timedelta(minutes=10), max_fps=30)
red = ColorBlobDetector(name="red", label="enemy", hsv_lower=(170,120,120), hsv_upper=(10,255,255), min_area=400)
pipeline = PerceptionPipeline([DetectorBinding(red)], change_detector=ChangeDetector(threshold=0.002))
with ScreenCaptureSource(consent, kill_switch=kill) as source:
    perception = pipeline.process(source.read())     # → détections, latences, erreurs
```
Exemple exécutable : [`examples/live_detect.py`](../packages/gaming/examples/live_detect.py).
Outils : `make gaming-probe` (capacités réelles), `make gaming-selfcheck ARGS="--i-consent --out c.png"`.

## 5. Conception (non construite) : Plugin SDK et modes d'autonomie

**Manifeste de plugin** (validé par Pydantic, refusé s'il est incomplet ou incohérent) : identité du jeu,
plateforme, version, capacités, APIs, méthodes de capture, actions permises, permissions requises, limites
(durée, cadence, actions/minute), `multiplayer`, `competitive`, et la **source d'autorisation** (jeu de
l'utilisateur, CGU autorisant l'automatisation, serveur privé…). Une liste blanche de capacités ; toute capacité
de type accès mémoire / injection / contournement est **rejetée à la validation**, pas seulement déconseillée.

**Mode supervisé** : observer → analyser → *proposer* → l'utilisateur valide → le moteur de permissions
vérifie → exécution. **Mode autonome** : observer → analyser → décider → permissions → exécution →
**vérification du résultat**. Configurable par projet ; l'arrêt d'urgence et les limites d'exécution
s'appliquent aux deux.

## 6. Mesures réelles (Linux x86-64, 4 cœurs, Xvfb 1280×720, Chromium jouant un jeu de test)

| Mesure | Résultat |
|---|---|
| Capture d'une image 1280×720 (mss/X11) | médiane **≈ 6 ms** |
| Perception complète (2 détecteurs couleur + 1 gabarit plein écran) | p50 **≈ 100 ms**, p95 ≈ 110–160 ms. Le gabarit domine (≈ 170 ms au pire) ; chaque détecteur couleur ≈ 3 ms |
| Image « inchangée » (détection de changement seule) | ≈ 9 ms, détecteurs non exécutés |
| Précision sur la scène de test (3 + 2 carrés, 3 sprites, 1 leurre) | précision 1,0 / rappel 1,0 / IoU moyen 1,0 sur les trois détecteurs |

**À lire avec prudence.** La scène de test est propre, statique et synthétique : ces scores **ne disent rien**
de la détection sur un vrai jeu (anti-crénelage, effets, animations, éclairage). ≈ 100 ms par analyse complète
est **trop lent pour du 30 images/s** : c'est pourquoi l'analyse événementielle existe, et les optimisations
(niveaux de gris, régions d'intérêt, réduction d'échelle, détecteurs natifs) restent à faire.

## 7. Vérifié / non vérifié par plateforme

| | Linux (Xvfb) | macOS Apple Silicon | Windows 11 / CUDA |
|---|---|---|---|
| Capture d'écran (`mss`) | ✅ testée de bout en bout | ❓ **non exécutée**. `mss` supporte macOS ; exige la permission « Enregistrement de l'écran » | ❓ non testée |
| Détection de la permission macOS | n/a | ❓ code écrit d'après l'API CoreGraphics, **jamais exécuté sur Mac** (retourne `unknown` au moindre doute) | n/a |
| OpenCV 4.14, NumPy, Pydantic | ✅ | roues arm64 présentes ; **macOS ≥ 13** | non vérifié |
| ONNX Runtime (CPU) | ✅ plomberie vérifiée (modèle ONNX **fabriqué dans le test**, sortie constante) | roue arm64 présente ; **macOS ≥ 14** | non vérifié |
| Accélération CoreML / CUDA / DirectML | n/a | ❓ sélection du backend codée et testée en logique pure ; **jamais exécutée sur GPU** | ❓ idem (pas de GPU ici) |

Pour valider sur votre Mac (5 minutes) : `make setup`, `make gaming-probe`,
`make gaming-selfcheck ARGS="--i-consent --out ~/check.png"` (signale une image uniforme = permission
manquante), `make test-gaming` (le test d'écran réel s'ignore automatiquement hors Linux/Xvfb).

## 8. Limites connues

* **Aucun poids de modèle fourni, et aucune évaluation sur un vrai jeu.** `OnnxDetector` n'a été éprouvé qu'avec un
  modèle ONNX minimal fabriqué dans le test (sortie constante) : il valide letterbox, retour au repère de
  l'image, décodage, NMS et rejet des formats inattendus — pas la qualité d'un vrai YOLO. Formats gérés :
  YOLOv8/11 `(1, 4+nc, N)`. YOLOv5 (avec « objectness ») et modèles à NMS intégrée sont rejetés explicitement.
* **Licence** : Ultralytics (outils et poids YOLOv8/11) est sous **AGPL-3.0**. Ce paquet n'en dépend pas
  (inférence via ONNX Runtime, MIT). Utiliser des poids AGPL dans un SaaS commercial a des conséquences
  juridiques : **décision à prendre** (modèles sous licence permissive, entraînement propre, ou licence commerciale).
* Détecteur par couleur : aucune notion de forme ni de contexte (une cellule rouge d'un sprite est « rouge » ;
  testé et documenté) ; deux objets de même couleur contigus fusionnent.
* Détecteur par gabarit : sensible à la rotation et aux changements de rendu.
* Capture d'un affichage ou d'une zone **fixe** : une fenêtre qui se déplace n'est pas suivie ; pas de capture
  par fenêtre native (ScreenCaptureKit, Windows Graphics Capture) — `mss` est la base portable, non la plus performante.
* Un petit changement d'écran (ex. un chiffre de score) peut rester sous le seuil du `ChangeDetector` : utiliser
  une région d'intérêt dédiée ou abaisser le seuil.
* Un modèle `.onnx` est un graphe exécuté par ONNX Runtime : ne charger que des modèles de provenance maîtrisée.
* PyTorch n'est pas utilisé à ce stade (inférence via ONNX) ; il servira à l'entraînement et au RL.

## 9. Ordre de développement (suite)

Plan demandé : 1 audit ✅ · 2 architecture ✅ · 3 Plugin SDK · 4 agent local macOS · 5 capture (✅ prototype) ·
6 vision (✅ prototype) · 7 OCR et suivi · 8 état du jeu · 9 cerveau · 10 comportements · 11 actions ·
12 Training Lab · 13 monitoring · 14 Windows/NVIDIA.

Prochaine étape recommandée : **valider la capture sur votre Mac** (§7), puis **OCR + suivi** (étape 7), qui
complètent la perception avant l'état du jeu. Le Plugin SDK (étape 3) est la meilleure occasion d'encoder les règles
de conformité du §1 dans du code ; je propose de le faire juste après la validation Mac.
