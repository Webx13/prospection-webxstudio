# blackforge-gaming

Moteurs **Gaming AI** de BLACKFORGE : capture d'écran soumise à consentement, détection visuelle,
pipeline de perception. Paquet Python indépendant de l'API.

> Prototype de perception. Rien n'agit sur un jeu : ni souris, ni clavier, ni manette.
> Architecture, limites, mesures et état par plateforme : [`docs/04-GAMING-ARCHITECTURE.md`](../../docs/04-GAMING-ARCHITECTURE.md).

## Installation

```bash
uv sync --all-extras          # capture (mss) + vision (OpenCV) + onnx (ONNX Runtime)
uv run pytest                 # 175 tests ; les tests d'écran réel exigent Linux + Xvfb + Chromium
```

Extras : `capture` (mss), `vision` (OpenCV), `onnx` (ONNX Runtime). Le cœur ne dépend que de NumPy et Pydantic.
Prérequis macOS : **macOS 14+** (ONNX Runtime), permission « Enregistrement de l'écran » pour capturer.

## Outils en ligne de commande

```bash
uv run blackforge-gaming probe                                   # capacités RÉELLES de cette machine
uv run blackforge-gaming selfcheck-capture --i-consent --out c.png   # capture UNE image
uv run python examples/live_detect.py --i-consent --frames 20    # capture + détection en direct
uv run blackforge-gaming plugin validate plugins/blackforge-test-game   # valide un plugin de jeu
```

`selfcheck-capture` refuse de capturer sans `--i-consent` et signale une image uniforme (écran noir, ou
permission macOS manquante : l'OS ne renvoie alors aucune erreur).

## Structure

```
src/blackforge_gaming/
├── core/         contrats : Frame, Detection, Rect/NormRect, FrameSource, Detector, KillSwitch
├── consent/      CaptureConsent (périmètre, durée, cadence, audit)
├── capture/      ScreenCaptureSource (mss), ReplaySource, record_frames
├── vision/       ColorBlobDetector, TemplateDetector, OnnxDetector (+ NMS, décodage YOLO)
├── perception/   PerceptionPipeline, ChangeDetector, RegionOfInterest, RollingStats
├── plugin/       Game Plugin SDK : manifeste, vocabulaire fermé, politique, chargeur sûr (DONNÉES)
├── probe.py      racine de composition : rapport de capacités
├── assemble.py   racine de composition : plugin → pipeline de perception
└── cli.py        commandes ci-dessus
```

Les frontières entre moteurs sont **vérifiées par un test** (analyse AST) : un moteur ne dépend que de `core`
(et `capture` de `consent`). SDK de plugins : [`docs/05-PLUGIN-SDK.md`](../../docs/05-PLUGIN-SDK.md).
