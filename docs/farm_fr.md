# Rendu (farm)

*[← Index de la documentation](README.md) · [English version](farm.md)*

---

Deux rôles, indépendants du fait d'avoir un fichier ouvert ou non :

- **Monitor** : un seul par projet à la fois (`config/.farm/monitor.lock`). Fait tourner la queue — reçoit les demandes de rendu, avance chaque job à travers ses étapes, dispatch vers les workers disponibles.
- **Worker** : n'importe quel poste avec Blender + l'addon ouverts. S'enregistre, envoie un heartbeat, exécute les rendus qui lui sont assignés en subprocess Blender headless.

Un job traverse : `queued → setup → render → checks_images (contrôle ffmpeg) → compilation (assemblage vidéo ffmpeg) → finished/failed → archived`. Chaque étape a son échec dédié (`*_failed`), jamais bloquant pour les autres jobs de la queue. Le lancement du monitor vérifie en amont la présence de `ffmpeg` (sur le PATH de la machine, ou via le chemin explicite réglé dans Préférences → FFmpeg path, pour un lancement de Blender qui ne voit pas correctement son PATH — un runtime sandboxé comme celui de Steam, par exemple) et avertit (Cancel / Continue anyway) s'il est absent — sinon cet échec ne se serait révélé que plus tard, silencieusement, job par job.

Soumission (panel "Render", ou bouton par fichier) : priorité, mode de rendu, incrément (nouveau dossier de sortie systématique ou réutilisation), plage de frames avec override relatif (`s+10`, `e-5`...), machines ciblées (vide = auto), preset de script pré-rendu.

**Modes de rendu** :
- `single` : une seule machine sur toute la plage.
- `placeholder` : toutes les machines libres attaquent la même plage en parallèle, sans découpage explicite — elles s'auto-arbitrent via les réglages natifs Blender `use_placeholder` + `use_overwrite=False` (chaque frame déjà réclamée/rendue est sautée par les autres). Rapide, mais une frame corrompue par une course entre deux machines reste possible sur un drive lent.
- `auto` : comme `placeholder`, sauf si le dernier rendu placeholder de ce fichier a laissé des frames corrompues (mémorisé dans `.pipeline/render_history.json` à côté du fichier) — dans ce cas, bascule automatiquement en `single` pour ce job.

Un bloc de shots (multishot, voir [Blocs de shots (multishot)](multishot_fr.md)) se soumet et se comporte exactement comme n'importe quel fichier de ce côté-là — le découpage en un job par shot se fait automatiquement une fois le fichier pris en charge, pas quelque chose à faire différemment à la soumission.

Toute la farm se coordonne sur le drive partagé du projet, sans SSH ni connexion directe entre machines — voir [Choix de conception](design_fr.md#pas-de-ssh-coordination-push-pull-sur-le-drive-partagé) pour le mécanisme push-pull et ses compromis.

---

**Voir aussi** : [Interface](interface_fr.md#popups-de-vue-densemble) pour le dashboard Jobs/Workers · [Sessions et verrouillage](sessions-and-locking_fr.md) pour le pattern heartbeat/expiration que suivent aussi les workers et le monitor.
