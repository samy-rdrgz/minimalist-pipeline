# Page snapshot v7 : incohérences et questions à trancher

Relevées en lisant `HANDOFF.md`, la guideline / roadmap et les sources de la
maquette v7, et en faisant la phase 0. Chaque point : le constat, puis une
proposition, et la décision quand elle est prise.

## Structure du chantier

1. **Phase 0 contredit « ancienne page figée ».** La phase 0 découpe la page
   *actuelle* en modules au format v7 (`core/`, `desktop/`, …), puis les
   phases 1 à 10 la réécrivent. Mais pendant la bêta les deux pages doivent
   coexister (préférence `classic` / `v2`, ancienne page figée). Elles ne
   peuvent pas partager les mêmes fichiers.
   *Proposition :* `templates/snapshot/` = la page classique (découpée à plat
   en phase 0, sans plus y toucher) et `templates/snapshot_v2/` = les sources
   de la maquette, qui deviennent la v2. `render_page()` choisit l'arbre
   selon la préférence.
   **Décidé :** pas de bêta. La page v7 remplace directement la classique.
   *Fait en phase 0 :* le découpage à plat (`js/NN-nom.js`, `css/NN-nom.css`)
   aux séparateurs existants. La page classique ne suit pas la règle
   `core/` / `desktop/`, donc ces dossiers auraient été trompeurs.

2. **La règle « `core/` ne touche jamais au DOM » n'est pas tenue par la
   maquette elle-même** : `core/00-data.js`, `05-mode.js` et `40-player.js`
   utilisent `document`. *Proposition :* déplacer le lecteur dans
   `desktop/` + `mobile/` (ou dans un `ui/` partagé), et garder la règle.

3. **Le contrat de données n'a pas de phase.** `demo-data.json` (« export
   réel ») n'a pas la forme de `page_data()` de la branche 2.0 :
   `toCheck` / `to_check`, `linkedBy`, `versions` en liste d'objets ou en
   texte, `wip` / `render` / `work` absents de l'export, et à l'inverse
   `stable_v`, `wip_v`, `renders`, `shot_thumbs`, `weights`, `naming`,
   `review_base`… absents de la démo. La roadmap ne prévoit de changement de
   format qu'en phase 6 (liens). La page classique ne peut pas lire la démo
   (fixture de la phase 0 convertie à la main, sans rendus ni farm).
   **Décidé :** la page lit le format de l'addon (`page_data()`), traduit
   pour les vues dans `core/00-data.js`. Fait.
   *Proposition d'origine :* une phase 0.5 « contrat de données » : un seul format,
   écrit par `page_data()` et documenté, `SCHEMA_VERSION` + 1 une seule fois,
   et la démo régénérée depuis un vrai export.

4. **Données nouvelles non signalées.** Le temps de travail (`work`,
   phase 3), les liens hors ligne (phase 6, signalé), la langue (`meta.lang`)
   et le thème ne sont pas dans l'export actuel. La langue, comme le thème,
   demande `bpy` sur le thread principal avant `SnapshotJob`.
   *Proposition :* lire langue + thème + échelle ensemble en phase 1
   (`read_theme()` → `read_prefs()`).

5. **Préférence `snapshot_ui` en phase 0** : il n'y a encore rien à choisir.
   Pas ajoutée. *Proposition :* l'ajouter avec la première page v2 qui sort
   (phase 1 ou 2).

6. **Noms de fichiers de la roadmap ≠ découpage de la phase 0.** Les phases
   2 à 9 citent `page.css`, `glyph.js`, `chrome.js`, `list.js`, `synth.js`,
   `detail.js`, `player.js`, `review.js` ; la phase 0 et la maquette ont
   `10-status.js`, `20-top-tree.js`, `22-detail.js`… et aucun fichier
   Synthèse (son code est réparti dans `20-top-tree`, `21-list`,
   `27-review`, `29-events`). *Proposition :* réécrire les listes de
   fichiers de la roadmap avec les vrais noms, et un `desktop/30-synth.js`.

7. **Seuils mobile.** Bascule mobile à 900 px (§4b), détail en feuille sous
   860 px (§4), cibles de 36 px sous 860 px (§9). *Proposition :* un seul
   seuil (860 ou 900), en jeton.

## Couleurs et états

8. **Vert = « fini » mais aussi le bouton « Valider ».** P2 : vert = fini,
   violet = validé. §5 : bouton valider vert. On clique du vert pour obtenir
   du violet. **Fait :** bouton Valider violet.

9. **Un même coin orange ↻ pour deux choses différentes** : « repris depuis
   le stable » (`rework`, un état de base dans `lib/status.py`) et « à
   refaire » (`flags.to_redo`, une étape d'avant a changé). La page actuelle
   les distingue (losange ouvert vs flèche). **Fait :** deux signes. Repris
   = losange vert avec une flèche dedans ; à refaire = coin orange.

10. **Couleurs en dur hors `:root`** malgré la règle : dans le JS de la
    maquette (`10-status.js` : `#2a1d08`, `#0d1d3a`, `#1b1b1b` ;
    `23-farm.js` : `#6ea4ff`, `#9a9a9a`, `#e5575f`, `#5fb88a` ;
    `28-dialogs.js`). *Proposition :* passer par `var(--st-*)` dès la
    phase 1, l'audit de la feuille de composants doit aussi lire le JS.
    *En partie fait :* l'encre des glyphes passe par `--on-st`. Restent la
    Farm et les dialogues.

11. **Couleurs d'état fixes, mais « votre revue » = bleu de sélection.** Si
    `--sel` suit le thème Blender, le coin « vous » change de couleur d'un
    poste à l'autre. *Proposition :* un `--st-you` fixe, distinct de `--sel`.

12. **Clés de stockage.** La roadmap dit de garder `mp-snapshot:theme` ; la
    maquette écrit `snap-theme` et `snap3-scale`. Une revue en cours est
    gardée sous `mp-review:<projet>:<snapshot>` : si la v2 change de clé, les
    revues en cours sont perdues au passage. **Décidé :** pas grave (2.0.0
    pas publiée). Les clés restent préfixées `mp-`.

## Icônes (consigne : celles de Blender d'abord)

Correspondance faite : voir `NOTES.md`, « Snapshot page v7: Blender's
icons ». Restent à trancher :

13. **Farm : deux icônes.** Onglet du haut `i-film` (FILE_MOVIE), onglet
    mobile `i-render`. **Fait :** RENDER_ANIMATION partout.
14. **Version précédente / suivante** : la maquette dessine ⏪ ⏩, soit
    REW / FF dans Blender, qui veulent dire « aller au début / à la fin »,
    juste à côté de frame -1 / +1. Mis BACK / FORWARD (← →).
15. **« Lecteur de cette machine »** (`i-ext`) : pas d'icône Blender
    évidente. Mis URL. Autres possibilités : WINDOW, FILEBROWSER.
16. **« En grand »** (`i-big`) vs **plein écran** (`i-full`) : WINDOW et
    FULLSCREEN_ENTER. À valider.
17. **Boucle** (`i-loop`) : FILE_REFRESH (Blender n'a pas d'icône de
    boucle de lecture).
18. **Cloche** (« Quoi de neuf ») : Blender n'en a pas. Gardée custom. Autre
    piste : INFO, l'éditeur où Blender range ses messages.
19. **Notes** (`i-note`, bulle) : gardée custom, c'est un signe d'état (la
    bulle sous le losange). Autre piste : TEXT.
20. **Sablier** : `SORTTIME` était déjà dans `icons/` (identique à celui
    envoyé).

## Nouveaux points (port de la maquette)

21. **Envoi en live : bouton ou automatique ?** La page classique envoyait
    chaque changement à Blender 300 ms après. La maquette v7 a un bouton
    « Envoyer… ». **Décidé :** automatique. Fait.
22. **Frames des notes.** La démo a des notes en `f12`, `f5-20` alors que
    les rendus commencent à 1001. La page écrit maintenant les numéros de
    Blender (1001…) dès que le rendu donne sa première frame. Les notes
    déjà écrites en numéros relatifs tombent hors de la timeline.
23. **Ce que la v7 n'a pas encore** (la classique l'avait) : « Partager
    avec un téléphone » (accès invité + QR), « Mettre à jour les liens »
    (pas de route live). **L'option son du rendu est faite** : le son de la
    scène est maintenant dans la vidéo, sauf si on le coupe.
24. **Langue.** Tous les textes de la maquette sont en français, alors
    que l'addon est en anglais. Passage par `T()` à faire (gros lot).
