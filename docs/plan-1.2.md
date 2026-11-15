# Plan 1.2 — récapitulatif des modifications

*État au 14/11/2026, à partir de la 1.1.10. Les phases 1A, 1B et 1C sont faites (dans `main`, voir « Avancement » ci-dessous) ; le reste fixe les décisions prises et l'architecture retenue. Les points marqués **[à confirmer]** restent à trancher.*

Hypothèse de départ, validée : **tous les PC sont mis à jour en même temps.** Le code qui gère des machines sur des versions différentes peut donc disparaître.

## Avancement

**Phase 1A et 1B faites**, un commit par tâche, à comportement identique (sauf la popup de 1B.3). Vérifié sans Blender : import complet avec un faux `bpy` (`tools/fake_bpy.py`), et pour chaque écran réécrit, la trace des appels d'interface de l'ancien code et du nouveau sur les mêmes données (identiques). Les tests sont dans `tests/`, que le `.gitignore` exclut : ils restent sur la machine locale. `tests/test_migration.py`, écrit dans la session cloud, a été perdu pour cette raison (à réécrire) ; `tests/test_dates.py` est là.

| | 1.1.10 | Après la phase 1 |
|---|---|---|
| Fichiers du zip (bruts) | 1 398 Ko | 1 282 Ko (−116 Ko) |
| Lignes Python | 30 426 | 29 731 (−695) |
| Lignes de code Python (sans commentaires ni docstrings) | 22 835 | 22 008 (−827) |

Dont **+439 lignes de code** pour le script de migration (`lib/migration.py` 307, `operators/migration_ops.py` 132), qui reprend l'ancienne logique de lecture pour la jouer une fois. Hors migration, la phase 1 retire **1 266 lignes de code** (−5,5 %) et 141 Ko.

| Étape | Lignes de code | Lignes Python | Zip brut |
|---|---|---|---|
| Retrait xlsx + CHANGELOG (1B.1, 1B.2) | −533 | −627 | −122 Ko |
| Compat entre versions de l'addon (1B.4) | −12 | −17 | — |
| Legacy retiré des lecteurs (1B.5) | ≈ −140 | ≈ −170 | — |
| Script de migration ajouté (1B.5) | +439 | +611 | +25 Ko |
| Factorisations (1A.1, 1A.4 à 1A.7) | −141 | −119 | −4 Ko |
| Écrans en boucles, fonctions d'affichage (1A.2, 1A.3, 1B.3) | −458 | −389 | −3 Ko |

**1C faite** (dates avec fuseau) : `now()` écrit le décalage ; `parse_iso()` rend toujours une date avec fuseau, ramenée à l'heure locale de la machine qui lit, et lit aussi les anciennes dates et les secondes epoch ; plus aucun tri ni affichage de date par le texte (`time_key()`, `local_time()`) ; heartbeats en secondes epoch ; page HTML (`dayOf()`, `isoNow()`) ; étape de la migration (`_migrate_dates()`). Vérifié sans Blender dans quatre fuseaux (`tests/test_dates.py`). Détails : NOTES.md, « Dates with their offset ».

**1D faite** (page du snapshot −23 Ko). **La phase 1 est terminée.**

**Phase 2b essayée dans Blender 5.2.3** : faisable (voir la phase 2b).

**Page snapshot, refonte v3** (maquette Claude Design, `docs/` du brief) : étape 1 faite (palette sombre façon Blender, en-tête sur une ligne, losanges keyframe, post-its, Breakdown en onglet), étape 2 faite (lecteur dans le panneau, timeline avec les notes à leurs images, Watch large, fils sous leur département), étape 3 en cours (fenêtre d'envoi faite ; fenêtre de démarrage et résumé dans l'en-tête à venir), étape 4 à venir (téléphone, iPad). Icônes : celles de Blender (`trailers/icons` → `tools/clean_icons.py`). Les marques de Project monitoring reprennent les losanges de la page.

**Testé dans Blender** : *Migrate old data* sur une copie d'un vrai projet, sans erreur visible (avant 1C : à relancer pour les dates). **Pas encore testé dans Blender** : le reste de ce qui est ci-dessus, dont 1C, plus les deux changements de la 1.1.10 (« waiting for a worker », la molette). À vérifier en priorité : la popup « Which machine, which frame... » (son champ Frame qui se met à jour), le bouton *Migrate old data* sur une copie d'un vrai projet, et une passe sur chaque écran réécrit (Farm monitoring, File details, Edit project, menu du haut, panneaux Project et File).

## 0. Pour reprendre dans une nouvelle conversation

**État du dépôt au 14/11/2026 :**
- `main` : phases 1 (1A, 1B, 1C, 1D), 2 et 2b faites, pas encore publiées (section `## Unreleased` du CHANGELOG). `main` sur GitHub = ce qui a été poussé par *Sync* depuis la machine locale.
- **Testé dans Blender** : *Migrate old data* (deux fois, dates comprises, projet `alive`), la 2b (zones, raccourcis), la molette et « waiting for a worker » de la 1.1.10.
- **Les tests sont dans `tests/`**, suivis par git (exclus du zip par le manifest) : `test_dates.py`, `test_snapshot_folders.py`. `test_migration.py`, perdu, est à réécrire avant la phase 3.

**Ordre de travail** : les phases de la section 3, dans l'ordre (3, 4, 5, 6). Une seule sortie à la fin (section 5).

**Comment tester sans Blender** (aucun Blender dans les sessions cloud) :
- **Importer tout l'addon avec un faux `bpy`** : chaque module `bpy*`, `mathutils`, `gpu`, `blf`, `bmesh`… remplacé par un `MagicMock`, sauf `bpy.types`, à remplacer par un module dont chaque attribut est une classe vide (sinon `class X(bpy.types.Panel)` échoue). Puis `import <paquet>` depuis un dossier qui pointe vers le dépôt. Ça attrape les imports cassés et les noms manquants dans les `__init__`.
- **Tester les fonctions pures directement** (états, voisins dans une liste, priorités, moyennes…), et les commandes ffmpeg en les lançant vraiment sur des frames générées par ffmpeg.
- **Ruff** : comparer le nombre d'avertissements par règle avant et après, pas viser zéro. Le projet garde volontairement des `except Exception` dans les fonctions qui ne doivent jamais lever d'erreur.
- **Le détecteur de code dupliqué** (étape 1A.8) : comparer des fenêtres de N lignes de code après normalisation (noms → `N`, textes → `S`, nombres → `0`, sans commentaires ni docstrings).

**Construire un zip de test**, comme `blender --command extension build` :
- partir des fichiers suivis par git (`git ls-files`) ;
- appliquer les exclusions de `blender_manifest.toml` : fichiers et dossiers en `.`, `__pycache__/`, `/docs/`, `/NOTES.md`, `/CODE.md`, `/graph.md`, `/README.md`, `/README_fr.md`, les `.zip` à la racine, `*.blend1`… — et `/CHANGELOG.md` une fois l'étape 1B.1 faite ;
- mettre les fichiers à la racine du zip.

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
  - les « toujours done » (voir 2.2).
  
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
  - manuelle : **un bouton « Toujours done »** (« Still done » dans l'interface) sur le département, dans File details, le panneau latéral et la page HTML (qui le transmet comme action de review). Il enregistre la date, l'auteur et éventuellement une note. Ce n'est **pas** « valide » : la validation reste le statut réservé à la prod, et ce bouton ne fait que dire que le travail fait reste bon.
- **Plusieurs RTK en amont ne posent pas de problème** : la date couvre tous les changements jusqu'à maintenant. Un nouveau changement après cette date fait revenir « À reprendre ».
- Seuls les départements **commencés** peuvent être « À reprendre ». Un département pas encore commencé partira de toute façon de la dernière version.

**La règle de remise à jour automatique : un enregistrement avec le département coché comme travaillé.** Ni le rendu ni l'incrément ne sont obligatoires dans le pipeline, donc aucun des deux ne peut être la condition.
- Un département est remis à jour par un **enregistrement** (la date du save), dans une session où il a été **coché comme travaillé**, **après** le changement en amont. Un rendu tagué à son nom compte aussi, mais n'est pas nécessaire.
- **Le piège dans les données actuelles** : un `.wipmeta` n'a qu'**une** date, `edited_at`, mise à jour à chaque save (`wipmeta_touch()`), alors que `departments_worked` liste les départements **par session**. Exemple : « animation » est coché lundi dans la version v005, le layout change mardi, et quelqu'un enregistre v005 mercredi sans rien cocher. La date du fichier devient mercredi, et l'animation passerait pour remise à jour alors que personne n'y a touché.
- **La correction** : noter la date du dernier enregistrement **de chaque session**, avec ses départements cochés : `departments_worked: {<session>: {"departments": [...], "saved_at": "..."}}`. Le script de migration (1B.5) convertit les anciens fichiers, en prenant `edited_at` comme date de leurs sessions.

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
   {"type": "still_done",  "file": "...", "department": "animation", "text": "..."},
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
- **Un menu pour basculer entre « Plus haut département » et « Plus récent »**, qui décide quel rendu est le principal :
  - dans File details et dans la page : c'est un choix de celui qui regarde, retenu par la page dans le navigateur et par Blender pour la session ;
  - à l'export du snapshot et dans la fenêtre de preview de séquence : il décide quelles vidéos sont emportées ou enchaînées.
- **Dans File details et dans la page** : le rendu principal en tête, puis une ligne par département. **Un rendu plus récent que le principal**, d'un département plus bas (un rendu animation refait après le render), est **signalé sur la ligne du principal** (« plus récent : animation v007 ») et s'ouvre d'un clic. On voit le rendu « render », sans rater ce qui a été refait depuis.
- **Dans `videos/` ou le zip** : uniquement le rendu principal de chaque shot, avec une case **« tous les départements »** à l'export. Sans cette case, les autres lignes se lisent depuis `renders/` quand le projet est accessible.
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
- **Un marqueur par fichier** : pour un **bloc** (`sh040-050-060`, un seul fichier), il vaut pour tout le bloc. Pour écarter un seul shot d'un bloc, on modifie la structure du fichier, ce qui est déjà possible.

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
| 1B.5 | **Les anciennes données de projet : un script de migration plutôt qu'une couche « legacy »** (détail ci-dessous) | `lib/tracking.py`, `lib/snapshot.py`, Maintenance |

**1B.5 en détail.** Le relevé du code donne **trois vraies lectures d'anciennes données**. Les autres mentions sont du code entre versions de l'addon (1B.4), ou sans rapport (un texte « placeholder », un lien vers une ancienne version d'asset).

| Ancienne donnée | Lue aujourd'hui par | Ce qui casserait si on retirait cette lecture |
|---|---|---|
| **Les validations « reportées » d'un stable fait avant la 1.1.9** : ces stables ne notaient pas les validations héritées du stable précédent | `_legacy_carried()`, `lib/tracking.py:1498`, appelée deux fois | **Visible** : des départements validés s'afficheraient non validés sur les fichiers dont le dernier stable date d'avant la 1.1.9, jusqu'au prochain stable |
| **Les entrées de `render_history.json` sans `source_file` ni `shot_override`** (anciennes versions) | `lib/snapshot.py:110`, recherche du dernier rendu d'un shot | **Visible** : certains shots rendus il y a longtemps afficheraient un mauvais « dernier rendu », ou aucun |
| **Les rendus d'avant que l'historique note leur plage de frames** | `_folder_frames()`, `lib/snapshot.py:213` : la plage est déduite du nom des images | Mineur : la numérotation des frames dans la page partirait de 1 au lieu de la vraie première frame |
| Les rendus d'avant la 1.1.7, sans preset noté | `history_pace()` : estimation « preset unknown » | Négligeable : pas d'estimation pour ces fichiers |

**Pourquoi une migration plutôt qu'une couche legacy :** le moteur d'états de la phase 3 deviendrait sinon le principal utilisateur de ces cas particuliers, alors qu'il devrait ne connaître qu'**une seule forme de données**.

**Le script : un bouton « Migrer les anciennes données » dans Maintenance**, lancé une fois par projet :
1. il écrit dans les vieux `.stablemeta` les validations que `_legacy_carried()` calcule ;
2. il complète les vieilles entrées de `render_history.json` (`source_file`, `shot_override`, `frame_range_rendered`) avec les mêmes déductions qu'aujourd'hui ;
3. il fait une sauvegarde de chaque fichier avant de le réécrire, **jamais à côté du fichier** : tout va dans un seul dossier à la racine du projet, `backup/migration-<AAAA-MM-JJ_HH-MM>/`, qui reprend le chemin relatif de chaque fichier (`backup/migration-…/shots/sq080/sh010/.pipeline/tracking.json`). Une migration vérifiée se nettoie donc en supprimant un seul dossier, sans aller chercher des petits fichiers partout ;
   - il indique ce qu'il a changé, fichier par fichier ;
4. il note dans la config du projet qu'il a été lancé.

Le script permet de **supprimer tout le legacy actuel** : `_legacy_carried()`, la recherche de secours de `snapshot.py:110`, l'estimation « preset unknown ». Il porte aussi les conversions de format de la 1.2 elle-même (les dates sans décalage de 1C, `departments_worked` avec la date de chaque session, voir 2.2). Le code n'a ensuite plus qu'une seule forme de données à lire. On garde seulement la lecture défensive de `_folder_frames()` : elle coûte quelques lignes et sert aussi quand l'historique manque.

#### 1C — Dates avec fuseau horaire (voir 2.7)

| # | Tâche | Où |
|---|---|---|
| 1C.1 ✅ | `now()` écrit l'heure locale **avec son décalage** | `lib/core.py` |
| 1C.2 ✅ | Toutes les lectures et comparaisons de dates passent par la fonction de 1A.4, qui accepte aussi les anciennes dates sans décalage. **À faire en une fois** : Python refuse de comparer une date avec fuseau et une date sans | partout où il y a `fromisoformat` |
| 1C.3 ✅ | Plus aucune date triée comme du texte | `lib/tracking.py` (`last_saved_at`…), `farm/pace.py`, d'autres à repérer |
| 1C.4 ✅ | Heartbeats et vie des machines en secondes epoch | `farm/workers.py`, `farm/monitor.py`, `farm/loop.py`, `panels/farm_panel.py` |
| 1C.5 ✅ | Vérifier la lecture et l'affichage des dates avec décalage dans la page HTML | `templates/snapshot/page.js` |

#### 1D — Alléger la page du snapshot

Relevé du 14/11 : le JS est déjà compact (132 fonctions toutes appelées, quasiment aucun doublon). Le gain est surtout sur chaque snapshot exporté, qui embarque toute la page (~170 Ko).

| # | Tâche | Où |
|---|---|---|
| 1D.1 ✅ | Retirer les règles CSS mortes : `.b-valid`, `.b-old`, `.gr`, `.grab`, `.links` (3 règles), `.no-open` (~0,6 Ko) | `templates/snapshot/page.css` |
| 1D.2 ✅ | Les icônes SVG écrites deux fois (aide et filtres) en `<symbol>` + `<use>`, comme le logo (~1,4 Ko) | `templates/snapshot/page.html` |
| 1D.3 ✅ | Retirer les commentaires du JS et du CSS **à l'export** (les sources restent commentées) : −21 Ko par snapshot, −12 %. Pas de minification, qui demanderait un outil externe | `lib/snapshot_page.py` `render_html()` |
| — | **Pas maintenant** : le code de la review (~185 lignes, 17 Ko du JS), remplacé par le format en actions de la phase 4 | `page.js` |

**Fait** : −23 Ko par snapshot (177 → 154 Ko hors données, −13 %) : commentaires −22 Ko, icônes −0,6 Ko, CSS morte −0,5 Ko. Vérifié dans Firefox sans interface avec les données d'un vrai snapshot : capture identique au pixel près, et le JS sans commentaires passe le contrôle de syntaxe.

### Phase 2 — Rangement des snapshots et des reviews

**Faite** (14/11) : `month_folder()`, `snapshot_videos_folder()`, `keep_review()`, testés sans Blender (`tests/test_snapshot_folders.py`). Le sélecteur d'*Import review* s'ouvre à la racine du projet (question 4).

- **Copie de la review** : après un import réussi depuis Blender, copie du fichier original dans `snapshots/reviews/<rôle>/<AAAA-MM>/`, le mois de la review. Le nom contient déjà la date, le rôle et l'auteur. Le même fichier n'est pas recopié ; un fichier différent du même nom reçoit un suffixe ; rien n'est copié si l'import est annulé. *Import review* ouvre son sélecteur sur `snapshots/reviews/`.
- **Snapshots rangés par mois** : `snapshots/2026-11/…html`.
  - **Un seul dossier `snapshots/videos/`**, que la page trouve via `../videos` : sinon chaque mois aurait sa propre copie de toutes les vidéos (le mode *Folder* écrit aujourd'hui `videos/` à côté du snapshot, `tracking_ops.py:1207`).
  - Le chemin relatif vers `renders/` est calculé à l'export : les nouveaux snapshots s'adaptent tout seuls.
  - **Les anciens snapshots restent à la racine** : les déplacer casserait leurs chemins vers les vidéos.

### Phase 2b — Le détail à côté de la liste, dans les fenêtres de monitoring

**Faite** (14/11), testée dans Blender (zones, raccourcis ; la largeur gardée et la liste étroite corrigées ensuite) : `sync_detail_zones()` et `monitoring_zone()` (`lib/monitoring.py`), panneaux et raccourcis selon la zone, liste réduite à ses noms sous 600 px (seulement Project monitoring). Détails : NOTES.md, « Monitoring: the detail beside the list ».

**Aujourd'hui :** ouvrir un détail (un fichier dans Project monitoring, un job ou un worker dans Farm monitoring) **remplace** toute la liste, dans la même zone.

**Proposition :** le détail s'ouvre **à droite de la liste**, dans une **deuxième zone** de la même fenêtre, comme le panneau d'un fichier dans la page HTML sur ordinateur.
- **Redimensionnable** en tirant la bordure entre les deux zones, comme n'importe quelle zone de Blender. La largeur choisie est retenue pendant la session, par type de fenêtre.
- **Un clic sur une autre ligne** change le détail sans le fermer. **Échap**, ou un bouton ×, ferme la zone de droite et rend toute la largeur à la liste.
- **Les raccourcis suivent la zone sous la souris**, ce qui règle tout seul le conflit d'avant :
  - sur la liste, la molette et ←/→ tournent les pages ;
  - sur le détail, la molette fait défiler, et ←/→ passent au fichier précédent ou suivant.
- **Fenêtre trop étroite** pour deux colonnes : on revient au comportement actuel, le détail remplace la liste.
- La liste garde ses pages calculées sur la hauteur de la fenêtre. Sa largeur réduite oblige seulement les colonnes à se resserrer.
- **Zone trop étroite** (la bordure tirée loin) : la zone ne garde que sa **première colonne**, sans les colonnes suivantes. Idée venue de l'essai ci-dessous, pour la zone de droite. Le seuil de largeur reste à fixer.

**Essai dans Blender 5.2.3 (14/11/2026) : faisable.** Un script hors de l'addon a découpé une fenêtre Project monitoring en deux, affiché la liste à gauche et le détail à droite, puis refermé la zone de droite. Tout a marché. Ce que l'essai a appris :
- **Créer la zone** : `bpy.ops.screen.area_split(direction="VERTICAL", factor=…)` dans `context.temp_override(window=…, screen=…, area=…)` répond `FINISHED`. La nouvelle zone **reprend tout** de l'ancienne : éditeur Properties, onglet Tool, sans en-tête ni colonne d'onglets. Rien à remettre en forme.
- **`factor` a un piège** : le nouvel éditeur prend toujours **la plus petite part**. Avec 0.6 il est à droite (40 %), avec 0.3 à gauche (30 %).
- **Reconnaître le détail par sa position** : la zone Properties la plus à droite (le plus grand `area.x`), jamais « la nouvelle ». Chaque panneau dessine la liste ou le détail selon la zone où il est. Avec une seule zone, rien ne change par rapport à aujourd'hui.
- **La taille d'une zone n'existe qu'au dessin suivant** : 0×0 juste après le split. La lire dans un timer.
- **La bordure tirée se relit** (`area.width`) : la largeur choisie peut être retenue.
- **Ne pas redécouper** une fenêtre qui a déjà deux zones : un deuxième split en crée une troisième.
- **La fermer** : `bpy.ops.screen.area_close()` sur la zone de droite, dans le même contexte, répond `FINISHED`. Mais **il faut vider le détail en même temps**, sinon la zone qui reste, revenue au dessin normal, affiche le détail à la place de la liste. Même chose quand l'utilisateur ferme la zone lui-même : au dessin, un détail encore ouvert avec une seule zone doit être vidé.
- **Le redessin doit être demandé** : un clic sur une ligne (`m_pipeline.tracking_file_details`, et les boutons de job et de worker) change le détail sans rien redessiner. Blender ne redessine que la zone cliquée, et la droite attendait le passage de la souris. `set_monitoring_detail()` doit appeler `redraw_monitoring()`, qui passe déjà sur toutes les zones Properties de la fenêtre.

**Encore à vérifier pendant le développement :**
- **L'interaction avec ce qui existe** : la fenêtre au premier plan, la réouverture sur le détail (Ctrl+clic), les fichiers ouverts par le pipeline qui gardent la fenêtre, le masquage de l'outil actif (voir NOTES.md, « Monitoring windows… »).
- **Deux fonctions choisissent aujourd'hui « la plus grande zone »** de la fenêtre (`lib/monitoring.py:89`, à l'ouverture, et `:213`, pour la mettre au premier plan). Avec deux zones, elles doivent viser explicitement la liste.
- **Les raccourcis par zone** (molette, ←/→, Échap) : pas encore essayés.
- **Un .blend enregistré** avec une fenêtre de monitoring en deux zones, puis rouvert.

### Phase 3 — Moteur d'états et hiérarchie des départements

**Découpage** : 3A moteur extrait à comportement identique ✅ (`lib/status.py`, `tests/test_status.py`) · 3B `departments_worked` par session et sa migration ✅ · 3C étapes, Waiting, À reprendre, `departments_synced`, « Still done » ✅ (moteur, Project monitoring, File details ; le panneau latéral et la page en 3E) · 3D Omit / On hold ✅ (Blender, données du snapshot ; la page en 3E) · 3E légendes : côté Blender ✅ (panneau latéral, légende de Project monitoring) ; la page attend sa refonte (Claude Design), ses données sont déjà exportées (`flags`, `omit`).

**Ordre décidé ensuite** : ce qui ne touche pas la page d'abord (phases 5 et 6), puis tout le travail sur la page en une fois, avec la refonte : 3E page, phase 4 (review en actions, créations, stats en direct, moteur JS). L'import des actions part avec la nouvelle page : le changer avant casserait les reviews de la page actuelle.

- `lib/status.py` (2.1), branché partout où un état est affiché. On remplace les calculs actuels au lieu d'en ajouter.
- `department_stages` dans la config, avec le champ « étape » dans Edit project.
- Les états **Waiting** et **À reprendre** (2.2), et `departments_synced` dans `tracking.json`.
- `departments_worked` avec la date de chaque session (2.2), écrite à chaque enregistrement. Les anciens fichiers sont convertis par la migration (1B.5).
- Le bouton **« Toujours done »** dans File details et le panneau latéral, ouvert à tous : comme le travail lui-même, ce n'est pas une validation.
- **« Omit / On hold »** (2.6) : le marqueur, son bouton dans File details, et son exclusion par le moteur.
- Les nouvelles marques dans la légende : panneau, Project monitoring, page snapshot.

### Phase 4 — La page HTML : nouveau format de review, créations, stats en direct

- Le format **actions typées** (2.3), écrit par `page.js` et lu par un nouvel import.
- Dans la page :
  - **« + shot » par séquence, « + asset » par préfixe** : nom (validé avec les règles de nommage exportées dans la page), description, plage de frames, départements requis. Le futur shot ou asset apparaît en « prévu » jusqu'à l'import. Tout le monde peut créer ; l'auteur et le rôle sont notés.
  - **Ajouter ou retirer des départements requis** sur un fichier existant.
  - **« Toujours done »** sur un département « À reprendre ».
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
- **Clean old renders, avec un menu « Garder les N derniers : par département / par version »** :
  - aujourd'hui, il garde les N rendus les plus récents d'un shot tous départements confondus (`lib/render_clean.py:198`). Avec 3 rendus animation faits après le lighting et « garder 2 », le rendu lighting serait allégé ou supprimé ;
  - **par département**, le choix par défaut : il garde les N derniers rendus **de chaque département** de chaque shot ;
  - **par version** : le comportement actuel, les N derniers tous départements confondus ;
  - dans les deux modes, restent toujours protégés : **le dernier rendu de chaque département**, le rendu principal, chaque « to check » (un par département), les rendus cités par une note ouverte, et ceux que la farm est en train d'écrire. Les anciens rendus sans département forment un groupe à part.

### Phase 5b — Le son des rendus

Décidé : le son vient **des fichiers de shot** (bandes son du séquenceur, speakers). Le son du montage seul (animatic) viendra plus tard, si besoin.

- **Au rendu**, le worker fait un mixdown du son de la scène sur la plage du shot (`bpy.ops.sound.mixdown`, sans interface), à côté des images : `renders/<seq>/<shot>/<version>/<nom>.flac`. Rien quand la scène n'a pas de son.
- **À la compilation**, ffmpeg l'intègre au mp4 (AAC) ; les previews de séquence, qui mettent les mp4 bout à bout, gardent le son en continu (un silence pour un shot sans son).
- Les copies légères (`ld/`) et les vidéos du snapshot gardent le son.
- **La page** : le lecteur a déjà son bouton son (M), gardé par le navigateur ; rien d'autre à faire.
- **Blender** : le son joue dans *Play* des rendus (lecteur système), rien à ajouter.
- À vérifier : la durée du son égale à celle des images (fps, plage), et un bloc rendu en entier puis découpé par shot.

### Phase 6 — Équipe, attribution et « Mon travail »

Elle vient en dernier : elle repose sur le moteur d'états (phase 3), et « mes rendus à vérifier » sur les rendus par département (phase 5).

- La liste `team` dans la config, et son champ dans Edit project.
- Le nom d'utilisateur dans les préférences : un menu avec la liste de l'équipe, plus « Autre… ».
- `assignees` par département dans `tracking.json`. On attribue dans File details, dans la page (action `assign`) et à la création (page, CSV).
- Le filtre « Moi » dans Project monitoring et dans la page.
- La vue « Mon travail » (2.5).

---

## 4. Questions encore ouvertes

1. ~~Phase 1B.5~~ : **décidé**, un script de migration, avec les sauvegardes dans `backup/` à la racine du projet.
2. ~~Phase 2b~~ : **vérifié** dans Blender 5.2.3, la découpe et la fermeture de la zone marchent (voir la phase 2b).
3. ~~Section 5~~ : **décidé**, une seule sortie sur le store, tout ensemble (la migration et le protocole farm 3 en font de toute façon une version qui demande tous les PC à jour).
4. ~~Phase 2, le sélecteur d'*Import review*~~ : **décidé**, il s'ouvre à la racine du projet (une review arrive de l'extérieur ; `reviews/` garde celles déjà importées).
5. ~~Phase 2, emporter un seul snapshot~~ : **sans souci**, les snapshots partent par un transfert (SwissTransfer) qui prend un dossier entier, ou le HTML seul en pièce jointe.

## 5. Versions et sorties

**Décidé : une seule sortie sur le store, tout ensemble**, quand les phases 1 à 6 sont faites.
- Elle change les données (migration, dates avec fuseau, nouveau format de review, `departments_worked` par session) : une version 1.1.x qui lirait un projet migré se tromperait ou planterait (Python refuse de comparer une date avec fuseau et une date sans).
- Donc **tous les PC à jour en même temps, puis *Migrate old data* lancé une fois par projet** : à dire dans les notes de version. Le numéro (1.2.0 ou 2.0.0) reste à choisir ; 2.0.0 signalerait mieux ce passage obligé.

**À garder malgré le retrait du code entre versions (1B.4)** : une **seule** vérification de version. Une machine qui n'a pas la même version de la farm que l'hôte est refusée, avec un message clair. Aujourd'hui, c'est `FARM_PROTOCOL` qui le fait. Sans cette vérification, une machine oubliée se comporterait mal sans rien dire, au lieu d'être écartée.

**Avant chaque sortie :**
- la doc (EN et FR), le CHANGELOG et NOTES.md à jour ;
- un test dans Blender des points marqués « à vérifier dans Blender » ;
- **lire les notes de version de Blender 5.0 à 5.3** : les pages autres que l'API Python 5.3 n'ont pas pu être lues. À noter : `UILayout.label_multiline()` (5.3) pourrait remplacer le passage à la ligne fait à la main, avec l'ancienne méthode gardée pour 4.2 à 5.2.

## 6. Écarté, et pourquoi

| Idée | Pourquoi on ne la fait pas |
|---|---|
| « Depuis ta dernière visite » | Peu fiable et risqué : la date ne vaudrait que pour une machine, et on se fierait à « je n'ai regardé que ce qui était nouveau » au risque de rater des RTK. Le journal des sessions dit quand on était connecté, pas ce qu'on a vu, et l'addon ne le relit jamais, par principe. « Mon travail » (2.5) montre tout ce qui reste à faire, sans notion de nouveauté |
| Dessiner sur une frame dans la review | Pratique, mais trop lourd à écrire en JS et trop lourd dans le fichier de review |
| Comparer deux versions côte à côte dans la page | Même raison |
| Temps estimé contre temps passé, Gantt, échéances par tâche | Conçu pour les producteurs de gros studios ; pour 2 à 5 personnes, le planning global du projet suffit |
| Feuilles de temps, quotas, stats ou charge par personne | Contraire au principe de `docs/design.md` : pas de surveillance dans une petite équipe |
| Accès client, Slack, comptes utilisateurs | Il faudrait un serveur ; l'addon reste « tout en JSON sur le partage » |
| Supprimer les previews compilées sur un worker | On les garde (plusieurs previews d'un coup peuvent être longues) ; on factorise seulement leur mécanique (1A.1) |

## 7. Effet attendu sur le poids

- **Phase 1** : −94 Ko (CHANGELOG), environ −600 lignes (xlsx), environ −80 à 100 lignes (previews), les retraits de compatibilité, et les écrans en boucles, qui devraient être le plus gros gain : panneau farm, File details, Edit project, de l'ordre de quelques centaines de lignes (estimation grossière). Le poids sera mesuré avant et après chaque étape.
- **Phases 3 à 5** : elles ajoutent du code, surtout le moteur d'états et son jumeau JS. Mais ce moteur *remplace* les calculs d'états répartis aujourd'hui, et le format en actions rend l'import plus simple que l'actuel.
