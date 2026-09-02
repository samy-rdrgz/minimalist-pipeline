# Minimalist Pipeline

*[English version: README.md](README.md)*

Addon Blender de pipeline léger pour artistes solo et petites équipes (2-5), full Blender, sans dépendance externe ni serveur à installer.

**Auteur** : Samy Rodriguez · **Version** : 1.0.1 · **Blender** : 4.2+

---

## Sommaire

- [En bref](#en-bref)
- [Pour qui, pourquoi](#pour-qui-pourquoi)
- [Installation](#installation)
- [Concepts](#concepts)
- [Interface](#interface)
- [Choix de conception](#choix-de-conception)
- [Limites connues actuelles](#limites-connues-actuelles)
- [Documentation](#documentation)

---

## En bref

- Créer un asset ou un shot et taper un nom — l'addon construit le bon nom de fichier, le bon dossier, et le fichier de suivi pour vous.
- Travailler et sauvegarder (Ctrl+S) comme d'habitude — le versioning et le filet de sécurité `-stable` tournent en dessous, et n'interrompent que quand une vraie décision est nécessaire.
- Soumettre un rendu depuis n'importe quel poste qui a le projet ouvert — pas de logiciel de farm à installer, pas de serveur à configurer.
- Tout atterrit en JSON simple et lisible à côté des fichiers — rien d'enfermé dans une base de données que seul l'addon peut lire.

Nouveau ici ? **[Prise en main](docs/getting-started_fr.md)** détaille un premier projet clic par clic, sans jargon. Les sections ci-dessous vont plus loin, concept par concept.

---

## Pour qui, pourquoi

**Cible** : artistes 3D solo ou petites équipes, sans budget/temps pour Shotgrid ou une pipeline studio.

**Problème résolu** : l'entre-deux entre le chaos artisanal (`vfinale_lavrai02.blend`) et les usines à gaz. L'addon structure le *rangement* — nommage, dossiers, versions, verrouillage léger — sans imposer de workflow artistique.

**Philosophie** :
- **Détecter → Informer → Proposer → Exécuter si validé.** L'addon ne fait jamais rien en silence, mais ne bloque jamais non plus le travail. Toute automatisation passe par une popup avec un choix explicite.
- **Warning, pas blocage.** Même sur un fichier `-stable`, l'artiste peut écraser s'il le décide vraiment.
- **Lisible sans l'outil.** Tout est stocké en JSON humainement lisible à côté des fichiers `.blend`. Si l'addon disparaît demain, les noms de fichiers et l'historique gardent du sens.

---

## Installation

Addon Blender standard : `Edit > Preferences > Add-ons > Install`, sélectionner le dossier (ou son zip), activer. `blender_manifest.toml` à la racine décrit l'addon pour la plateforme Extensions de Blender (4.2+) — `bl_info` dans `__init__.py` reste la source pour le système d'addons legacy ; les deux numéros de version doivent être maintenus manuellement en phase.

**Minimum réel : Blender 4.2**, pas 4.1 : plusieurs panneaux et popups (`farm_ops.py`, `project_ops.py`, `tracking_ops.py`, `addon_data.py`, `file_panel.py`) utilisent le paramètre `type` de `UILayout.separator()`, ajouté en 4.2 ([release notes](https://developer.blender.org/docs/release_notes/4.2/user_interface/), [PR #117310](https://projects.blender.org/blender/blender/pulls/117310)) — une vraie install 4.1 lève une `TypeError` dès le premier panneau qui en dessine un. Le paramètre `confirm_text` de `invoke_props_dialog` (ajouté en 4.1, [PR #117528](https://projects.blender.org/blender/blender/pulls/117528)) est une seconde dépendance déjà couverte par le plancher 4.2, pas celle qui contraint. Testé activement en 5.2 — pas vérifié sur une vraie install 4.2–5.1.

Réglages disponibles dans `Preferences > Add-ons > Minimalist Pipeline` :

| Réglage | Effet |
|---|---|
| **User name** | Nom utilisé dans les logs et les métadonnées (sinon fallback sur le login OS). |
| **Silent auto-increment** | À la première ouverture du fichier dans la journée (déjà sur la dernière version), incrémente en silence au lieu de demander confirmation. |
| **Auto-launch worker** | Ce poste devient automatiquement worker de rendu quand un projet devient actif (au démarrage de Blender ou en changeant de projet). |
| **Always open read-only** | Force tous les fichiers du projet en lecture seule à l'ouverture, quel que soit leur état de verrou. Utile sur un poste de review/playblast. |
| **Experience level** | En *Beginner*, de courtes explications des concepts du pipeline (versions, stable, links...) s'affichent près des boutons et popups concernés ; *Advanced* les masque. Le premier lancement affiche aussi un popup de bienvenue une fois, réouvrable à tout moment depuis le "?" du panneau principal. |

Session, verrouillage, check des libs périmées et gating read-only tournent toujours dès qu'un projet est actif — pas de toggle pour tout mettre en pause d'un coup. *Silent auto-increment* ne contrôle que le silence (ou pas) de la proposition de version à la première ouverture du jour.

---

## Concepts

Vue d'ensemble ci-dessous — chaque entrée pointe vers une page dédiée avec l'explication complète, les cas limites, et le schéma JSON derrière.

- **[Le projet, nommage, création en masse](docs/project-and-naming_fr.md)** — un projet est un dossier avec `config/project_config.json` ; le préfixe du fichier le route automatiquement vers le bon dossier. Le nommage suit `{prefix}_{name}_v{number}[-{tag}]`, reconstruit depuis la config, jamais tapé à la main. Les assets/shots peuvent aussi être créés en masse depuis un CSV.
- **[Blocs de shots (multishot)](docs/multishot_fr.md)** — un seul fichier pour des cuts caméra sur une animation continue qu'on ne peut pas séparer sans casser les raccords. Se découpe automatiquement en un job de rendu par shot.
- **[Versions : wip et stable](docs/versions_fr.md)** — publier = tagger `-stable`, pas écraser un fichier. Auto-incrément à l'ouverture et garde à la sauvegarde évitent d'écraser une version stable par erreur.
- **[Sessions et verrouillage](docs/sessions-and-locking_fr.md)** — qui a quoi d'ouvert, en ce moment ; des verrous qui expirent d'eux-mêmes plutôt que de nécessiter un serveur central arbitre.
- **[Suivi & revues](docs/tracking-and-reviews_fr.md)** — notes/todos/rtk par asset/shot, validation par département, deux popups de monitoring project-wide.
- **[Link vs Append](docs/linking_fr.md)** — link est le mode natif du pipeline ; un append est détecté et une action de nettoyage est proposée.
- **[Rendu (farm)](docs/farm_fr.md)** — un monitor + un nombre quelconque de workers coordonnent les jobs de rendu sur le drive partagé du projet, sans SSH ni serveur.

---

## Interface

Tous les panneaux vivent dans la sidebar de la vue 3D (`N` > onglet **Pipeline**) — Project, Asset, Shot, Tracking, Farm — plus un popup de monitoring project-wide, un dashboard farm, et un menu "Pipeline" dans la barre du haut pour un accès rapide sans ouvrir la sidebar. Référence complète panneau par panneau : **[docs/interface_fr.md](docs/interface_fr.md)**.

---

## Choix de conception

Plusieurs choix délibérés structurent tout l'addon — tout en JSON plutôt qu'une base de données, un seul fichier par asset plutôt qu'un par département, coordination push-pull sur le drive partagé plutôt que du SSH, la durée de travail loggée mais jamais affichée par personne, et d'autres dans le même esprit. Le raisonnement derrière chacun : **[docs/design_fr.md](docs/design_fr.md)**.

---

## Limites connues actuelles

- Seul Ctrl+S est gardé, pas le bouton Save du menu File ni l'icône save de la barre du haut — ceux-ci contournent complètement la vérification lecture-seule/stable. Un avertissement "READ-ONLY" dans la barre du haut atténue ça (visible, ne bloque pas).
- Un NAS/lecteur qui se déconnecte *pendant que Blender tourne déjà* n'est pas entièrement géré — seul le check au démarrage l'est.
- Preview et Branch block du multishot ne sont pas encore éprouvés dans un vrai passage create → render → preview → branch.
- La casting JSON par shot (roadmap) n'est pas encore implémentée.

Liste complète avec détails : **[docs/limitations_fr.md](docs/limitations_fr.md)**.

---

## Documentation

| | |
|---|---|
| **[docs/](docs/README.md)** | Une page par thème ci-dessus, en plus détaillé, avec des liens croisés. À consulter pour tout ce qui dépasse la vue d'ensemble rapide. |
| **[CODE.md](CODE.md)** | Référence dev : architecture des modules (`lib/`, `farm/`, `operators/`, `panels/`), patterns de code, roadmap v0.2–v0.4+. |
| **[graph.md](graph.md)** | Diagramme exhaustif de chaque handler/timer/opérateur : qui déclenche quoi, dans quel ordre, avec quelles conditions. |
| **[NOTES.md](NOTES.md)** | Notes de conception dev, feature par feature — le *pourquoi*, les alternatives rejetées, et l'historique d'archi qu'un commentaire de code est trop court pour porter. Couvre le multishot pour l'instant ; d'autres sections viendront s'y ajouter. |
