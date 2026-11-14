# Brief : la page « snapshot » d'un projet d'animation

Ce document dit **ce que la page contient, ce qu'elle doit permettre et sous quelles contraintes**. Il ne dit rien de sa présentation : la mise en page, la hiérarchie visuelle, les couleurs et les composants sont entièrement à concevoir.

---

## 1. Ce qu'est la page

- Un add-on Blender suit l'avancement d'un projet d'animation 3D : des **fichiers** (shots et assets), chacun avec des **départements** (layout, animation, lighting…), des versions, des retakes, des validations et des rendus.
- Le **snapshot** est l'export de cet état à un instant donné, sous la forme d'**une seule page HTML autonome**, ouverte hors ligne dans un navigateur.
- **Ses lecteurs n'ont ni Blender ni accès au serveur du studio** : production, superviseurs, réalisateur, client, membres de l'équipe à distance. La page leur arrive par mail ou par transfert de fichiers (SwissTransfer, avec ou sans dossier de vidéos).
- **Elle sert à deux choses :**
  1. **Lire** l'état du projet : où on en est, ce qui bloque, ce qui reste à valider, ce qui a été rendu.
  2. **Faire une review** : valider, demander des retakes, répondre aux notes. La review est **téléchargée en fichier `.json`** et renvoyée au studio, qui l'importe dans Blender. La page n'envoie rien elle-même.
- L'équipe compte de 2 à 5 personnes, et le projet de quelques dizaines à quelques centaines de fichiers.

## 2. Contraintes techniques

### Un fichier, hors ligne
- **Tout tient dans le fichier HTML** : CSS, JS, police, logo, données (JSON intégré) et vignettes (images en base64). Il n'y a **aucune ressource réseau** : ni CDN, ni police web, ni API, ni serveur.
- La page s'ouvre en `file://`, donc sans service worker ni module ES chargé depuis un autre fichier.
- **Chaque export embarque toute la page** : son poids compte. Le code est aujourd'hui d'environ 150 Ko, et les données et vignettes ajoutent souvent 1 à 3 Mo. Aucune bibliothèque externe n'est utilisable, puisqu'il faudrait l'intégrer dans chaque export.
- **Les vidéos ne sont pas dans le fichier.** La page les retrouve de trois façons :
  - par un chemin relatif vers le dossier `renders/` du projet, sur une machine du studio ;
  - par un dossier `videos/` ou un zip livré avec le snapshot ;
  - par un dossier que le lecteur choisit lui-même : `showDirectoryPicker` sur Chrome et Edge, sélection de fichiers ailleurs.

  Il faut donc gérer le cas « vidéo introuvable » avec un message utile.

### Appareils
- **Ordinateur** : Chrome, Edge, Firefox et Safari, avec souris et clavier, en écran large ou portable.
- **Tablette** : l'iPad est un vrai cas d'usage (une review sur le canapé, en salle de projection). La page est ouverte dans Safari ou dans le visualiseur de l'app *Documents*, en portrait (1024 px) comme en paysage.
- **Téléphone** : consultation surtout ; une review courte doit rester possible.
- **Tactile :**
  - des cibles d'au moins 44 px ;
  - aucune information accessible **seulement** au survol ;
  - aucune action accessible **seulement** au clavier.
- **Clavier sur ordinateur** : des raccourcis pour aller vite pendant une review (fichier précédent ou suivant, fermer, valider, retake, image par image dans une vidéo, valider l'écriture). Ce sont des raccourcis, jamais le seul moyen.
- **Clavier virtuel** : il cache la moitié de l'écran. Le champ où l'on écrit doit rester visible, et ce qui suit l'écriture (valider, passer au fichier suivant) ne doit pas se retrouver sous le clavier.
- **Particularités iPad connues :**
  - la barre d'état apparaît et disparaît à chaque toucher dans le visualiseur *Documents* ; il faut gérer `safe-area` et `viewport-fit=cover` ;
  - une saisie sous 16 px fait zoomer la page ;
  - la page ne doit jamais sauter : ni à l'ouverture d'une vidéo, ni en cochant une validation, ni en passant d'un fichier à l'autre ;
  - les listes déroulantes natives peuvent se refermer seules ;
  - une vidéo très large (au-delà de 8192 px) est refusée par le navigateur ; une copie légère existe pour ce cas.
- **Thème** clair, sombre ou celui du système, au choix du lecteur et retenu par le navigateur.
- La page est en anglais (le produit est en anglais).

### Persistance
- **La review en cours est gardée dans le navigateur** (`localStorage`), par snapshot, jusqu'au téléchargement ou à l'effacement. Fermer l'onglet ne doit rien perdre.
- Une review téléchargée peut être **rechargée** dans la page pour être continuée.
- La page ne peut pas choisir le dossier de téléchargement. Sur iPad, c'est la feuille de partage qui sert.

---

## 3. Les données disponibles

### Vocabulaire
- **Fichier** : un shot (`sq010_sh020`), un **bloc** de shots rendus ensemble dans un seul fichier (`sq010_sh030-040-050-060-070-080`, des noms qui peuvent être longs), un asset (`ch_bob`) ou une library (`mat_wood`).
- **Onglets de données** : shots, assets, libraries.
- **Groupe** : la séquence pour un shot (`sq010`), le préfixe pour un asset (`ch`, `pr`, `env`…).
- **Département** : une étape de travail requise pour un fichier. Chaque type a sa liste, de 3 à 8 départements ; un fichier peut ne pas en exiger certains.
- **WIP / stable** : une version de travail, ou une version figée et partageable (`v004`, `v004-stable_001`).
- **RTK (retake)** : une correction demandée, ouverte jusqu'à ce qu'elle soit marquée faite. Elle vient soit d'un **rôle de validation**, soit de **l'équipe**, et ces deux origines doivent se distinguer.
- **Rôles de validation** : configurés par projet et ordonnés par niveau, par exemple `sup` < `prod`. L'équipe (`team`) n'est pas un rôle de validation : elle peut demander des retakes mais ne valide pas.

### Le projet
- Le nom du projet, la date et l'heure du snapshot, qui l'a exporté et la version de l'add-on. L'âge du snapshot compte : un snapshot de 10 jours n'est plus à jour.
- **L'avancement par onglet** (shots, assets) en %, et le **% validé**.
- **Le planning**, s'il est configuré :
  - le début, la fin, les jours non travaillés et les jours travaillés de la semaine ;
  - l'avancement attendu aujourd'hui pour un rythme régulier (« jour 23 / 39, 59 % attendus ») ;
  - pour chaque onglet, l'avance ou le retard en jours ouvrés et le rythme (« 3 jours d'avance, rythme 114 % »).
- Les départements de chaque type, les rôles de validation, les poids de l'avancement (combien comptent « en cours » et « retravaillé »), et les fps du projet.

### Chaque fichier
- Son nom, son type, son onglet, son groupe et sa **description** (texte libre, parfois de plusieurs lignes).
- Sa version de travail et sa dernière stable.
- **L'état de chaque département requis :**
  - pas commencé ;
  - en cours ;
  - **fait** (au dernier stable) ;
  - **fait mais retravaillé depuis** ;
  - pas requis.

  S'y ajoute le score de chaque département, utilisé pour l'avancement.
- **Les RTK ouverts** par département (de rôle ou d'équipe), et les RTK **généraux**, qui ne visent aucun département et bloquent tout le fichier.
- **Les validations** par département : le plus haut rôle qui a validé, le détail de chaque rôle (qui, quand, sur quel stable), et le cas « validé sur un stable plus ancien, à revoir ».
- Le % fait et le % validé du fichier.
- **Pour un bloc** : la liste de ses shots et une vignette par shot.
- **Sa vignette**, tirée du dernier rendu.
- **Ses derniers rendus**, avec une ligne par vidéo (un shot d'un bloc rendu à part a la sienne). Chaque ligne donne :
  - les shots couverts et le dossier du rendu ;
  - le chemin de la vidéo ;
  - la plage d'images et la première image : les images se numérotent comme dans Blender (`f1042`), pas depuis 0 ;
  - « en retard sur la version actuelle » ;
  - un statut : **à vérifier** (rendu, pas encore vérifié par l'équipe), ou l'état sur la farm.
- **« Rendu périmé »** : le fichier a changé depuis son dernier rendu.
- **La farm** (les machines de rendu) : en cours de rendu, en file d'attente ou en échec, avec un texte (machine, progression).
- **Ses notes, en fils de discussion** : une note racine et ses réponses. Chaque entrée a :
  - un type (RTK, todo ou remarque), un texte, un auteur, un rôle ou l'équipe, et une date ;
  - ses départements (ou aucun) ;
  - le shot visé pour un bloc (`[sh020]`) et une plage d'images (`[f12-40]`) ;
  - le rendu regardé quand la note a été écrite ;
  - si elle est faite, si elle fait partie d'une validation, et la review dont elle vient.

  Un fil fermé (fait, sans réponse en attente) existe mais ne doit pas encombrer.

---

## 4. Ce que le lecteur doit pouvoir faire

### Comprendre le projet d'un coup d'œil
- **Savoir où en est le projet** et s'il est en avance ou en retard sur le planning, onglet par onglet.
- **Repérer ce qui demande de l'attention**, avec ces compteurs, chacun pouvant servir de filtre :
  - les fichiers avec un RTK ;
  - les notes ouvertes ;
  - les rendus périmés ;
  - ce qui est **à valider** (fait, pas encore validé) ;
  - ce qui est sur la farm ;
  - ce qui n'est pas fini ;
  - ce que **ma review** a touché.
- Voir le détail de l'avancement **par groupe et par département**.
- Lire la **légende** de tous les états et marques.

### Parcourir et trouver
- Passer d'un onglet à l'autre (shots, assets, libraries) et voir les fichiers par groupe, chaque groupe pouvant se replier.
- **Filtrer** par les critères ci-dessus, éventuellement **limités à un département**.
- **Chercher** un fichier par son nom et y aller directement, même hors des filtres en cours.
- Voir pour chaque fichier, sans l'ouvrir : l'état de chaque département, les RTK, les validations, l'avancement et sa vignette.
- **Ouvrir un fichier** pour tout voir de lui (section 3), puis passer au **précédent ou au suivant** dans l'ordre de la liste filtrée.
- Un **lien direct** vers un fichier (`#nom`), à envoyer à quelqu'un.

### Regarder les rendus
- Lire la vidéo d'un fichier ; pour un bloc, les vidéos de ses shots à la suite dans l'ordre.
- Lire **toute une séquence** à la suite, en sautant d'un shot au précédent ou au suivant.
- Lire une ligne de rendu précise.
- **Des contrôles précis** : lecture et pause, position, temps, plein écran, **image par image**, et le **numéro d'image comme dans Blender**. Le reviewer écrit « f1042 » dans ses notes : il doit lire ce numéro.
- Indiquer où sont les vidéos quand elles sont introuvables.

### Faire une review
- **Dire qui l'on est** : un nom, un rôle de validation ou « team » (l'équipe ne valide pas), et la date de la review.
- **Par fichier et par département :**
  - **valider**, ou retirer une validation ;
  - **écrire des retakes**, un par ligne. Une ligne qui commence par `note:` est une simple remarque, qui ne renvoie rien. Des étiquettes en début de ligne : `[sh020]` (un shot d'un bloc) et `[f12-40]` (une plage d'images).
- **Un retake général**, sans département.
- **Répondre** dans le fil d'une note existante. Une réponse peut être un retake ou une remarque.
- Marquer un RTK ouvert comme **corrigé** (*Fixed*), ou un todo comme fait.
- **Modifier la description** d'un fichier.
- **« Tout valider »** : valider d'un geste tous les départements faits du fichier.
- **Voir ce que sa review a changé** : marques sur les fichiers et départements touchés, nombre de changements, filtre « ma review ». La différence entre ce qui vient du projet et ce que j'y ajoute doit rester nette.
- Aller vite : enchaîner les fichiers sans revenir à la liste.
- **Télécharger** la review (`.json` nommé `<projet>_review_<date>_<rôle>_<auteur>.json`). La **recharger** pour la continuer, l'**effacer** ou la **quitter** (elle reste gardée dans le navigateur).
- Sans rôle et sans rien de saisi, la page dit pourquoi il n'y a rien à envoyer.

---

## 5. Points d'attention

- **Le volume** :
  - de 50 à 500 fichiers et de 3 à 8 départements, donc jusqu'à environ 4 000 cellules d'état ;
  - des descriptions et des notes longues ;
  - des fils de plusieurs réponses ;
  - des noms de blocs très longs.
- **Deux usages qui se recouvrent** : la lecture (prod et client, qui veulent une vue d'ensemble) et la review (sup et réalisateur, qui enchaînent fichier après fichier et écrivent beaucoup).
- **La couleur ne doit pas être le seul porteur de sens** : un rouge de RTK doit aussi se lire autrement. Les états doivent tous rester distinguables, en clair comme en sombre.
- **Les origines à distinguer** :
  - un RTK d'un rôle ou de l'équipe ;
  - une validation actuelle ou ancienne (à revoir) ;
  - ce qui est dans le projet ou ce qu'ajoute ma review non envoyée ;
  - un RTK sur un département ou un RTK général.
- **Rien n'est bloquant** : la page informe, elle n'empêche jamais une action.
- L'âge du snapshot doit se voir : les données ne sont pas en direct.
- Un projet sans planning, sans vignettes, sans vidéos ou sans rôles de validation doit rester lisible : chaque bloc d'information est facultatif.

---

## 6. À venir (version 1.2), à prévoir dès la conception

- **Deux nouveaux états calculés**, chacun avec sa raison :
  - **Waiting** (« Waiting : layout RTK », « Waiting : layout pas commencé ») : une étape amont bloque ce département. Ce n'est qu'une information : l'état réel du département reste visible.
  - **À reprendre** (« layout changé le 12/11 ») : l'amont a changé depuis la dernière mise à jour de ce département.
- **« Still done »** : une action de review sur un département à reprendre, qui dit « le travail fait reste bon ». Ce n'est pas une validation.
- **Omit / On hold** : un fichier écarté, avec une raison. Il reste visible, à part, et sort des % et des filtres. On peut le poser ou le retirer en review.
- **Les stats en direct** : les % et les compteurs recalculés avec la review en cours (« avec ta review : 64 % (+3) »).
- **Créer depuis la page** : un shot dans une séquence ou un asset dans un préfixe, avec nom, description, plage d'images et départements requis. Il apparaît comme « prévu » jusqu'à son import. On peut aussi **ajouter ou retirer des départements requis** sur un fichier.
- **Des rendus par département** : un fichier aura plusieurs derniers rendus (« layout v003 · animation v005 · lighting v006 »).
  - Un **rendu principal** (celui qu'on lit et qu'on enchaîne en séquence) est choisi par le lecteur entre « plus haut département » et « plus récent ».
  - **Un rendu plus récent qu'un rendu principal d'un département plus haut est signalé** : « plus récent : animation v007 ».
- **L'attribution** : des personnes par département d'un fichier, posées en review (action « assign »). S'y ajoutent :
  - **un filtre « Moi »** (le nom saisi pour la review) ;
  - **une vue « Mon travail »** : ce qui m'est attribué et est à reprendre, mes RTK ouverts, ce qui est prêt à démarrer (l'amont est fini) et mes rendus à vérifier.
- **Pas de** tableau de charge ni de stats par personne : c'est un choix de principe, pour ne pas surveiller une petite équipe.

---

## 7. Exemple de données brutes

Ce que la page reçoit, intégré en JSON dans le fichier : un extrait d'un vrai projet (`lapins_3_oreilles`), réduit à trois fichiers. Les vignettes sont des clés vers `images`, chacune stockée une seule fois en base64 (ici tronquée). Les dates sont en ISO 8601 avec leur décalage ; une vieille donnée peut en être dépourvue.

```json
{
  "meta": {
    "project": "lapins_3_oreilles",
    "snapshot": "2026-11-04T09:59:39+01:00",
    "exported_by": "samy-r",
    "addon_version": "1.2.0",
    "roles": ["sup", "prod", "real"],
    "role": "prod",
    "weights": {"wip": 25, "rework": 50, "rtk": 50},
    "progress":   {"asset": 0.893, "shot": 0.674},
    "validation": {"asset": 0.5,   "shot": 0.497},
    "departments": {
      "shot":  ["layout", "fixanim", "render-ld", "render-hd"],
      "asset": ["modeling", "texturing", "rigging", "tech", "render"]
    },
    "schedule": {
      "start": "2026-10-05", "end": "2026-11-27",
      "expected": 0.59, "elapsed_days": 23, "total_days": 39,
      "at": {"asset": {"date": "2026-11-23", "days": 12},
             "shot":  {"date": "2026-11-10", "days": 3}}
    },
    "fps": 25,
    "videos": {"mode": "folder", "base": "../videos",
               "files": ["sq030/sh080/v003-stable_001/sq030_sh080.mp4"],
               "local": "../../renders"},
    "format": "minimalist-pipeline-review",
    "schema_version": 7,
    "review_base": "lapins_3_oreilles"
  },

  "items": [
    {
      "name": "sq030_sh080", "kind": "shot", "root": "shots", "group": "sq030",
      "desc": "Les lapins découvrent le terrier.\nPlan large, caméra fixe.",
      "file": "sq030_sh080_v004", "stable": "sq030_sh080_v003-stable",
      "versions": "wip v004 · stable v003", "stable_v": "v003",
      "render_ref": "v003-stable_001",
      "states": {"layout": "done", "fixanim": "rework", "render-ld": "done", "render-hd": "todo"},
      "scores": {"layout": 1.0, "fixanim": 0.5, "render-ld": 0.5, "render-hd": 0.0},
      "rtk": {"render-ld": "role"},
      "ok": {
        "layout": {"role": "prod", "old": false, "seen": "",
                   "tip": "sup: covered by prod\nprod: validated by Valerie (02/11/2026)\nreal: covered by prod"},
        "fixanim": {"role": "sup", "old": true, "seen": "v002-stable",
                    "tip": "Validated by sup on v002-stable: a newer stable since, to review again"}
      },
      "done": 0.5, "valid": 0.25,
      "shots": [], "thumb": "39ab65df794b", "shot_thumbs": [],
      "renders": [
        {"shots": "", "shot_list": ["sh080"], "folder": "v003-stable_001",
         "video": "sq030/sh080/v003-stable_001/sq030_sh080.mp4",
         "first": 1001, "whole": false, "behind": true,
         "status": {"state": "check", "text": "to check", "tip": "Rendered, not checked by the team yet"}}
      ],
      "outdated": true, "to_check": true,
      "farm": {"state": "running", "text": "rendering 42 %", "tip": "render-hd on pc-salle-2, frame 1063 / 1150"},
      "notes": [
        {"id": "8a32a", "type": "rtk", "done": false, "team": false, "role": "prod",
         "author": "Valerie", "date": "2026-11-03T14:12:00+01:00",
         "text": "Rallonger la fin du plan", "deps": ["render-ld"],
         "shot": "", "frames": "1120-1150", "render": "v003-stable_001",
         "version": "sq030_sh080_v003-stable.blend",
         "review": true, "approval": false, "closed": false,
         "replies": [
           {"id": "c41f0", "type": "note", "done": null, "team": true, "role": "",
            "author": "léa", "date": "2026-11-03T16:40:00+01:00",
            "text": "Il faut 20 images de plus au layout d'abord", "deps": ["render-ld"],
            "shot": "", "frames": "", "render": "", "version": "",
            "review": false, "approval": false}
         ]},
        {"id": "b7aa9", "type": "todo", "done": false, "team": true, "role": "",
         "author": "tom", "date": "2026-11-02T10:05:00+01:00",
         "text": "Vérifier les ombres du sol", "deps": [],
         "shot": "", "frames": "", "render": "", "version": "",
         "review": false, "approval": false, "closed": false, "replies": []}
      ]
    },

    {
      "name": "sq030_sh040-050", "kind": "shot", "root": "shots", "group": "sq030",
      "desc": "",
      "file": "sq030_sh040-050_v003-stable", "stable": "sq030_sh040-050_v003-stable",
      "versions": "stable v003", "stable_v": "v003", "render_ref": "v003-stable_002",
      "states": {"layout": "done", "fixanim": "done", "render-ld": "done", "render-hd": "todo"},
      "scores": {"layout": 1.0, "fixanim": 1.0, "render-ld": 1.0, "render-hd": 0.0},
      "rtk": {},
      "ok": {"layout": {"role": "prod", "old": false, "seen": "", "tip": "prod: validated by Valerie (04/11/2026)"},
             "fixanim": {"role": "prod", "old": false, "seen": "", "tip": "prod: validated by Valerie (04/11/2026)"},
             "render-ld": {"role": "prod", "old": false, "seen": "", "tip": "prod: validated by Valerie (04/11/2026)"}},
      "done": 0.75, "valid": 0.75,
      "shots": ["sh040", "sh050"],
      "thumb": "9c7af485c8e9", "shot_thumbs": [["sh040", "9c7af485c8e9"], ["sh050", null]],
      "renders": [
        {"shots": "sh040", "shot_list": ["sh040"], "folder": "v003-stable_002",
         "video": "sq030/sh040/v003-stable_002/sq030_sh040.mp4", "first": 1001,
         "whole": false, "behind": false, "status": null},
        {"shots": "sh050", "shot_list": ["sh050"], "folder": "v003-stable_002",
         "video": null, "first": null, "whole": false, "behind": false,
         "status": {"state": "failed", "text": "failed", "tip": "GPU out of memory on every machine"}}
      ],
      "outdated": false, "to_check": false,
      "farm": {"state": "failed", "text": "failed", "tip": "GPU out of memory on every machine"},
      "notes": [
        {"id": "a5865", "type": "note", "done": null, "team": false, "role": "prod",
         "author": "Valerie", "date": "2026-11-04T09:43:10+01:00",
         "text": "Validated (prod): render-ld, sq030_sh040-050_v003-stable", "deps": ["render-ld"],
         "shot": "", "frames": "", "render": "", "version": "sq030_sh040-050_v003-stable.blend",
         "review": false, "approval": true, "closed": false, "replies": []},
        {"id": "f02d1", "type": "rtk", "done": true, "team": false, "role": "sup",
         "author": "Marc", "date": "2026-10-28T11:00:00+01:00",
         "text": "[sh050] [f1012-1030] Le lapin traverse le décor", "deps": ["fixanim"],
         "shot": "sh050", "frames": "1012-1030", "render": "v002-stable_001",
         "version": "sq030_sh040-050_v002-stable.blend",
         "review": true, "approval": false, "closed": true, "replies": []}
      ]
    },

    {
      "name": "env_sol-petales", "kind": "asset", "root": "assets", "group": "env",
      "desc": "Sol de la clairière, couvert de pétales",
      "file": "env_sol-petales_v003", "stable": "env_sol-petales_v002-stable",
      "versions": "wip v003 · stable v002", "stable_v": "v002", "render_ref": "v003_001",
      "states": {"texturing": "done", "render": "wip"},
      "scores": {"texturing": 1.0, "render": 0.25},
      "rtk": {},
      "ok": {"texturing": {"role": "prod", "old": false, "seen": "", "tip": "prod: validated by Valerie (04/11/2026)"}},
      "done": 0.625, "valid": 0.5,
      "shots": [], "thumb": "a05cde7aa97a", "shot_thumbs": [],
      "renders": [
        {"shots": "", "shot_list": [""], "folder": "v003_001",
         "video": "assets/env/env_sol-petales/v003_001/env_sol-petales.mp4",
         "first": 1, "whole": false, "behind": false, "status": null}
      ],
      "outdated": false, "to_check": false, "farm": null, "notes": []
    }
  ],

  "images": {"39ab65df794b": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD…"}
}
```

**Valeurs possibles :**
- `states` : `todo` (pas commencé), `wip` (en cours), `done` (fait), `rework` (fait, retravaillé depuis). Un département absent n'est pas requis pour ce fichier.
- `rtk` : par département, `role` (d'un rôle de validation) ou `team` (de l'équipe). Les RTK généraux sont les notes `type: "rtk"`, non faites, sans `deps`.
- `ok` : la validation affichée par département. `old: true` signifie « validé sur un stable plus ancien (`seen`), à revoir ».
- `done`, `valid`, `progress`, `validation`, `expected` : des parts entre 0 et 1. `schedule.at.<onglet>.days` est l'avance (+) ou le retard (−) en jours ouvrés.
- `farm.state` et `renders[].status.state` : `running`, `waiting` (en file), `failed`, et `check` (à vérifier).
- `notes[].type` : `rtk` (retake), `todo` ou `note` (remarque). `done` vaut `null` pour une remarque. `approval: true` signale la note automatique d'une validation. `closed: true` signale un fil fini, à replier.
- `renders[].video: null` : pas de vidéo pour cette ligne. `whole: true` : un bloc rendu d'un seul tenant.

### Ce que la page produit : la review (format de la 1.2, en actions)

```json
{
  "format": "minimalist-pipeline-review", "schema_version": 8,
  "project": "lapins_3_oreilles", "snapshot": "2026-11-04T09:59:39+01:00",
  "author": "Valerie", "role": "prod", "review_date": "2026-11-05",
  "written_at": "2026-11-05T18:22:04+01:00",
  "actions": [
    {"type": "validate",    "file": "sq030_sh040-050", "department": "render-ld"},
    {"type": "unvalidate",  "file": "sq030_sh080", "department": "fixanim"},
    {"type": "rtk",         "file": "sq030_sh080", "departments": ["fixanim"],
                            "text": "Le saut arrive trop tôt", "shot": "", "frames": "1040-1060",
                            "render": "v003-stable_001"},
    {"type": "rtk",         "file": "sq030_sh080", "departments": [], "text": "Revoir la lumière générale"},
    {"type": "note",        "file": "env_sol-petales", "text": "Très joli"},
    {"type": "reply",       "to": "8a32a", "text": "note: ok, on attend le layout"},
    {"type": "fixed",       "id": "b7aa9"},
    {"type": "description", "file": "env_sol-petales", "old": "Sol de la clairière, couvert de pétales",
                            "new": "Sol de la clairière, pétales roses et blancs"},
    {"type": "still_done",  "file": "sq030_sh080", "department": "render-ld", "text": "Le rallongement ne change rien au rendu"},
    {"type": "omit",        "file": "sq030_sh090", "state": "on_hold", "reason": "en attente du montage"},
    {"type": "assign",      "file": "sq030_sh080", "department": "fixanim", "people": ["tom"]},
    {"type": "departments", "file": "sq030_sh080", "add": ["fx"], "remove": []},
    {"type": "create",      "kind": "shot", "sequence": "sq030", "name": "sh095",
                            "description": "Plan de coupe sur le terrier",
                            "frame_start": 1001, "frame_end": 1048, "departments": ["layout", "fixanim"]}
  ]
}
```

### Champs prévus pour la 1.2 (illustratifs, pas encore figés)

```json
{
  "name": "sq030_sh080",
  "states": {"layout": "done", "fixanim": "rework", "render-ld": "done", "render-hd": "todo"},
  "flags": {
    "render-ld": {"waiting": "layout RTK"},
    "fixanim":   {"to_redo": "layout changed on 12/11"},
    "render-hd": {"waiting": "render-ld not started"}
  },
  "still_done": {"render-ld": {"at": "2026-11-05T18:22:04+01:00", "by": "Valerie", "text": "…"}},
  "omit": {"state": "on_hold", "reason": "en attente du montage", "by": "Valerie", "at": "2026-11-05T18:22:04+01:00"},
  "assignees": {"fixanim": ["tom"], "layout": ["léa"]},
  "renders_by_department": [
    {"department": "render-ld", "folder": "v003-stable_001", "video": "…", "main": true,
     "newer": {"department": "fixanim", "folder": "v004_002"}},
    {"department": "fixanim", "folder": "v004_002", "video": "…", "main": false}
  ],
  "planned": false
}
```

- `flags` : la raison de chaque Waiting ou À reprendre. L'état réel (`states`) reste à côté.
- `planned: true` : un fichier créé dans une review, pas encore importé.
- `meta.team` : la liste des noms de l'équipe, pour l'attribution et le filtre « Moi ».
