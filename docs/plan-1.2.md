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

La réponse est de ne pas raisonner par RTK, mais avec **une seule date par département et par fichier**, dans le `.pipeline/tracking.json` du dossier :

```json
"departments_synced": {"animation": {"at": "2026-11-12T15:02:00+01:00", "by": "léa"}}
```

**« À reprendre » n'est stocké nulle part**, pas plus que « Waiting ». Le moteur d'états les recalcule à chaque lecture en comparant des dates qui existent déjà :
- la fermeture des RTK (`done_at`, dans `tracking.json`) ;
- les stables (`.stablemeta`) ;
- les sessions de travail par département (`.wipmeta`) ;
- les rendus par département (`render_history.json`, phase 5) ;
- `departments_synced`, le seul ajout.

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
   {"type": "assign",      "file": "...", "department": "animation", "people": ["tom"]},
   {"type": "omit",        "file": "...", "state": "omit", "reason": "coupé au montage"},
   {"type": "create",      "kind": "shot", "sequence": "sq080", "name": "sh090", "description": "...",
                           "frame_start": 1001, "frame_end": 1120, "departments": ["layout", "animation"]}
 ]}
```

- **L'import = un aiguillage** : une petite fonction par type d'action. La fenêtre de confirmation les liste par type.
- `create` passe par le **moteur de création existant** (`lib/batch.py`, celui qu'utilise le CSV) : un seul endroit crée des fichiers, avec les mêmes règles de nommage et les mêmes modèles.
- Doublons : une action déjà importée est ignorée (identifiant d'action). Un `create` déjà existant est ignoré lui aussi : `shot_batch_exists()` le vérifie déjà.
- Les reviews de l'ancien format sont refusées, comme aujourd'hui pour une autre version du schéma.

### 2.4 Le rendu principal d'un shot

Avec des rendus par département (phase 5), un shot en a plusieurs. **Le rendu principal** est celui qu'on voit et qu'on emporte par défaut : la lecture ▶, la vignette, la lecture de toute une séquence, la copie dans `videos/` ou le zip du snapshot, et la preview de séquence de la farm.

- **La règle** : le rendu du **département le plus avancé** selon les étapes (2.2). À étape égale, c'est le plus récent. Rien à configurer : la hiérarchie dit déjà quels départements sont « finaux ». Sans étapes définies, c'est le plus récent.
- Un rendu layout relancé après le lighting **ne remplace donc pas** le lighting dans la lecture de la séquence.
- **Dans File details et dans la page** : le rendu principal en tête, puis une ligne par département.
- **Dans `videos/` ou le zip** : uniquement le rendu principal de chaque shot, avec une case « tous les départements » à l'export. Les autres lignes se lisent depuis `renders/` quand le projet est accessible.
- **Les anciens rendus sans département** passent après ceux qui en ont un. Un projet entièrement ancien ne change pas : son rendu le plus récent reste le principal.

### 2.5 L'équipe, l'attribution et « Mon travail »

- **La liste de l'équipe** est dans la config du projet : `"team": ["léa", "tom", ...]`, modifiable dans Edit project.
- **Le nom d'utilisateur** (dans les préférences, propre à chaque machine) se **choisit dans la liste de l'équipe** du projet actif, avec une entrée « Autre… » pour un nom libre. La liste sert à éviter les fautes de frappe, qui casseraient le filtre « Moi ».
- **L'attribution se fait par département d'un fichier**, comme une tâche dans Kitsu : sh010 avec layout pour Léa et animation pour Tom. Elle est facultative.
  - Stockée dans le `tracking.json` du dossier : `"assignees": {"animation": ["tom"]}`.
  - On attribue dans File details, dans la page HTML (une action de review `assign`) et à la création (dans la page comme en CSV).
- **Un filtre « Moi »** dans Project monitoring et dans la page. Dans la page, « moi » est le nom saisi pour la review.
- **La vue « Mon travail »**, calculée par le moteur d'états, pour les départements qui me sont attribués :
  - ceux **à reprendre** ;
  - mes **RTK ouverts** ;
  - ceux **prêts à démarrer** (toutes les étapes précédentes sont finies) ;
  - mes **rendus à vérifier**.
- **Pas de tableau de charge par personne**, ni de nombre de tâches, ni de temps par personne. C'est le principe de `docs/design.md` : l'attribution sert à filtrer, pas à compter.

### 2.6 « Omit / On hold » : écarter un shot sans l'archiver

Aujourd'hui, la seule façon d'exclure un shot des stats est de l'archiver, et il disparaît alors des listes.

- **Un marqueur** dans le `tracking.json` du dossier : `"omit": {"state": "omit" | "on_hold", "at", "by", "reason"}`.
- Le fichier **reste dans l'arborescence et dans les listes**, en grisé, avec son marqueur.
- Le moteur d'états le **sort** des %, de l'avancement du planning, des filtres RTK / To validate / À reprendre, du calcul des Waiting, et de « Mon travail ».
- Il se pose et se retire depuis File details, et dans la page via une action de review `omit`.
- **[à confirmer]** Pour un **bloc** (`sh040-050-060`, un seul fichier) : le marqueur vaut pour tout le bloc, ou peut-il viser un seul de ses shots ?

### 2.7 Des dates avec fuseau horaire

**Le constat :** toutes les dates écrites par l'addon sont en **heure locale sans fuseau**. `lib/core.py` `now()` écrit `datetime.now()`, il est appelé 78 fois, et aucun fichier n'utilise `timezone`, `tzinfo` ni `astimezone`. Le commentaire de `now()` le dit lui-même : « Local, not UTC ».

Ce que ça casse aujourd'hui, ou cassera :
- **Une personne dans un autre fuseau** (un freelance à l'étranger sur le partage) écrit ses dates avec quelques heures d'écart. Les comparaisons d'ordre deviennent fausses : « retravaillé depuis le stable », l'ordre des notes, et demain Waiting et À reprendre, qui reposent entièrement sur cet ordre.
- **Un worker dans un autre fuseau** paraît mort ou « silencieux » dès sa première seconde : son heartbeat a des heures d'écart, pour un seuil de 15 s.
- **Le passage à l'heure d'hiver ou d'été**, même dans un seul pays : deux fois par an, une heure se répète ou disparaît, et l'ordre ou les durées calculées dans cette fenêtre sont faux.
- **Des dates triées comme du texte** (par exemple `max(edited_at)` dans `lib/tracking.py`, le tri par `at` dans `farm/pace.py`) : avec des fuseaux différents, l'ordre alphabétique ne correspond plus à l'ordre réel.

**La solution :**
- **On écrit l'heure locale avec son décalage** : `2026-11-14T10:03:00+01:00` (`datetime.now().astimezone()`). Elle reste lisible dans les fichiers et ne laisse aucune ambiguïté.
- **On compare toujours des dates avec fuseau.** Une seule fonction de lecture (celle de la phase 1A) accepte les deux formes :
  - une date avec décalage est prise telle quelle ;
  - une ancienne date sans décalage est considérée comme l'heure locale de la machine qui lit, comme aujourd'hui.
  
  Il faut le faire **partout d'un coup** : Python refuse de comparer une date avec fuseau et une date sans, ce qui donnerait une erreur.
- **Plus aucune date triée comme du texte** : on trie les dates lues.
- **Les heartbeats et le fait d'être en vie passent en secondes epoch** (`time.time()`, comme les réservations de chunks le font déjà) : ils ne dépendent plus ni du fuseau ni du changement d'heure.
- **Dans la page HTML**, une date avec décalage est lue correctement par `Date`, et s'affiche à l'heure locale de celui qui regarde.
- **Les noms de fichiers** (snapshots, reviews, dossiers par mois) restent à l'heure locale de celui qui les crée, ce qui est sans risque.
- Les horloges doivent toujours être à l'heure (synchronisées automatiquement), mais le fuseau de chaque machine n'a plus d'importance.

---

## 3. Les phases de travail

### Phase 1 — Simplifier le code, avant toute nouvelle fonctionnalité

**On commence par là.** Tant que le code n'est pas allégé, chaque nouvelle fonctionnalité s'ajouterait à des mécaniques en double et à des écrans écrits ligne par ligne.

Méthode :
- une nouvelle branche, un commit par tâche ;
- **à comportement identique** : rien ne change à l'écran sauf la popup de 1B.3 ;
- un test après chaque factorisation ;
- le poids du zip et le nombre de lignes mesurés avant et après chaque étape.

#### 1A — Factorisations et boucles (en premier)

| # | Tâche | Où |
|---|---|---|
| 1A.1 | **Un seul circuit demande → processus → résultat entre l'hôte et un worker**, en deux variantes (rendu, preview). On garde les previews sur worker et on supprime la mécanique en double (~80-100 lignes) | `farm/workers.py`, `farm/post_render.py` |
| 1A.2 | **Les écrans en boucles** : quand on sait à l'avance quelles lignes afficher, une liste de champs (libellé, icône, valeur) parcourue par une boucle, au lieu d'appels écrits un par un. À traiter dans cet ordre, du plus gros au plus petit : | |
| | – `draw_farm_job_details` (276 lignes), `draw_farm_workers` (196), `draw_farm_jobs` (191), `draw_farm_worker_details` (175) | `panels/farm_panel.py` (1 111 lignes) |
| | – `draw_file_details` (253), `_draw_entry` (118), `draw_entries` (112), `_draw_monitor_row` (109), `draw_monitor_table` (67) | `panels/tracking_panel.py` |
| | – la fenêtre Edit project, `draw_settings` (133 lignes, 50 appels d'interface), avec ses réglages sur deux colonnes, facile à décrire en liste | `operators/project_ops.py` |
| | – le menu du haut (151), le panneau Project (145), le panneau File (126), la fenêtre de rendu (99), l'accueil (91), le plan d'import d'une review (69), le navigateur (61) | `menus/top_bar.py`, `panels/project_panel.py`, `panels/file_panel.py`, `operators/farm_ops.py`, `lib/operators.py`, `operators/tracking_ops.py`, `operators/browser_ops.py` |
| 1A.3 | **Des fonctions d'affichage partagées** : « libellé + champ » ; « boutons si peu de choix, sinon menu déroulant », écrit 4 fois ; le bloc description / départements / fichier vierge, identique dans la création d'asset et de shot ; les boutons ouvrir le dossier, lire la vidéo et infobulle, répétés dans plusieurs panneaux | `operators/asset_ops.py:82`, `shot_ops.py:345, 410, 592`, `browser_ops.py:88, 102, 139, 211`, `lib/browser.py:281-401`, panneaux |
| 1A.4 | **Une seule version de chaque petite fonction**, dans `lib/` : | |
| | – lecture d'une date ISO : remplace 17 `try/except` autour de `fromisoformat` et 4 fonctions locales (`_job_time`, `_timestamp`, `parse_review_date`, `_heartbeat_age`). C'est elle qui gérera le fuseau horaire (1C) | `lib/core.py` |
| | – affichage d'une durée : `_duration` (farm_panel), `format_duration` (tracking), `pace._clock` | |
| | – lecture de la sortie de `ffmpeg -i` : `_video_info` (preview), `_frame_size` (post_render) | |
| 1A.5 | **Un petit cache commun** pour « relire un fichier seulement s'il a changé » (`history`, `preset_pace` dans `farm/loop.py`, et les autres caches maison qui s'y prêtent) | `farm/loop.py`, `lib/` |
| 1A.6 | **Une fonction unique pour ajouter une étape à un job** : elle remplace les 18 `stage_history.append(...)` écrits à la main, à côté de `mark_stage()` | `farm/*` |
| 1A.7 | **Les 5 lancements d'un Blender en arrière-plan** (setup, création par lot, vignettes, rendu worker) : une seule fonction si possible, `popen_logged()` en centralise déjà une partie | `farm/setup.py`, `lib/batch.py`, `farm/post_render.py`, `farm/workers.py` |
| 1A.8 | **Relancer le détecteur de code dupliqué** après 1A.1 à 1A.7, pour vérifier qu'il ne reste rien de notable | — |

#### 1B — Retraits

| # | Tâche | Où |
|---|---|---|
| 1B.1 | Retirer `CHANGELOG.md` du zip (`paths_exclude_pattern`) | `blender_manifest.toml` |
| 1B.2 | Retirer l'xlsx : générateur, import, lecture (~600 lignes) | `lib/review_sheet.py`, `lib/review_import.py`, opérateurs, docs |
| 1B.3 | « Quelle machine a rendu quelle frame » dans un **bouton + popup** | `panels/farm_panel.py` |
| 1B.4 | Retirer le code de compatibilité **entre versions de l'addon** : worker sur un ancien protocole, libellés « older addon », demandes sans chunks | `farm/*`, `panels/farm_panel.py`, ~43 endroits repérés |
| 1B.5 | **[à confirmer]** Anciennes **données** de projet (validations d'avant la 1.1.9, historiques sans preset…) : soit une *migration unique* (un bouton dans Maintenance qui réécrit les vieux fichiers, puis on retire les lectures de compatibilité dans la version suivante), soit on garde ces lectures | `lib/tracking.py` (`_legacy_carried`…), `farm/loop.py` |

#### 1C — Dates avec fuseau horaire (voir 2.7)

| # | Tâche | Où |
|---|---|---|
| 1C.1 | `now()` écrit l'heure locale **avec son décalage** | `lib/core.py` |
| 1C.2 | Toutes les lectures et comparaisons de dates passent par la fonction de 1A.4, qui accepte aussi les anciennes dates sans décalage. **À faire en une fois** : Python refuse de comparer une date avec fuseau et une date sans | partout où il y a `fromisoformat` |
| 1C.3 | Plus aucune date triée comme du texte | `lib/tracking.py` (`last_saved_at`…), `farm/pace.py`, d'autres à repérer |
| 1C.4 | Heartbeats et vie des machines en secondes epoch | `farm/workers.py`, `farm/monitor.py`, `farm/loop.py`, `panels/farm_panel.py` |
| 1C.5 | Vérifier la lecture et l'affichage des dates avec décalage dans la page HTML | `templates/snapshot/page.js` |

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
- **« Omit / On hold »** (2.6) : le marqueur, son bouton dans File details, et son exclusion par le moteur.
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
- **Le rendu principal** (2.4) pour ▶, la vignette, la lecture de la séquence, `videos/` et le zip (avec la case « tous les départements » à l'export), et la preview de séquence.
- *Checked* précoche le département du rendu au lieu de « render ».
- Un rendu tagué compte comme remise à jour de son département dans le moteur d'états (2.2).

### Phase 6 — Équipe, attribution et « Mon travail »

Elle vient en dernier : elle repose sur le moteur d'états (phase 3), et « mes rendus à vérifier » sur les rendus par département (phase 5).

- La liste `team` dans la config, et son champ dans Edit project.
- Le nom d'utilisateur dans les préférences : un menu avec la liste de l'équipe, plus « Autre… ».
- `assignees` par département dans `tracking.json`. On attribue dans File details, dans la page (action `assign`) et à la création (page, CSV).
- Le filtre « Moi » dans Project monitoring et dans la page.
- La vue « Mon travail » (2.5).

---

## 4. Questions encore ouvertes

1. **Phase 1B.5** : migration unique des anciennes données de projet, ou on garde leur lecture ?
2. **2.2** : pour un département de rendu, la remise à jour automatique se fait-elle uniquement par un nouveau rendu tagué ?
3. **2.2** : le « Toujours valide » est-il ouvert à tous, ou réservé à certains rôles ?
4. **Phase 2** : les reviews rangées aussi par mois dans `snapshots/reviews/<rôle>/` ? Le nom du fichier commence déjà par la date.
5. **2.6** : « Omit » sur un bloc : pour tout le bloc, ou par shot du bloc ?

## Écarté, et pourquoi

| Idée | Pourquoi on ne la fait pas |
|---|---|
| « Depuis ta dernière visite » | Peu fiable : la date n'aurait été valable que pour une machine. Le journal des sessions dit quand on était connecté, pas ce qu'on a vu, et l'addon ne le relit jamais, par principe |
| Dessiner sur une frame dans la review | Pratique, mais trop lourd à écrire en JS et trop lourd dans le fichier de review |
| Comparer deux versions côte à côte dans la page | Même raison |
| Temps estimé contre temps passé, Gantt, échéances par tâche | Conçu pour les producteurs de gros studios ; pour 2 à 5 personnes, le planning global du projet suffit |
| Feuilles de temps, quotas, stats ou charge par personne | Contraire au principe de `docs/design.md` : pas de surveillance dans une petite équipe |
| Accès client, Slack, comptes utilisateurs | Il faudrait un serveur ; l'addon reste « tout en JSON sur le partage » |
| Supprimer les previews compilées sur un worker | On les garde (plusieurs previews d'un coup peuvent être longues) ; on factorise seulement leur mécanique (1A.1) |

## 5. Effet attendu sur le poids

- **Phase 1** : −94 Ko (CHANGELOG), environ −600 lignes (xlsx), environ −80 à 100 lignes (previews), les retraits de compatibilité, et les écrans en boucles, qui devraient être le plus gros gain : panneau farm, File details, Edit project, de l'ordre de quelques centaines de lignes (estimation grossière). Le poids sera mesuré avant et après chaque étape.
- **Phases 3 à 5** : elles ajoutent du code, surtout le moteur d'états et son jumeau JS. Mais ce moteur *remplace* les calculs d'états répartis aujourd'hui, et le format en actions rend l'import plus simple que l'actuel.
