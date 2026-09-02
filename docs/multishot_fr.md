# Blocs de shots (multishot)

*[← Index de la documentation](README.md) · [English version](multishot.md)*

---

Un **bloc** n'est pas "plusieurs shots dans un fichier" au sens générique — c'est spécifiquement pour des cuts caméra sur **une seule animation continue** qu'on ne peut pas fabriquer en fichiers séparés sans casser les raccords aux coutures : même décor, même lighting, un seul département/une seule personne dessus à la fois. Un vrai besoin, mais rare — l'addon ne le pousse jamais en avant dans l'UI, le mono-shot reste le défaut même en solo. Si deux cuts ont des besoins différents (fx sur l'un, lighting distinct sur l'autre), ce n'est pas un bloc, ce sont deux shots.

- **Créer un bloc** : même dialogue "New shot", mais on sélectionne plusieurs shots de la séquence courante au lieu d'un seul (jamais tapé à la main — le nom est généré depuis la sélection, donc le padding/l'ordre ne peuvent pas dériver). Résultat : un seul fichier, un seul nom : `sq040_sh030-040-045-050_v001.blend`.
- **Ce qui marque vraiment les coupes** : des caméras et des markers de timeline dans le fichier, nommés d'après leur propre shot (`cam_sq040_sh045`). Le nom du fichier est un *plan* (les shots que ce bloc est censé couvrir) ; les markers sont l'*état réel* — ils peuvent diverger pendant que le travail est en cours, c'est normal. Ça n'est réconcilié que quand ça compte, au moment du rendu (voir plus bas), et jamais en silence : un marker qui ne correspond à aucun shot du nom est simplement absorbé par le précédent plutôt que d'être perdu.
- **Rendu** : on soumet le bloc une fois, même bouton "Render" que n'importe quel fichier. La farm le découpe automatiquement en un job de rendu ordinaire par shot — chacun atterrit dans son propre dossier de sortie (`renders/sq040/sh045/...`), donc une note de review sur un seul shot veut dire re-rendre juste celui-là, pas tout le bloc. Une checklist permet de ne soumettre qu'une partie des shots du bloc si c'est tout ce qu'il faut. Mécanique complète dans [Rendu (farm)](farm_fr.md).
- **Preview** : "Preview block" / "Preview sequence" compilent le dernier rendu de chaque shot en une vidéo jetable (`renders/sq040/_preview/..._{date}.mp4`) — jamais autoritaire, jamais régénérée toute seule, toujours sur un clic manuel.
- **Changer quels shots sont regroupés** : "Branch block" — l'ancienne composition est marquée archivée (pas supprimée, pas déplacée — toujours là si besoin de vérifier) et un nouveau fichier prend le relai avec la nouvelle sélection de shots, en continuant la même lignée de versions et en reprenant ses notes/todos.
- Les notes/todos peuvent porter un numéro de shot optionnel, choisi dans une liste déroulante construite à partir des shots du bloc (`[sh045] le pied glisse`) — pas un filtre, juste une étiquette sur l'entrée. Voir [Suivi & revues](tracking-and-reviews_fr.md).

---

**Voir aussi** : [Convention de nommage](project-and-naming_fr.md#convention-de-nommage) pour la construction du nom d'un bloc · [Limites connues actuelles](limitations_fr.md) pour l'état actuel des tests de Preview/Branch et le risque théorique de longueur de chemin Windows sur les très longs blocs · [NOTES.md](../NOTES.md) (racine du repo, section "Multishot blocks") pour les notes de conception dev de cette feature.
