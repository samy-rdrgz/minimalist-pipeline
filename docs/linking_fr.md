# Link vs Append

*[← Index de la documentation](README.md) · [English version](linking.md)*

---

Link est le mode natif du pipeline (le rig link le model, le shot link les assets — pas de copie de données). Après un import Blender (`File > Append` ou `Link`), l'addon détecte lequel a été fait et propose une action cohérente : nettoyer et re-linker un append, ou déplacer+relinker un link externe au projet. Un link normal *dans* le projet est juste discrètement noté dans le `.wipmeta` de la version courante (voir [Versions : wip et stable](versions_fr.md)), aucune popup.

À l'ouverture d'un fichier, l'addon compare aussi chaque bibliothèque liée à la dernière version `-stable` disponible dans son dossier, et propose une mise à jour groupée si une plus récente existe.

---

**Voir aussi** : [Versions : wip et stable](versions_fr.md) — un link pointe toujours vers une version stable précise, jamais un "dernier" flottant.
