# Plan 1.2 — récapitulatif des modifications

*État au 14/11/2026, à partir de la 1.1.10 (branche `claude/tender-tesla-ov9148`). Rien n'est codé : ce document fixe les décisions prises et l'architecture retenue. Les points marqués **[à confirmer]** restent à trancher.*

Hypothèse de départ, validée : **tous les PC sont mis à jour en même temps.** Le code qui gère des machines sur des versions différentes peut donc disparaître.

---

## 1. Pourquoi l'addon pèse ×3,1 depuis la v1

Contenu du zip (sans docs) : **444 Ko en 1.0.1 → 1 398 Ko en 1.1.10**. Les commentaires n'y sont pour rien : ils passent de 10 à 13 % des lignes. Le code Python réel passe de 9 400 à 22 800 lignes.

| Fonctionnalité | v1.0.1 | 1.1.10 | Part de la croissance |
|---|---|---|---|
| Snapshot HTML + reviews (page web, import json **et** xlsx, générateur xlsx) | 6 Ko | 302 Ko | 31 % |
| Farm (chunks, reprise, priorités, previews, panneau de 1 111 lignes) | 116 Ko | 351 Ko | 25 % |
| Suivi (validations, RTK, notes, scan du projet) | 96 Ko | 230 Ko | 14 % |
| Base (fichiers, versions, projet) | 226 Ko | 324 Ko | 10 % |
| **CHANGELOG.md embarqué dans le zip** | 0 | 94 Ko | 10 % |
| Fenêtres de monitoring + log | 0 | 59 Ko | 6 % |
| Maintenance, rushes | 0 | 37 Ko | 4 % |

Côté farm, les protections (causes d'échec, frames bloquées, frames corrompues, coupures du partage, priorités) sont justifiées et on les garde. Ce qui pèse, c'est l'interface et la mécanique des previews écrite en double.

---

## 2. Architecture retenue

On se libère de l'architecture actuelle sur trois points. Ce sont eux qui rendent les nouvelles fonctionnalités simples au lieu de les empiler.

### 2.1 Un moteur d'états unique (`lib/status.py`) et son jumeau dans la page

**Problème :** l'état d'un département (pas commencé, en cours, fini, validé, retravaillé depuis…) est calculé à plusieurs endroits :
- en Python : `lib/tracking.py` `_status_from_raw()`, les infobulles des panneaux, la colonne Farm ;
- en JavaScript, dans `page.js`.

Ajouter « Waiting », « À reprendre » et les stats en direct pendant une review à chacun de ces endroits multiplierait les risques d'écart.

**Solution :**
- **Une fonction pure** prend les *faits* d'un fichier et rend l'état de chaque département avec sa raison. Les faits sont :
  - les départements requis et les étapes ;
  - les sessions de travail par département ;
  - les stables et leurs validations ;
  - les RTK avec leurs dates d'ouverture et de fermeture ;
  - les rendus par département ;
  - les « toujours valide » (voir 2.2).
  
  Le panneau latéral, le Project monitoring, File details, la colonne Farm et l'export du snapshot l'utilisent tous.
- **La même fonction en JavaScript dans `page.js`**, alimentée par les mêmes faits, que l'export écrit dans la page. Elle sert aux stats en direct : la page recalcule les états en appliquant la review en cours.
- **Des cas de test communs** : un fichier JSON de cas (des faits en entrée, les états attendus en sortie), vérifié par les tests Python **et** par ceux du JS. C'est ce qui garantit que les deux versions ne divergent pas.

### 2.2 La hiérarchie des départements : calculée, avec un seul fait stocké

**Configuration** : une clé à part, sans toucher aux listes de départements existantes.

```json
"department_stages": {
  "shots":  {"layout": 1, "animation": 2, "fx": 3, "lighting": 3, "render": 4},
  "assets": {"modeling": 1, "texturing": 2, "rigging": 2, "tech": 3}
}
```

- Même numéro : départements en parallèle.
- Pas de clé : pas de hiérarchie, les projets existants ne changent pas.
- Dans Edit project : un champ « étape » à côté de chaque département.
- Un département non requis pour le fichier est sauté.

**Les deux états calculés :**

| État | Quand | Raison affichée |
|---|---|---|
| **Waiting** | une étape inférieure a un RTK ouvert, ou n'est pas commencée | « Waiting : layout RTK » / « Waiting : layout pas commencé » |
| **À reprendre** | une étape inférieure **a changé** après la dernière **remise à jour** de ce département | « À reprendre : layout changé le 12/11 » |

- Un département déjà commencé ou fini **passe aussi en Waiting**, avec le nom du département qui le bloque. Son état réel reste visible dans le détail.
- **Rien n'est bloqué**, c'est de l'information. Au plus, un avertissement quand on valide ou qu'on lance le rendu d'un département en Waiting.

**Le fait stocké : la dernière remise à jour de chaque département.** Ce qui posait problème : une fois le RTK du layout fermé, comment dire que l'animation n'a *pas besoin* d'être refaite, sans faire un stable ou un rendu, et sans entrée par RTK, illisible quand il y en a plusieurs ?

La réponse est de ne pas raisonner par RTK, mais avec **une seule date par département et par fichier** :

```json
"departments_synced": {"animation": {"at": "2026-11-12T15:02:00", "by": "léa"}}
```

- **« Changement en amont »** = un RTK de l'étape inférieure est fermé, ou un nouveau stable est fait avec cette étape travaillée alors qu'elle était déjà finie. Une simple sauvegarde de travail en cours ne compte pas : sinon la moindre retouche signalerait tout l'aval.
- **Remise à jour du département**, qui fait disparaître « À reprendre » :
  - automatique : une session de travail sur ce département, ou un rendu tagué à son nom, après le changement ;
  - manuelle : **un bouton « Toujours valide »** sur le département, dans File details, le panneau latéral et la page HTML (qui le transmet comme action de review). Il enregistre la date, l'auteur et éventuellement une note.
- **Plusieurs RTK en amont ne posent pas de problème** : la date couvre tous les changements jusqu'à maintenant. Un nouveau changement après cette date fait revenir « À reprendre ».
- Seuls les départements **commencés** peuvent être « À reprendre ». Un département pas encore commencé partira de toute façon de la dernière version.

**[à confirmer]** Pour un département de rendu (lighting, render), la remise à jour automatique serait-elle *uniquement* un nouveau rendu tagué à son nom, et pas une simple session de travail ?

### 2.3 Une review = une liste d'actions typées (fin du format tableur)

**Problème :** le `.json` d'une review garde la forme du tableur xlsx : une ligne par fichier, une colonne par département, des colonnes `reply <id>`, des cellules à interpréter (`page.js` `FIXED`, `lib/review_import.py`, 665 lignes, 27 fonctions). L'xlsx ne sert plus.

**Solution :** un nouveau format de review (nouveau `schema_version`), une simple liste d'actions :

```json
{"format": "...", "schema_version": 3, "project": "...", "snapshot": "...",
 "author": "...", "role": "sup", "review_date": "2026-11-14",
 "actions": [
   {"type": "validate",    "file": "shots/sq080/sh010", "department": "animation"},
   {"type": "unvalidate",  "file": "...", "department": "..."},
   {"type": "rtk",         "file": "...", "departments": ["layout"], "text": "...", "shot": "sh010", "frames": "12-40", "render": "v006-stable_001"},
   {"type": "note",        "file": "...", "text": "..."},
   {"type": "reply",       "to": "<id d'une note>", "text": "..."},
   {"type": "fixed",       "id": "<id d'un RTK>"},
   {"type": "description", "file": "...", "old": "...", "new": "..."},
   {"type": "departments", "file": "...", "add": ["fx"], "remove": []},
   {"type": "still_valid", "file": "...", "department": "animation", "text": "..."},
   {"type": "create",      "kind": "shot", "sequence": "sq080", "name": "sh090", "description": "...",
                           "frame_start": 1001, "frame_end": 1120, "departments": ["layout", "animation"]}
 ]}
```

- **L'import = un aiguillage** : une petite fonction par type d'action. La fenêtre de confirmation les liste par type.
- `create` passe par le **moteur de création existant** (`lib/batch.py`, celui qu'utilise le CSV) : un seul endroit crée des fichiers, avec les mêmes règles de nommage et les mêmes modèles.
- Doublons : une action déjà importée est ignorée (identifiant d'action). Un `create` déjà existant est ignoré lui aussi : `shot_batch_exists()` le vérifie déjà.
- Les reviews de l'ancien format sont refusées, comme aujourd'hui pour une autre version du schéma.

---

## 3. Les phases de travail

### Phase 1 — Nettoyage et factorisation (rien de visible, sauf une popup)

| # | Tâche | Où |
|---|---|---|
| 1.1 | Retirer `CHANGELOG.md` du zip (`paths_exclude_pattern`) | `blender_manifest.toml` |
| 1.2 | Retirer l'xlsx : générateur, import, lecture | `lib/review_sheet.py`, `lib/review_import.py`, opérateurs, docs |
| 1.3 | Retirer le code de compatibilité **entre versions de l'addon** : worker sur un ancien protocole, libellés « older addon », demandes sans chunks | `farm/*`, `panels/farm_panel.py`, ~43 endroits repérés |
| 1.4 | **[à confirmer]** Anciennes **données** de projet (validations d'avant la 1.1.9, historiques sans preset…) : *migration unique* (un bouton dans Maintenance qui réécrit les vieux fichiers, puis on retire les lectures de compatibilité dans la version suivante) **ou** on garde ces lectures | `lib/tracking.py` (`_legacy_carried`…), `farm/loop.py` |
| 1.5 | **Un seul circuit demande → processus → résultat entre l'hôte et un worker**, en deux variantes (rendu, preview) : on garde les previews sur worker, on supprime la mécanique en double (~80-100 lignes) | `farm/workers.py`, `farm/post_render.py` |
| 1.6 | Le panneau farm **en boucles** : listes de champs pour les détails d'un job et d'un worker, sur le même principe que les listes connues à l'avance | `panels/farm_panel.py` (1 111 lignes) |
| 1.7 | « Quelle machine a rendu quelle frame » dans un **bouton + popup** | `panels/farm_panel.py` |
| 1.8 | Fonctions d'affichage partagées : « libellé + champ » ; « boutons si peu de choix, sinon menu déroulant » (4 fois) ; le bloc description / départements / fichier vierge des fenêtres de création d'asset et de shot | `operators/asset_ops.py`, `shot_ops.py`, `browser_ops.py`, `lib/browser.py` |
| 1.9 | Une seule version des petites fonctions : lecture d'une date ISO (17 `try/except` + 4 fonctions locales), affichage d'une durée (`_duration`, `format_duration`, `pace._clock`), lecture de la sortie de `ffmpeg -i` (`_video_info`, `_frame_size`) | `lib/core.py` ou `lib/` |
| 1.10 | Un petit cache commun pour « relire un fichier seulement s'il a changé » (`history`, `preset_pace`, d'autres caches maison) | `farm/loop.py`, `lib/` |
| 1.11 | Une fonction unique pour ajouter une étape à un job : remplace les 18 `stage_history.append(...)` écrits à la main, en plus de `mark_stage()` | `farm/*` |
| 1.12 | Vérifier les 5 lancements d'un Blender en arrière-plan (setup, création par lot, vignettes, rendu worker) : une seule fonction si possible | `farm/setup.py`, `lib/batch.py`, `farm/post_render.py`, `farm/workers.py` |

Méthode : une nouvelle branche, un commit par tâche, un test après chaque factorisation (le comportement ne doit pas changer), et le poids du zip mesuré avant et après.

### Phase 2 — Rangement des snapshots et des reviews

- **Copie de la review** : après un import réussi depuis Blender, copie du fichier original dans `snapshots/reviews/<rôle>/`. Le nom contient déjà la date, le rôle et l'auteur. Le même fichier n'est pas recopié ; un fichier différent du même nom reçoit un suffixe ; rien n'est copié si l'import est annulé. *Import review* ouvre son sélecteur sur `snapshots/reviews/`.
- **Snapshots rangés par mois** : `snapshots/2026-11/…html`.
  - **Un seul dossier `snapshots/videos/`**, que la page trouve via `../videos` : sinon chaque mois aurait sa propre copie de toutes les vidéos (le mode *Folder* écrit aujourd'hui `videos/` à côté du snapshot, `tracking_ops.py:1207`).
  - Le chemin relatif vers `renders/` est calculé à l'export : les nouveaux snapshots s'adaptent tout seuls.
  - **Les anciens snapshots restent à la racine** : les déplacer casserait leurs chemins vers les vidéos.

### Phase 3 — Moteur d'états et hiérarchie des départements

- `lib/status.py` (2.1), branché partout où un état est affiché. On remplace les calculs actuels au lieu d'en ajouter.
- `department_stages` dans la config, avec le champ « étape » dans Edit project.
- Les états **Waiting** et **À reprendre** (2.2), et `departments_synced` dans `tracking.json`.
- Le bouton **« Toujours valide »** dans File details et le panneau latéral.
- Les nouvelles marques dans la légende : panneau, Project monitoring, page snapshot.

### Phase 4 — La page HTML : nouveau format de review, créations, stats en direct

- Le format **actions typées** (2.3), écrit par `page.js` et lu par un nouvel import.
- Dans la page :
  - **« + shot » par séquence, « + asset » par préfixe** : nom (validé avec les règles de nommage exportées dans la page), description, plage de frames, départements requis. Le futur shot ou asset apparaît en « prévu » jusqu'à l'import. Tout le monde peut créer ; l'auteur et le rôle sont notés.
  - **Ajouter ou retirer des départements requis** sur un fichier existant.
  - **« Toujours valide »** sur un département « À reprendre ».
  - **Stats en direct** : les %, les compteurs et les états recalculés par le moteur JS en appliquant la review en cours (« avec ta review : 64 % (+3) »).
- Le jumeau JS du moteur et les cas de test communs.

### Phase 5 — Rendus par département

- **Le département vient du nom du preset**, sans aucun champ à saisir :
  - on prend le **nom de département le plus long** par lequel commence le nom du preset, suivi de `_`, `-` ou de rien, sans tenir compte des majuscules ;
  - un nom de département peut contenir `_` (seule la virgule le découpe dans Edit project), d'où le « plus long » : `look_dev_hd` → *look_dev* ;
  - aucun département trouvé : le rendu n'a pas de département ;
  - Edit project affiche, à côté de chaque preset, le département qu'il donne.
- Stocké dans le job, puis dans `render_history.json`. Le nom des dossiers de rendu ne change pas.
- **Un « to check » par shot et par département** : un nouveau rendu du même département remplace l'ancien, pas celui d'un autre département. Ça touche la colonne Farm, File details, *Checked* et son Ctrl+clic, le snapshot, les rushes, et la lecture des anciens fichiers (rangés par shot seul, considérés sans département).
- **Un dernier rendu par département** dans File details et dans le snapshot (« layout v003 · animation v005 · lighting v006 »). Les anciens rendus apparaissent sans département.
- *Checked* précoche le département du rendu au lieu de « render ».
- Un rendu tagué compte comme remise à jour de son département dans le moteur d'états (2.2).

---

## 4. Questions encore ouvertes

1. **Phase 1.4** : migration unique des anciennes données de projet, ou on garde leur lecture ?
2. **2.2** : pour un département de rendu, la remise à jour automatique se fait-elle uniquement par un nouveau rendu tagué ?
3. **2.2** : le « Toujours valide » est-il ouvert à tous, ou réservé à certains rôles ?
4. **Phase 2** : les reviews rangées aussi par mois dans `snapshots/reviews/<rôle>/` ? Le nom du fichier commence déjà par la date.

## 5. Effet attendu sur le poids

- **Phase 1** : −94 Ko (CHANGELOG), environ −600 lignes (xlsx), environ −80 à 100 lignes (previews), les retraits de compatibilité, et le panneau farm en boucles, qui devrait être le plus gros gain, de l'ordre de quelques centaines de lignes (estimation grossière). Le poids sera mesuré avant et après.
- **Phases 3 à 5** : elles ajoutent du code, surtout le moteur d'états et son jumeau JS. Mais ce moteur *remplace* les calculs d'états répartis aujourd'hui, et le format en actions rend l'import plus simple que l'actuel.
