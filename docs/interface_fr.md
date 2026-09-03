# Interface

*[← Index de la documentation](README.md) · [English version](interface.md)*

---

Tous les panneaux vivent dans la sidebar de la vue 3D (`N` > onglet **Pipeline**), plus quelques popups pour les vues d'ensemble.

| Panneau | Toujours visible ? | Contenu |
|---|---|---|
| **Project** | Oui | Projet actif (nom, dossier, config), boutons New asset / New shot / Batch create from CSV / Open file / Render / Open folder, bouton Monitoring (voir plus bas). Liste dépliable des autres projets connus (activer / éditer / retirer chacun), New project / Find existing project. |
| **Asset** | Si le fichier ouvert est un asset/library | Boutons bascule "départements travaillés cette session" (si le fichier a des départements requis), Increment version, Mark as stable, Render, Open folder. |
| **Shot** | Si le fichier ouvert est un shot | Mêmes actions que le panneau Asset, plus Preview block / Preview sequence, et Branch block (voir [Blocs de shots (multishot)](multishot_fr.md)). |
| **Tracking** | Si le fichier ouvert appartient au projet actif | État par département du fichier courant, liste de ses notes/todos/rtk en place, avec édition/validation directe. Version "toujours visible" du popup de détail décrit plus bas. Voir [Suivi & revues](tracking-and-reviews_fr.md). |
| **Farm** | Si un projet est actif | En-tête : statut du monitor (arrêté / tournant / périmé) avec bouton Lancer/Tuer. Corps : bouton ouvrant le dashboard farm (voir plus bas). Voir [Rendu (farm)](farm_fr.md). |

<br>

## Popups de vue d'ensemble

Accessibles depuis les boutons ci-dessus, pas des panneaux permanents :

- **Monitoring projet** (bouton "Monitoring" du panneau Project) : tous les fichiers du projet avec leur état par département, filtrable par préfixe (assets) ou séquence (shots). Cliquer un fichier ouvre son détail — description, temps de travail total loggé (toutes versions, tout le monde confondu — voir [Choix de conception](design_fr.md), "La durée de travail est loggée, jamais affichée par personne"), notes/todos complets, création d'entrée, import CSV.
- **Dashboard farm** (bouton du panneau Farm) : deux vues, *Jobs* (chaque job actif avec son étage courant et sa progression, un bouton "X" pour annuler un rendu en cours, un bouton "✓" pour archiver un job terminé/échoué une fois qu'il ne sert plus à rien dans la liste) et *Workers* (chaque machine connue, idle ou en train de rendre quoi, avec le même bouton d'annulation ciblé sur cette machine), plus le bouton pour ajouter/retirer ce poste comme worker.

<br>

## Menu top bar

Un menu "Pipeline" apparaît dans la barre du haut (à côté de File/Edit/Render...), pour ne pas avoir à ouvrir la sidebar pour les actions courantes — même contenu que les panneaux ci-dessus (création, ouverture, rendu, save/increment/mark-stable sur le fichier courant, rôles farm), condensé en un seul menu.

Sous "Open file", jusqu'à 3 fichiers récemment ouverts — les tiens, pas ceux d'un collègue, et jamais le fichier déjà ouvert. Pas une liste séparée : dérivée de `sessions_log.jsonl` à chaque fois, donc automatiquement cantonnée au projet actif et ne peut pas en dériver. Un clic rouvre, pas de popup.

Même ligne, tout à gauche — avant l'icône Blender, avant File/Edit/Render, avant "Pipeline" aussi : un label rouge "READ-ONLY" apparaît dès que le fichier courant est en lecture seule pour cette session (`-stable`, verrouillé par quelqu'un d'autre, `always_read_only`, ou déjà en lecture seule plus tôt dans cette même session) — toujours visible quel que soit l'onglet de la sidebar ouvert, là où sont le bouton Save du menu File et l'icône save de la barre du haut, les deux façons de sauvegarder qui ne passent pas par la garde Ctrl+S (voir [Limites connues actuelles](limitations_fr.md)). La petite flèche juste après ouvre la raison (laquelle des raisons ci-dessus) et, sauf si c'est un verrou posé par quelqu'un d'autre, un bouton Incrémenter pour obtenir une copie modifiable sur-le-champ.

---

**Voir aussi** : [Structure de projet, nommage, création en masse](project-and-naming_fr.md) · [Versions : wip et stable](versions_fr.md) pour ce que font vraiment Increment/Mark as stable.
