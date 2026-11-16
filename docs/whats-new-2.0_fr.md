# Quoi de neuf dans la 2.0

*[← Index de la documentation](README.md) · [English version](whats-new-2.0.md)*

Tout ce qui est arrivé depuis la 1.0.0, en résumé. Le détail, version par version, est dans le CHANGELOG.

---

## Avant de mettre à jour

- **Mettez à jour tous les PC en même temps.** La 2.0 écrit ses données autrement : une 1.x qui ouvrirait un projet passé en 2.0 se tromperait. La farm refuse d'elle-même une machine restée sur une autre version, avec un message clair.
- **Lancez *Migrate old data* une fois par projet** (Edit project > Maintenance). La fenêtre montre ce qui va changer avant d'écrire quoi que ce soit, et chaque fichier modifié est sauvegardé dans `backup/` à la racine du projet. Elle propose aussi de renommer les presets de rendu dont le nom ne dit pas à quel département ils servent.

---

## La page du projet, dans le navigateur

C'est le gros changement de la 2.0 : **le suivi du projet se fait dans une page web**, au lieu des fenêtres Project monitoring et Farm monitoring.

- ***Monitor in browser*** (panneau Project, menu Pipeline) : Blender sert la page du projet à votre navigateur, à jour en permanence. Ce que vous y faites (valider, poser un retake, écrire une note, répondre, attribuer, ajouter un shot) est enregistré dans le projet tout de suite, sous votre nom.
- **La liste des assets et des shots** : où en est chaque département, les retakes ouverts, les rendus à vérifier, ce qui tourne sur la farm. Filtres par département, retakes, notes ouvertes, « mon travail ». Un clic sur un fichier ouvre son panneau : ses notes, ses rendus à regarder (avec la frame affichée et les notes posées dessus), ses liens, et un bouton pour l'ouvrir dans Blender.
- **Breakdown** : l'avancement par séquence et par département, en %, en états, en nombre ou en retakes, avec le planning du projet.
- **Onglet Farm** : les rendus et les machines, envoyer un fichier en rendu, la priorité, annuler, relancer, archiver, savoir quelle machine a rendu quelle frame et combien de temps il reste.
- **Thème clair / sombre**, et la page s'adapte aux tablettes et aux téléphones.
- **Accès à distance, secondaire** : quelqu'un reçoit la même page par un QR code ou un lien, valable d'une heure à une semaine, sous son nom et son rôle ; rien ne s'ouvre sur votre machine, et vous coupez l'accès en un clic. Combiné avec un VPN (type Tailscale), cela permet d'avoir facilement un monitoring extérieur et distant du projet et de la farm.

## Les reviews

- **Le snapshot de prod** : une page HTML autonome du projet (vignettes, vidéos, notes, avancement), à envoyer à quelqu'un d'extérieur au studio. Elle s'ouvre sans Blender et sans réseau, même sur tablette.
- **Faire la review dans la page même**, live ou snapshot : ✓ / ✕ par département, retakes avec leurs frames, notes, réponses, « marquer corrigé ». Pour un snapshot, la review se télécharge en un fichier, et *Import review* l'applique au projet (plusieurs à la fois si besoin).
- **Done et validé** : l'équipe coche *Done* quand un département est fini ; des rôles de validation (sup, prod…) valident ensuite. Les notes et retakes d'un rôle sont marqués comme tels.
- **Changer les départements de plusieurs fichiers d'un coup** (tous les shots, une séquence, un préfixe, ceux qui ont déjà un département donné).

## L'équipe et le suivi

- **L'équipe** (Edit project > Team) : on choisit son nom dans la liste, on attribue un département à quelqu'un (aussi à la création ou par CSV), et le filtre « Moi » montre son travail. Rien ne mesure le temps de chacun, par principe.
- **On hold / Cancelled** : mettre un shot en pause ou l'abandonner, avec une raison, sans le supprimer.
- **Étapes** : un ordre entre départements (layout > anim > lighting) pour savoir ce qui attend quoi.
- **Planning** : début, fin, jours travaillés et jours off du projet, repris dans l'avancement.
- **Supprimer** un shot ou un asset proprement, et **Clean old renders** pour libérer de la place en gardant les rendus qui comptent.
- Les dates gardent leur fuseau horaire : quelqu'un qui travaille depuis ailleurs voit les bonnes heures.

## La farm

- **Plus fiable** : une machine qui tombe ne fait plus échouer le rendu, un rendu planté est relancé ailleurs, une frame bloquée est repérée, les mauvaises frames sont refaites, un crash de Blender ne laisse plus de jobs à relancer à la main.
- **Rendus découpés en paquets de frames**, partagés entre les machines libres, avec une priorité (la plus haute prend des machines à la plus basse) et un maximum de machines par job.
- **Rendus à vérifier** : chaque rendu fini attend qu'on le regarde. *Checked* peut valider des départements en même temps, et envoyer le rendu au montage.
- **Rendus par département** : le preset de rendu dit à quel département il sert (`animation_hd`, `lighting_hd`…), et chaque département a ses propres rendus à vérifier.
- **Previews de séquence** : les vidéos des shots mises bout à bout, compilées sur une machine libre.
- **Rushes pour le montage** : *Push rushes to editing* copie la dernière vidéo de chaque shot dans `editing/rushes/`, sous un nom fixe : le montage voit la nouvelle version sans rien relier.
- **Copie légère** de chaque vidéo pour le navigateur, et le H.265 lu aussi sur téléphone et tablette.
- Un worker empêche sa machine de se mettre en veille pendant un rendu, et se lance quelques secondes après Blender s'il est réglé pour.
- Rendre un asset ou un fichier de bibliothèque fonctionne aussi.

## Dans Blender

- **Ctrl+Alt+S** (Save Incremental) passe par l'incrément de l'addon dans un projet.
- Des menus clic droit, des raccourcis réglables dans les préférences, une aide « ? » à côté des champs des réglages du projet.
- Une fenêtre d'accueil pour démarrer, et le journal du pipeline dans sa propre fenêtre.
- Le panneau latéral ne rame plus sur un disque réseau.
- La création de shots en lot par CSV accepte les blocs multishot et les personnes attribuées.

## Retiré

- Les fenêtres **Project monitoring** et **Farm monitoring** : la page du projet les remplace. Le panneau latéral de Blender garde tout le reste.
- Le **tableur de review** (.xlsx) : la review se fait dans la page.
- Les presets de rendu en `.json` : seuls les presets Python restent (*Migrate old data* convertit les anciens).
