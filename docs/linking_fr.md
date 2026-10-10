# Link vs Append

*[← Index de la documentation](README.md) · [English version](linking.md)*

---

Link est le mode natif du pipeline (le rig link le model, le shot link les assets — pas de copie de données). Après un import Blender (`File > Append` ou `Link`), l'addon détecte lequel a été fait et propose une action cohérente : nettoyer et re-linker un append, ou déplacer+relinker un link externe au projet. Un link normal *dans* le projet est juste discrètement noté dans le `.wipmeta` de la version courante (voir [Versions : wip et stable](versions_fr.md)), aucune popup.

Les links qui ne sont jamais passés par un import — un fichier migré depuis l'extérieur du pipeline, une bibliothèque repointée à la main ou par un script — sont aussi pris en compte : à l'ouverture et à chaque sauvegarde, l'addon scanne les bibliothèques du fichier et ajoute ce qui manque au `.wipmeta`. Seul ce que le fichier utilise directement est noté, comme pour un link manuel : linker une collection donne une seule entrée, pas une par objet, matériau ou armature qu'elle contient. Les assets contenus dans un autre fichier linké (un prop dans un décor linké) relèvent du suivi de ce fichier et sont ignorés, tout comme les fichiers internes de Blender et ceux hors du projet. Le scan ne fait qu'ajouter : un link supprimé est nettoyé comme d'habitude, pas par le scan. Un fichier `-stable` n'a pas de `.wipmeta`, donc rien n'y est scanné.

À l'ouverture d'un fichier, l'addon compare aussi chaque bibliothèque liée à la dernière version `-stable` disponible dans son dossier, et propose une mise à jour groupée si une plus récente existe.

---

**Voir aussi** : [Versions : wip et stable](versions_fr.md) — un link pointe toujours vers une version stable précise, jamais un "dernier" flottant. · [Interface](interface_fr.md) — c'est dans le popup "Links to" / "Linked by" du monitoring projet que ces links sont réellement visibles, fichier par fichier.
