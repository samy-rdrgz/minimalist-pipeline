# Prise en main

*[← Index de la documentation](README.md) · [English version](getting-started.md)*

---

Cette page n'est volontairement pas une référence de concepts — c'est ce qu'on clique concrètement, dans l'ordre, la première fois. Chaque étape pointe vers la page de concept qui couvre le raisonnement et les cas limites.

## 1. Créer un projet

Menu de la barre du haut (ou panneau Project) → **New project**. Choisir un dossier, donner un nom, et le wizard construit la structure de dossiers pour vous (`assets/`, `shots/`, `library/`, `renders/`...) — rien à monter à la main. Structure complète : [Structure de projet, nommage, création en masse](project-and-naming_fr.md).

## 2. Créer son premier asset ou shot

**New asset** / **New shot**, taper un nom — c'est tout. L'addon construit le bon nom de fichier (`ch_bob_v001.blend`, `sq010_sh010_v001.blend`...) et crée son dossier de suivi juste à côté. On ne tape jamais un numéro de version ou un padding à la main. Plusieurs à créer d'un coup ? **Batch create from CSV** fait la même chose depuis une feuille de calcul.

## 3. Travailler, sauvegarder, laisser l'addon gérer les versions

Ctrl+S comme d'habitude. La plupart du temps, rien de visible ne se passe — l'addon note discrètement ce qui a été touché. À la première ouverture du fichier dans la journée, il fait automatiquement passer à une nouvelle version en coulisses, pour ne jamais retoucher le fichier d'hier par erreur.

Le seul moment où une popup apparaît, c'est quand une vraie décision demande un humain — par exemple sauvegarder par-dessus une version déjà marquée `-stable`. La lire, choisir une option, continuer à travailler. [Versions : wip et stable](versions_fr.md) détaille exactement quand et pourquoi ça arrive.

## 4. Marquer quelque chose comme terminé : `-stable`

Quand un asset ou un shot est dans un état sur lequel les autres peuvent s'appuyer, utiliser **Mark as stable** plutôt que simplement incrémenter. C'est ce qu'un link ailleurs dans le projet va réellement pointer — une simple version de travail n'est jamais référencée d'un fichier à l'autre.

## 5. Laisser des notes, des todos, des retours à corriger

Le panneau **Tracking** sur n'importe quel fichier permet de noter une remarque, ajouter un todo, ou signaler quelque chose à corriger — pas de feuille de calcul, pas d'outil de revue séparé. Voir [Suivi & revues](tracking-and-reviews_fr.md).

## 6. Rendre

Cliquer **Render** sur n'importe quel fichier, choisir une plage de frames (ou garder les valeurs par défaut), et soumettre. N'importe quel poste avec le projet ouvert et Blender lancé peut prendre le job — suivre la progression depuis le dashboard farm. Rien à installer à part Blender. Voir [Rendu (farm)](farm_fr.md).

## Travailler avec quelqu'un d'autre

Rien à configurer. Si un collègue a déjà un fichier ouvert, une notice claire apparaît et le fichier s'ouvre en lecture seule au lieu d'entrer en conflit silencieusement — même dossier partagé, pas de serveur, pas de réglage. Détails : [Sessions et verrouillage](sessions-and-locking_fr.md).

---

Une fois que ça devient naturel, l'[index de la documentation](README.md) couvre le raisonnement, les cas limites, et le JSON exact derrière chacune de ces étapes.
