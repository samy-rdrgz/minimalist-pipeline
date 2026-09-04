# Versions : wip et stable

*[← Index de la documentation](README.md) · [English version](versions.md)*

---

Publier = tagger `-stable`, pas un fichier séparé à écraser. Les links pointent vers une version stable précise ; passer à une version plus récente est une action explicite (voir [Link vs Append](linking_fr.md)).

- **`-stable` est le seul tag avec un comportement pipeline réel** (verrouillage en lecture seule à l'ouverture, garde à la sauvegarde). Les autres tags que vous ajoutez au config (`tocheck`, `tovalid`...) sont purement informatifs.
- **Ouverture d'un fichier en lecture seule** (`-stable`, `always_read_only`, ou déjà en lecture seule plus tôt dans cette session) : marqué silencieusement, sans popup — juste l'indicateur rouge READ-ONLY de la barre du haut (voir [Interface](interface_fr.md)), à cliquer à tout moment pour voir la raison et incrémenter en un clic. Ouvrir un fichier déjà verrouillé par un autre poste reste le seul cas qui interrompt immédiatement avec une popup, parce que savoir qui le détient est une info en direct que l'indicateur ne peut pas porter à lui seul.
- **Auto-version à l'ouverture** : si le fichier ouvert est la dernière version *et* date d'avant aujourd'hui, l'addon l'incrémente silencieusement (aucun travail perdu, aucune interruption). S'il existe déjà une version plus récente que celle ouverte, une popup propose de repartir de ce fichier plus ancien (`branch_from`) plutôt que d'incrémenter dans le vide.
- **Incrémenter / marquer stable** : même opérateur (`pipeline.increment_version`), avec ou sans tag. La popup pré-coche "travaillé cette session" avec ce qui est déjà coché dans le panneau asset/shot (voir [Sessions et verrouillage](sessions-and-locking_fr.md)), et les départements probablement finis (validés au dernier stable, non retouchés depuis). La sidebar masque "Mark as stable" quand le fichier ouvert est déjà la version stable — le retagger stable ne servirait à rien.
- **Garde à la sauvegarde** (Ctrl+S, raccourci remplacé par l'addon) : si le fichier est verrouillé en lecture seule pour cette session — parce qu'il est `-stable`, parce qu'un autre poste l'a déjà ouvert, ou parce que `always_read_only` est actif — la sauvegarde directe est interceptée et remplacée par une popup (Save / Increment / Cancel sur un fichier stable, Save & Increment / Cancel sinon).

---

## Structures de données : `.wipmeta` et `.stablemeta`

Chaque asset/shot a un dossier `.pipeline/` à côté de ses fichiers `.blend`, contenant un de ces fichiers par version (voir [Suivi & revues](tracking-and-reviews_fr.md) pour le troisième fichier de ce dossier, `tracking.json`). Le nom du fichier sidecar lui-même retire le nom de base de l'asset/shot — déjà porté par le dossier parent — et ne garde que version+tag : `ch_bob_v004.blend` se suit donc via `.pipeline/v004.wipmeta`, pas `.pipeline/ch_bob_v004.wipmeta`. Ça compte surtout sur les blocs multishot, où le nom de base grandit avec chaque numéro de shot couvert.

**`.pipeline/v004.wipmeta`** — une par version de travail :

```json
{
  "file": "assets/ch/ch_bob/ch_bob_v004.blend",
  "created_from": "assets/ch/ch_bob/ch_bob_v003.blend",
  "creation_mode": "manual_incrementation",
  "created_at": "2026-03-25T16:00:00",
  "edited_at": "2026-03-25T18:42:00",
  "departments_worked": {"84213_a1b2c3d4e5f6": ["rigging"]},
  "linked": [
    {"file": "library/mat/mat_wood-dark/mat_wood-dark_v002-stable.blend", "type": "MATERIAL", "name": "wood_dark"}
  ]
}
```

`creation_mode` vaut `creation` (première version), `auto_increment` / `branch_from` (proposés à l'ouverture) ou `manual_incrementation`. `departments_worked` est indexé par session (`pid_machine_id`) pour agréger correctement même si un fichier est travaillé par plusieurs personnes le même jour.

<br>

**`.pipeline/v005-stable.stablemeta`** — une par version marquée stable :

```json
{
  "file": "assets/ch/ch_bob/ch_bob_v005-stable.blend",
  "created_from": "assets/ch/ch_bob/ch_bob_v004.blend",
  "created_at": "2026-03-26T10:00:00",
  "departments_validated": {"modeling": true, "rigging": true, "texturing": false},
  "linked": [],
  "conflict_warning": ""
}
```

C'est ce fichier qui sert de point de référence : tout le calcul "qu'est-ce qui a été retouché depuis le dernier stable" (affiché dans les panneaux Tracking et le monitoring projet) compare les `.wipmeta` postérieurs à `created_at` contre ce `departments_validated`.

---

**Voir aussi** : [Rendu (farm)](farm_fr.md) pour le lien entre la sortie d'un job et la version du fichier · [Choix de conception](design_fr.md) pour le pourquoi du JSON plutôt qu'une base de données.
