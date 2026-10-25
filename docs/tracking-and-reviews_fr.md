# Suivi & revues

*[← Index de la documentation](README.md) · [English version](tracking-and-reviews.md)*

---

Chaque asset/shot a un dossier `.pipeline/` à côté de ses fichiers `.blend` :

- **`tracking.json`** : départements requis + une description libre de ce qu'est l'asset/shot (définie à la création — interactivement ou via CSV en masse, voir [Structure de projet, nommage, création en masse](project-and-naming_fr.md)) + liste d'entrées (`note` / `todo` / `rtk`), chacune avec auteur, date, son ou ses départements, état fait/pas fait.
- **`{version}.wipmeta`** : une par version de travail — mode de création, départements travaillés cette session, libs liées. Détails complets dans [Versions : wip et stable](versions_fr.md).
- **`{version}.stablemeta`** : une par version `-stable` — départements validés à ce moment-là. C'est le point de référence pour calculer "qu'est-ce qui a été retouché depuis le dernier stable" affiché partout dans l'UI. Un département peut aussi être validé directement, sans republier de version `-stable` — boutons à côté de chaque département dans le panneau Tracking/le dashboard, pour les départements (comme "render") qui ne sont pas liés à une modification du fichier. Ça mute le `departments_validated` du dernier stablemeta en place ; nécessite qu'au moins une version `-stable` existe déjà.

**Import de review prod** (panneau Projet ou menu Pipeline > *Import review*) : relit le tableur de review d'un snapshot, tel quel. Chaque ligne de texte d'une case de département devient un retake séparé (voir *Tableur de review* plus bas ; une cellule *text* dans un tableur d'avant la 1.1.2) — plusieurs retakes sur le même plan vont sur plusieurs lignes (Alt+Entrée), chacune avec sa case à cocher. Auteur et date viennent du haut de la feuille (`prod` et le jour de l'import s'ils sont vides) ; chaque note est ancrée sur la version que montrait le snapshot. Réimporter le même fichier, ou un fichier renvoyé avec des notes en plus, ne crée jamais de doublon : les lignes déjà importées sont ignorées. Les descriptions modifiées dans la colonne *description* (éditable pour ça) sont appliquées aussi, après un dialogue qui liste chaque changement (avant / après) : toutes, ou aucune — pour en écarter une, corriger le tableur et le réimporter. Seule une cellule modifiée par la prod compte : une description changée dans le projet depuis l'export n'est jamais remise à l'ancienne, et une cellule vide ne change rien. Un tableur exporté avant la 1.0.12 voit ses descriptions ignorées. Une popup liste ce qui est entré et ce qui n'a pas pu (ex : un fichier renommé ou branché depuis). Les entrées importées l'indiquent dans leur infobulle.

**Snapshot de prod** (panneau Projet ou menu Pipeline > *Snapshot*) : écrit un seul fichier HTML — `<projet>_snapshot_<AAAA-MM-JJ>.html` — avec l'état de chaque asset/shot par département et toutes les notes (todos/RTK fermés compris, masqués tant que "Show closed" n'est pas coché), pour les personnes hors studio (pas besoin de Blender ni d'accès au partage : il s'ouvre hors ligne dans n'importe quel navigateur et s'envoie par mail). Chaque département affiche *Not started* (jamais travaillé ni validé), *WIP* (en cours : travaillé depuis le dernier stable, ou validé sur un stable antérieur ou travaillé avant le dernier mais pas validé dessus -- rouvert, ou pas encore fini), *Done* (fini) ou *Reworked* (fini au dernier stable mais retravaillé depuis), avec à côté sa validation par un rôle (voir plus bas). Le Monitoring projet affiche la même chose. Une colonne "Done" montre l'avancement de chaque asset/shot — chaque département requis compte pour une part égale : pas commencé 0 %, en cours 33 %, validé mais retravaillé depuis 67 %, validé avec un RTK ouvert 67 %, validé 100 % (les trois valeurs du milieu se règlent par projet : Project settings > *Snapshot done*) ; un département avec un RTK ouvert est entouré de rouge, quel que soit son état — avec le % de chaque séquence / préfixe d'asset sur sa ligne de groupe et une ligne "All" par tableau (total de la section et % par département). Un bloc *Progress* en haut résume tout le projet (filtres à part) : le Done des shots et des assets & libraries, les RTK ouverts, puis par section une barre de ses tâches de département par état, aux couleurs des capsules (validé, retravaillé, RTK ouvert -- quel que soit l'état --, WIP, pas commencé) et son Done par séquence / préfixe et par département, puis une grille séquence (ou préfixe) × département, chaque case teintée selon son %. Avec un planning (Project settings > *Schedule* : dates de début et de fin, jours fériés, et jours travaillés de la semaine -- du lundi au vendredi par défaut), il donne aussi où le projet devrait en être à rythme régulier le jour de l'export -- jours ouvrés écoulés sur ceux du planning --, l'avance ou le retard de chaque section, et son rythme (fait / attendu) dans une pastille colorée par palier, comme dans un tableur de suivi : 105 % et plus en avance (vert), 100 à 105 % dans les temps (vert clair), 90 à 100 % léger retard (ambre), moins de 90 % en retard (rouge) ; l'avancement attendu est un trait sur chaque barre, et une bande *Schedule* par section met les deux sur une même échelle d'avancement prévu (0 % à la date de début, 100 % à la date de fin) : l'avancement attendu aujourd'hui en trait, le Done de la section en remplissage, l'écart entre les deux en vert clair si on est en avance, en rouge si on est en retard ("▲ 18 pts, 7 working days ahead"). Chaque section de la page (Progress, Assets, Shots) se replie d'un clic sur son titre ; toutes sont ouvertes au chargement, et un lien vers une section repliée l'ouvre. Les en-têtes de colonnes des tableaux Assets et Shots restent en haut de l'écran, sous les filtres, pendant qu'on fait défiler le tableau. Les exports vont par défaut dans le dossier `snapshots/` du projet, nommés avec la date et l'heure. Une colonne "Last render" donne le dossier de sortie du dernier rendu de chaque asset/shot (vXXX_YYY : la version du .blend rendue, puis l'incrément du rendu), en rouge s'il a été rendu depuis une version plus ancienne que la dernière stable, chaque ligne commençant par sa capsule de statut, alignée sur toute la hauteur du tableau : *to check* tant que l'équipe ne l'a pas vérifié, puis les jobs encore dans la farm au moment de l'export — *queued*, leur étape en bleu (*rendering 45/120*, *compiling*...), *failed* en rouge. Un multishot a aussi, sous sa vignette, un petit bouton par shot (010, 020...) dans l'ordre du bloc : le survoler affiche la vignette de ce shot, pour se repérer dans un montage -- grisé pour un shot pas encore rendu. Chaque asset/plan affiche une vignette de son dernier rendu (la farm la crée à la fin d'un rendu ; l'export crée celles qui manquent ou sont périmées, à partir des frames déjà sur le disque). Filtrable par nom, groupe (préfixe/séquence), département et état, RTK ouverts ou notes ouvertes, ou "Farm" (dans la farm ou à vérifier), et un menu *Columns* masque les colonnes inutiles (mémorisé par le navigateur) ; chaque ligne qui a des notes a un bouton "n notes" qui les déplie juste en dessous, et *Notes* dans la barre du haut les déplie (ou replie) toutes -- l'impression sort toutes les notes ouvertes. La page contient un tableur de review (.xlsx) à télécharger, une ligne par asset/shot, que la prod remplit et renvoie. Le scan tourne en arrière-plan ; Blender reste utilisable pendant ce temps. Une fois écrit, il s'ouvre dans le navigateur (*Open when done*, à côté de *Thumbnails* dans le sélecteur de fichier ; décocher pour juste l'enregistrer).

<img src="images/tracking-snapshot-progress.png" alt="Le snapshot de prod : l'avancement">

<img src="images/tracking-snapshot-details.png" alt="Le snapshot de prod : assets et shots">

Le Monitoring projet (panneau Project ou menu Pipeline), une fenêtre à part : la liste de tous les fichiers avec leur état par département, et le détail d'un fichier (notes/todos, avec un clic pour valider un `rtk`, et son temps de travail total loggé — voir [Choix de conception](design_fr.md), "La durée de travail est loggée, jamais affichée par personne", pour ce que ce total est et n'est pas). Décrits dans [Interface](interface_fr.md#fenêtres-de-vue-densemble).

Un bloc multishot peut taguer une note/todo avec le shot du bloc concerné — voir [Blocs de shots (multishot)](multishot_fr.md).

**Rendus à vérifier** : quand un job farm se termine (frames vérifiées, vidéo compilée), son rendu attend une vérification. Le Project monitoring l'affiche dans sa colonne "Farm" sous forme de bouton (clic pour la lire), à côté de l'icône du popup Farm pour chaque job du fichier encore dans la farm (soumis, en file d'attente, en attente entre deux étapes, en cours, en échec) — une par shot, côte à côte pour un bloc ; le survol d'une icône donne son shot, sa version et son étape (rendering 45/120, compiling...). Le bouton coche qui suit marque les rendus à vérifier comme vérifiés ; une icône de filtre (caméra) n'affiche que les fichiers qui ont une icône dans cette colonne. Une légende de ces icônes est en bas du tableau, à côté du nombre de fichiers. Le détail du fichier les liste dans leur propre box (date, vidéo, le rendu précédent -- pour lire la version d'avant du shot et comparer --, dossier, "Checked"), avec en dessous une box "In the farm" pour ses jobs encore dans la farm (shot, version, étape), à côté du dernier rendu de chaque shot, vérifié ou non. Marquer un rendu vérifié archive aussi son job farm, et affiche tous les départements du fichier, cochés selon leur validation actuelle ("render" coché en plus) : en décocher un que le rendu montre pas au point le dévalide (il faut une version stable, comme pour toute validation de département à la main). Un bloc en garde un par shot ; un rendu plus récent d'un shot remplace l'ancien.

<img src="images/ui-file-details.png" alt="Le détail d'un fichier : départements, dernier rendu, rendus à vérifier, notes">

---

## Fini, puis validé : les rôles de validation

Un département est **fini** (*done*) quand son travail est terminé (la
coche à côté de lui -- appelée « validé » avant la 1.1.2, mêmes données).
La **validation** vient par-dessus : l'accord d'un rôle -- le superviseur,
la prod -- sur la version qu'il a vue.

- **Les rôles** se règlent par projet (Edit project > *Validation roles*,
  par ex. `sup:1,prod:2,real:2`) : un niveau plus haut couvre les plus bas
  (validé par la prod : bon pour le sup aussi), le même niveau est
  équivalent (prod ou real). Sans réglage, `sup:1,prod:2`.
- **Votre rôle** : Préférences > *Validation role*. Vide : membre de
  l'équipe.
- **Valider** : dans le détail d'un fichier, une étoile à côté de chaque
  département fini donne ou retire la validation de votre rôle (son
  infobulle liste chaque rôle : validé, couvert par un plus haut, ou non).
  Elle est gardée sur le dernier stable : un nouveau stable repart sans --
  le rôle ne l'a pas vu -- et affiche la dernière donnée (« prod : v012, à
  revoir »). La donner ou la retirer écrit une note sous votre rôle, pour
  la trace.
- **Notes sous un rôle** : une note, todo ou RTK écrite par quelqu'un qui a
  un rôle le porte (marque violette), comme les notes importées d'un
  tableur de review. Un RTK d'un rôle est rouge, celui de l'équipe orange.
  La fenêtre *New entry* montre votre rôle dans une case *As sup*, cochée
  par défaut : décochez-la pour écrire au nom de l'équipe (une note
  technique, par exemple).
- **Project monitoring** : un département fini affiche « Done · prod » une
  fois validé ; un filtre (l'étoile) liste les fichiers dont un département
  fini reste à valider -- pour votre rôle, ou par n'importe quel rôle si
  vous n'en avez pas.
- **Snapshot** : « ✓ prod » à côté de la capsule d'un département (chaque
  rôle dans son infobulle), « prod v012 » en gris pour une validation
  donnée sur un stable antérieur. Un chiffre *Validated* s'affiche à part
  du Done -- une tuile par section, une colonne, les groupes et les totaux,
  en violet : la part des départements requis validés par le rôle le plus
  haut (ou un de son niveau) au stable affiché. Le Done reste la
  fabrication : 100 % fini sans rien de validé donne 100 % / 0 %.
- **Tableur de review** : un premier onglet *Review* pour votre nom, la
  date de review et votre *Role* (obligatoire dès que le fichier contient
  un retake ou une validation), le mode d'emploi et la légende des
  couleurs ; puis un onglet *Shots* et un onglet *Assets*, une ligne par
  fichier et **une case par département** (seulement ceux de la
  section), colorée selon son état au snapshot : blanc pas commencé,
  ambre en cours, vert clair fini mais retravaillé depuis, vert fini -- à
  valider --, violet déjà validé par le rôle le plus haut ; une bordure
  rouge pour un retake ouvert ; gris « – » non requis (verrouillé).
  - `ok` (ou `yes`, `oui`, `v`, `✓`...) valide le département pour votre
    rôle -- refusé s'il n'est pas fini.
  - `no` retire cette validation.
  - tout autre texte la retire aussi, et **chaque ligne devient un
    retake** (RTK) de ce département -- Alt+Entrée pour la ligne suivante.
    Commencez une ligne par `[sh020]` pour un shot d'un bloc, `[f12-40]`
    (ou `[f12]`) pour ses frames, dans n'importe quel ordre :
    `[sh020] [f12-40] caméra plus haute` ; par `note:` pour une remarque
    plutôt qu'un retake. Un tag qui n'en est pas un -- un shot hors du
    bloc, un intervalle à l'envers comme `[f40-12]` -- reste dans le texte.
  - *global* : `ok` valide tous les départements déjà finis (la case
    propre d'un département l'emporte), un texte est un retake sans
    département particulier.
  - vide : rien ne change.

  L'import demande d'abord, en rappelant le rôle et la liste des
  validations, puis refuse toute validation d'un fichier qui a un stable
  plus récent que le snapshot. Un tableur exporté par une version
  précédente s'importe toujours, lu comme avant.

Rien à migrer : `departments_validated` garde son nom, les validations
sont une nouvelle clé `approvals` du stablemeta, le rôle d'une note une
nouvelle clé `role` -- absente, celle de l'équipe.

## Structure de données : `tracking.json`

**`assets/ch/ch_bob/.pipeline/tracking.json`** — un par asset/shot, créé avec le fichier :

```json
{
  "file_name": "ch_bob",
  "created_at": "2026-03-25T16:00:00",
  "departments_required": ["modeling", "rigging", "texturing"],
  "description": "Personnage principal, le renard.",
  "entries": [
    {
      "id": "a3f1c",
      "type": "todo",
      "text": "Ajouter les shape keys du visage",
      "author": "samy",
      "date": "2026-03-21T09:00:00",
      "department": "rigging",
      "done": false
    }
  ]
}
```

`type` vaut `note` (`done: null`, jamais cochable), `todo` ou `rtk` (retour à corriger — `done: true/false`, avec `done_by`/`done_at` une fois validé).

**New entry** : une entrée par ligne, quel que soit le type (RTK par défaut) -- chaque ligne ses propres départements, frames et, dans un bloc, shot. Les départements s'affichent toujours dans l'ordre du projet (Edit project), partout où ils sont listés.

<img src="images/tracking-new-entry.png" alt="Le dialogue New entry" width="560">

**Plusieurs départements** : une entrée peut concerner plusieurs départements à la fois -- les cocher dans le menu département des dialogues New entry / Edit. C'est une seule entrée avec un seul état fait, affichée sous le filtre de chacun de ses départements ; une RTK ouverte met chacun de ses départements en rouge (Project monitoring, snapshot). Stocké en `"departments": ["animation", "lighting"]` à côté de `"department"` (le premier, ce que lit un addon d'avant la 1.1.0). La cellule département d'un tableur de review en accepte plusieurs aussi : `layout, lighting` (`,` `;` `/` `+`).

Un rendu farm terminé ajoute une clé `to_check`, jusqu'à ce qu'il soit marqué vérifié : `{"<shot>": {"render", "video", "at", "job_id"}}` — le shot vaut `""` pour un asset ou un shot seul, une clé par shot pour un bloc.

---

**Voir aussi** : [Versions : wip et stable](versions_fr.md) pour `.wipmeta`/`.stablemeta` · [Interface](interface_fr.md) pour le panneau Tracking et les fenêtres de monitoring.
