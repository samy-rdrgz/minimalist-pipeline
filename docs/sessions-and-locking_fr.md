# Sessions et verrouillage

*[← Index de la documentation](README.md) · [English version](sessions-and-locking.md)*

---

À l'ouverture d'un fichier du projet actif (hors mode background), l'addon :
1. Écrit `config/.sessions/.session_{pid}.json` — qui a quel fichier ouvert, depuis quand, dernier ping.
2. Tente un verrou sur le `.blend` lui-même (`.{nom}.blend.lock`) ; s'il est déjà pris, le fichier s'ouvre en lecture seule avec une popup indiquant qui le détient.

Tant que le fichier reste ouvert normalement (pas en lecture seule), le heartbeat toutes les 30s rafraîchit à la fois la session et ce verrou — il ne va donc pas expirer tant que la session est active. La péremption du verrou est vérifiée contre 90s (3× l'intervalle du heartbeat — une marge pour qu'un seul battement manqué/retardé ne fasse pas voler un verrou encore légitimement tenu). Le verrou n'est en revanche jamais libéré *explicitement* à la fermeture : il expire tout seul (90s sans heartbeat) si Blender crashe ou si l'addon est désactivé sans quitter Blender, ce qui reste la façon dont un lock abandonné se débloque de lui-même sans arbitre central à interroger. Le raisonnement général derrière cette approche par expiration (pas de serveur central) est dans [Choix de conception](design_fr.md).

Chaque fin de session est loggée dans son propre `config/logs/sessions_log.jsonl`, durée de travail incluse — séparé du log général pour rester simple à parser pour le suivi de temps. Pas de ligne de début de session séparée : tout ce qu'elle pourrait dire (qui, quel fichier, quand) se retrouve déjà dans la ligne de fin (son timestamp moins la durée), donc logger les deux serait deux lignes pour un seul fait. Changer de fichier, ou quitter Blender directement, ferme proprement la session du fichier précédent dans les deux cas. Voir [Choix de conception](design_fr.md) ("La durée de travail est loggée, jamais affichée par personne") pour ce à quoi ce log sert, et ne sert pas.

Les départements travaillés ne sont plus demandés via une popup à la fermeture/au quit — un dialogue modal posé aussi tard n'est pas garanti de s'afficher (Blender démonte déjà sa window manager au moment où `exit_pre` se déclenche). À la place, le panneau asset/shot affiche un bouton bascule par département requis directement sur le fichier, modifiable à tout moment pendant la session ; chaque clic écrit immédiatement dans le `.wipmeta` de cette version (voir [Versions : wip et stable](versions_fr.md)). Rien n'est présumé travaillé par défaut — un fichier non touché n'enregistre simplement rien.

---

**Voir aussi** : [Versions : wip et stable](versions_fr.md) pour comment les toggles "travaillé cette session" alimentent la popup increment/mark-stable · [Rendu (farm)](farm_fr.md) pour les heartbeats worker/monitor, qui suivent la même logique d'expiration.
