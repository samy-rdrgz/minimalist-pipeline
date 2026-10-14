# Suivi & revues

*[← Index de la documentation](README.md) · [English version](tracking-and-reviews.md)*

---

Chaque asset/shot a un dossier `.pipeline/` à côté de ses fichiers `.blend` :

- **`tracking.json`** : départements requis + une description libre de ce qu'est l'asset/shot (définie à la création — interactivement ou via CSV en masse, voir [Structure de projet, nommage, création en masse](project-and-naming_fr.md)) + liste d'entrées (`note` / `todo` / `rtk`), chacune avec auteur, date, département, état fait/pas fait.
- **`{version}.wipmeta`** : une par version de travail — mode de création, départements travaillés cette session, libs liées. Détails complets dans [Versions : wip et stable](versions_fr.md).
- **`{version}.stablemeta`** : une par version `-stable` — départements validés à ce moment-là. C'est le point de référence pour calculer "qu'est-ce qui a été retouché depuis le dernier stable" affiché partout dans l'UI. Un département peut aussi être validé directement, sans republier de version `-stable` — boutons à côté de chaque département dans le panneau Tracking/le dashboard, pour les départements (comme "render") qui ne sont pas liés à une modification du fichier. Ça mute le `departments_validated` du dernier stablemeta en place ; nécessite qu'au moins une version `-stable` existe déjà.

**Import de review prod** (panneau Projet ou menu Pipeline > *Import prod review*) : relit le tableur de review d'un snapshot, tel quel. Chaque ligne d'une cellule *text* devient une entrée séparée — plusieurs retakes sur le même plan vont sur plusieurs lignes (Alt+Entrée), chacune avec sa case à cocher. Auteur et date viennent du haut de la feuille (`prod` et le jour de l'import s'ils sont vides) ; chaque note est ancrée sur la version que montrait le snapshot. Réimporter le même fichier, ou un fichier renvoyé avec des notes en plus, ne crée jamais de doublon : les lignes déjà importées sont ignorées. Les descriptions modifiées dans la colonne *description* (éditable pour ça) sont appliquées aussi, après un dialogue qui liste chaque changement (avant / après) : toutes, ou aucune — pour en écarter une, corriger le tableur et le réimporter. Seule une cellule modifiée par la prod compte : une description changée dans le projet depuis l'export n'est jamais remise à l'ancienne, et une cellule vide ne change rien. Un tableur exporté avant la 1.0.12 voit ses descriptions ignorées. Une popup liste ce qui est entré et ce qui n'a pas pu (ex : un fichier renommé ou branché depuis). Les entrées importées l'indiquent dans leur infobulle.

**Snapshot de prod** (panneau Projet > *Export prod snapshot*) : écrit un seul fichier HTML — `<projet>_snapshot_<AAAA-MM-JJ>.html` — avec l'état de chaque asset/shot par département et toutes les notes (todos/RTK fermés compris, masqués tant que "Show closed" n'est pas coché), pour les personnes hors studio (pas besoin de Blender ni d'accès au partage : il s'ouvre hors ligne dans n'importe quel navigateur et s'envoie par mail). Chaque département affiche *Not started*, *Work in progress*, *Validated* ou *Validated, reworked since* (validé au dernier stable mais retravaillé depuis). Une colonne "Done" montre l'avancement de chaque asset/shot — chaque département requis compte pour une part égale : par tiers : en cours 1/3, validé mais retravaillé depuis ou avec un RTK ouvert 2/3, validé 3/3 ; un département validé avec un RTK ouvert est entouré de rouge — avec le % de chaque séquence / préfixe d'asset sur sa ligne de groupe, une ligne "All" par tableau (total de la section et % par département) et deux totaux en haut (assets & libraries, shots). Les exports vont par défaut dans le dossier `snapshots/` du projet, nommés avec la date et l'heure. Une colonne "Last render" donne le dossier de sortie du dernier rendu de chaque asset/shot (vXXX_YYY : la version du .blend rendue, puis l'incrément du rendu), en rouge s'il a été rendu depuis une version plus ancienne que la dernière stable. Chaque asset/plan affiche une vignette de son dernier rendu (la farm la crée à la fin d'un rendu ; l'export crée celles qui manquent ou sont périmées, à partir des frames déjà sur le disque). Filtrable par nom, groupe (préfixe/séquence), département et état, RTK ouverts ou notes ouvertes ; chaque ligne qui a des notes y renvoie directement. La page contient un tableur de review (.xlsx) à télécharger, une ligne par asset/shot, que la prod remplit et renvoie. Le scan tourne en arrière-plan ; Blender reste utilisable pendant ce temps.

Deux popups de monitoring project-wide (menu Projet) : la liste de tous les fichiers avec leur état par département, et le détail d'un fichier (notes/todos, avec un clic pour valider un `rtk`, et son temps de travail total loggé — voir [Choix de conception](design_fr.md), "La durée de travail est loggée, jamais affichée par personne", pour ce que ce total est et n'est pas). Les deux sont décrites dans [Interface](interface_fr.md#popups-de-vue-densemble).

Un bloc multishot peut taguer une note/todo avec le shot du bloc concerné — voir [Blocs de shots (multishot)](multishot_fr.md).

**Rendus à vérifier** : quand un job farm se termine (frames vérifiées, vidéo compilée), son rendu attend une vérification. Le Project monitoring l'affiche dans sa colonne "To check" — un bouton vidéo le lit, la case à cocher le marque vérifié — et une icône œil dans ses filtres n'affiche que les fichiers qui en ont un en attente. Le détail du fichier les liste dans leur propre box (date, vidéo, dossier, "Checked"), à côté du dernier rendu de chaque shot, vérifié ou non. Marquer un rendu vérifié archive aussi son job farm, et propose de valider les départements du fichier pas encore validés ("render" coché par défaut ; il faut une version stable, comme pour toute validation de département à la main). Un bloc en garde un par shot ; un rendu plus récent d'un shot remplace l'ancien.

---

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

Un rendu farm terminé ajoute une clé `to_check`, jusqu'à ce qu'il soit marqué vérifié : `{"<shot>": {"render", "video", "at", "job_id"}}` — le shot vaut `""` pour un asset ou un shot seul, une clé par shot pour un bloc.

---

**Voir aussi** : [Versions : wip et stable](versions_fr.md) pour `.wipmeta`/`.stablemeta` · [Interface](interface_fr.md) pour le panneau Tracking et les deux popups de monitoring.
