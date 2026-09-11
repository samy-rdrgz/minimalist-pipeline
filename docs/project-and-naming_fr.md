# Structure de projet, nommage, création en masse

*[← Index de la documentation](README.md) · [English version](project-and-naming.md)*

---

## Le projet

Un projet = un dossier avec `config/project_config.json` à sa racine. Structure imposée à la création, configurable dans le wizard :

```
my_project/
├── config/
│   ├── project_config.json
│   ├── logs/pipeline_log.jsonl, sessions_log.jsonl
│   ├── presets/            ← preset Python de collections d'asset, presets ffmpeg
│   ├── .sessions/          ← qui a quoi d'ouvert, en ce moment
│   └── .farm/               ← queue de rendu, workers, monitor.lock
├── refs/
├── assets/
│   └── ch/
│       └── ch_bob/
│           └── .pipeline/   ← tracking.json, .wipmeta, .stablemeta
├── library/
│   └── mat/
│       └── mat_wood-dark/
├── shots/
│   └── sq010/sh010/
├── renders/
└── exports/
```

**Routing par préfixe** : le préfixe du fichier détermine son dossier parent, l'artiste ne choisit rien. `ch`/`pr`/`env` → `assets/`, `mat`/`gn`/`tech` → `library/`. Les deux listes de préfixes sont configurables par projet.

<br>

## Convention de nommage

```
{prefix}_{name}_v{number}[-{tag}].blend      # asset / library
{prefix}sq{n}_{prefix}sh{n}_v{number}[-{tag}].blend   # shot
```

- Tout en minuscules. Underscore = séparateur structurel (toujours 3 segments). Tiret = mots à l'intérieur d'un segment, et tag de version.
- Pas de tag = wip, implicitement.
- La regex de parsing n'est pas figée dans le code : elle est **reconstruite dynamiquement depuis `project_config.json`** (préfixes, digits, tags autorisés) à chaque changement de config.

La variante multishot d'un shot (plusieurs cuts dans un seul fichier) étend ce pattern — voir [Blocs de shots (multishot)](multishot_fr.md).

<br>

## Création en masse

De nouveaux assets/shots peuvent aussi être créés en masse depuis un fichier CSV (bouton "Batch create from CSV" du panneau Projet, ou menu top bar). Chaque ligne est construite dans son propre process Blender headless jetable — jamais la session courante — donc rien ne s'accumule entre les lignes (pas de collections résiduelles d'une ligne précédente) et le travail en cours de l'artiste n'est jamais réinitialisé ni touché. Les lignes sont traitées strictement une par une, jamais en parallèle.

- **Assets** : `prefix`, `name` obligatoires ; `departments`, `description` optionnels.
- **Shots** : `sequence`, `shot` obligatoires ; `frame_start`/`frame_end`/`frame_duration`, `departments`, `description` optionnels (`frame_end` prend le pas sur `frame_duration` si les deux sont donnés ; si aucun des deux n'est donné, le frame range par défaut de la scène n'est pas touché).
- `departments` : noms de départements séparés par des virgules. Retombe sur l'ensemble par défaut du projet si la colonne est vide/absente ; tout nom absent des départements réellement configurés dans le projet est ignoré et loggé en warning — ne bloque jamais la ligne.
- Une ligne correspondant à un asset/shot déjà existant (même prefix+name, ou même sequence+shot) est silencieusement ignorée — la création en masse n'écrase jamais rien.

---

## Structure de données : `project_config.json`

Écrit sous verrou et de façon atomique (fichier temporaire puis renommage), comme tout autre fichier JSON du pipeline (voir [Choix de conception](design_fr.md)). Un par projet, entièrement éditable via "Edit project" :

```json
{
  "project_name": "my_project",
  "pipeline_addon_version": "1.0.3",
  "blender_version": "(4, 2, 0)",
  "resolution": {"x": 1920, "y": 1080},
  "default_fps": 30,
  "default_frame_start": 1001,
  "naming": {
    "sequence": {"prefix": "sq", "digits": 3},
    "shot": {"prefix": "sh", "digits": 3},
    "version": {"prefix": "v", "digits": 3},
    "frame": {"prefix": ".", "digits": 5}
  },
  "structure": {
    "project_folders": ["config", "refs", "assets", "library", "shots", "renders", "exports"],
    "asset_prefixes": ["ch", "pr", "env"],
    "library_prefixes": ["mat", "gn", "tech"]
  },
  "tags": ["stable"],
  "assets_departments": ["modeling", "texturing", "rigging", "tech"],
  "shots_departments": ["layout", "animation", "lighting", "render"],
  "farm": {"max_concurrent_local": 1, "stale_monitor_seconds": 30}
}
```

Tous les préfixes, tags, départements et digits sont libres — c'est ce fichier qui reconstruit la regex de nommage et le routing par dossier à chaque changement. `pipeline_addon_version` est écrit/rafraîchi à chaque création ou édition du projet — pas de logique de migration automatique pour l'instant, juste de quoi savoir plus tard quelle version de l'addon a touché en dernier un config donné.

---

**Voir aussi** : [Versions : wip et stable](versions_fr.md) · [Interface](interface_fr.md) pour le panneau où vivent ces actions.
