# Rendu (farm)

*[← Index de la documentation](README.md) · [English version](farm.md)*

---

Deux rôles, indépendants du fait d'avoir un fichier ouvert ou non :

- **Monitor** : un seul par projet à la fois (`config/.farm/monitor.lock`). Fait tourner la queue — reçoit les demandes de rendu, avance chaque job à travers ses étapes, dispatch vers les workers disponibles.
- **Worker** : n'importe quel poste avec Blender + l'addon ouverts. S'enregistre, envoie un heartbeat, exécute les rendus qui lui sont assignés en subprocess Blender headless.

Un job traverse : `queued → setup → render → checks_images (contrôle ffmpeg) → compilation (assemblage vidéo ffmpeg) → finished/failed → archived`. Chaque étape a son échec dédié (`*_failed`), jamais bloquant pour les autres jobs de la queue. Le lancement du monitor vérifie en amont la présence de `ffmpeg` (sur le PATH de la machine, ou via le chemin explicite réglé dans Préférences → FFmpeg path, pour un lancement de Blender qui ne voit pas correctement son PATH — un runtime sandboxé comme celui de Steam, par exemple) et avertit (Cancel / Continue anyway) s'il est absent — sinon cet échec ne se serait révélé que plus tard, silencieusement, job par job.

Soumission (panel "Render", ou bouton par fichier) : priorité (la plus haute passe en premier, 10 par défaut ; à priorité égale : le plus ancien d'abord), mode de rendu, incrément (nouveau dossier de sortie systématique ou réutilisation), plage de frames avec override relatif (`s+10`, `e-5`...), machines ciblées (vide = auto), preset de script pré-rendu.

**Presets pré-rendu** : tout fichier `.py` ou `.json` déposé dans `config/presets/` (sauf `asset_file_preset.py`) apparaît dans la liste des presets à la soumission, et chaque worker l'applique juste avant de rendre -- par-dessus les réglages du fichier, sans jamais les sauvegarder dedans. Un `.py` définit `override(scene, job_data)` (`job_data` est le JSON du job, à lire seulement) ; un `.json` est une simple liste de chemins à points depuis la scène :

```python
def override(scene, job_data):
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 64
    scene.render.resolution_percentage = 50
```

```json
{"render.engine": "CYCLES", "cycles.samples": 64, "render.resolution_x": 1280, "render.resolution_y": 720}
```

Un preset qui ne peut pas être appliqué **fait échouer le rendu de cette machine** au lieu de rendre avec les réglages du fichier (burn-in, pleine résolution...) : un `.py` qui plante, un preset qui n'existe plus, un `.json` illisible -- loggé comme erreur farm, le job continue avec ses autres machines ou échoue. Seule une clé `.json` invalide est simplement ignorée (les autres s'appliquent quand même). Chaque worker lit le job sans prendre son verrou : toutes les machines d'un job démarrent en même temps, et le verrou qu'elles se disputaient faisait rendre certaines sans le preset.

Le preset est aussi appliqué une fois au setup, dans cette session jetable (jamais sauvegardée non plus), pour lire ce que le rendu va vraiment produire : le format de sortie (ce que cherchent la vérification des frames et la compilation) et le fps (celui de l'encodage de la compilation) viennent du fichier *plus* son preset. Attention aux identifiants qui changent selon la version si les workers ne tournent pas tous sur la même : EEVEE s'appelle `BLENDER_EEVEE_NEXT` en 4.2–4.5 mais `BLENDER_EEVEE` à partir de 5.0 -- un preset `.py` peut choisir celui qui existe.

**Modes de rendu** :
- `single` : une seule machine sur toute la plage.
- `placeholder` : toutes les machines libres attaquent la même plage en parallèle, sans découpage explicite — elles s'auto-arbitrent via les réglages natifs Blender `use_placeholder` + `use_overwrite=False` (chaque frame déjà réclamée/rendue est sautée par les autres). Rapide, mais une frame corrompue par une course entre deux machines reste possible sur un drive lent.
- `auto` : comme `placeholder`, sauf si le dernier rendu placeholder de ce fichier a laissé des frames corrompues (mémorisé dans `.pipeline/render_history.json` à côté du fichier) — dans ce cas, bascule automatiquement en `single` pour ce job.

**Workers par job** (Edit project, 0 = pas de limite) : le nombre maximum de machines qu'un rendu `placeholder`/`auto` reçoit à la fois, workers qui rejoignent compris -- les machines restantes vont aux jobs suivants. Le placeholder de Blender n'est pas atomique sur un partage réseau : deux machines qui finissent une frame au même moment peuvent prendre toutes les deux la suivante et l'écrire ensemble (une frame lisible avec des blocs corrompus, que la vérification des frames ne voit pas). Moins de machines sur les mêmes frames, moins de cas.

**Les workers libres rejoignent d'abord les rendus en cours** : avant qu'un nouveau job soit envoyé, un worker libre (ou qui se libère) rejoint un rendu déjà en cours -- priorité la plus haute d'abord -- si ce rendu est en `placeholder` ou `auto` (pas `single`, ni un `auto` retombé en `single`), si le worker y est autorisé (aucune machine assignée, ou dans sa liste) et n'a jamais échoué dessus, et s'il reste plus de 10 frames que personne n'a commencées *par worker qui rejoint* (78 restantes : jusqu'à 7 ; 10 ou moins : aucun). Il reçoit la même demande de rendu, donc ne prend que les frames encore libres. Un nouveau job n'a que les workers restants. Tant que des jobs attendent leur setup, le worker du serveur farm (quand il est aussi le monitor) ne prend pas de nouveau rendu : le setup attend la fin du rendu de cette machine, ce qui bloquait toute la file pendant des heures.

Un bloc de shots (multishot, voir [Blocs de shots (multishot)](multishot_fr.md)) se soumet et se comporte exactement comme n'importe quel fichier de ce côté-là — le découpage en un job par shot se fait automatiquement une fois le fichier pris en charge, pas quelque chose à faire différemment à la soumission.

**Dossiers de sortie** : un plan se rend dans `renders/<seq>/<plan>/<version>_<n>/`, un fichier d'asset ou de library dans `renders/assets/<préfixe>/<asset>/<version>_<n>/` (ou `renders/library/...`).

**Vignette** : une fois un rendu compilé, la farm écrit une vignette à côté de ses dossiers — `renders/<seq>/<plan>/<seq>_<plan>_thumbnail.jpg`, `renders/assets/ch/ch_bob/ch_bob_thumbnail.jpg` (frame du milieu, 240 px sur son plus grand côté par défaut — "Thumbnails" dans Edit project), utilisée par le snapshot de prod. Faite par Blender lui-même ; seul un EXR multicouche demande ffmpeg.

**Après le rendu** : une fois un job terminé (frames vérifiées, vidéo compilée), son rendu apparaît dans la colonne "Farm" du Project monitoring (qui montre aussi le job de chaque fichier pendant qu'il attend ou rend) jusqu'à ce que quelqu'un le marque vérifié (bouton vidéo pour la lire, bouton coche pour la valider), ce qui archive aussi le job (il quitte la liste du Farm monitoring) -- voir [Suivi & revues](tracking-and-reviews_fr.md). Un job terminé (rendu, découpe d'un bloc, preview) quitte de lui-même la liste du Farm monitoring 24 h après sa fin (`"auto_archive_hours"`, 0 = jamais) ; un job en échec reste jusqu'à ce que quelqu'un l'archive.

**Logs** : chaque processus de la farm écrit sa sortie dans un fichier de `config/.farm/queue/requests/` -- `request_<job_id>.log` pour le setup, la vérification des frames, la compilation et la preview d'un job, plus un `request_<job_id>_<machine>.log` par rendu de worker. Supprimés quand le job se termine bien, conservés (et archivés avec le job) en cas d'échec : c'est le premier endroit où regarder. Un log conservé est réduit une fois son job terminé -- les lignes de progression de Blender par frame retirées sauf les dernières, puis seuls son début et sa fin gardés au-delà de 256 Ko (le log d'un rendu échoué atteignait 36 Mo) -- et les logs archivés sont supprimés après 14 jours (`"farm": {"archive_log_days": ...}` dans `project_config.json`, 0 = jamais).

**Re-soumettre un shot déjà dans la farm** : un job est identifié par fichier + preset + shot, donc une nouvelle demande pour un shot dont le job précédent est encore en cours (en file, en attente d'un worker, en rendu...) attend que ce job se termine, puis part toute seule. Farm monitoring l'affiche "waiting for this shot's job in progress (étape)" ; un clic ouvre le job qui la retient.

**Relancer** : un job en échec a un bouton retry (dans la liste du Farm monitoring et dans son détail). Il repart de l'étape qui a échoué -- même dossier de sortie, mêmes frames, même preset, pas de nouvelle version. Un rendu ne rend que les frames manquantes : les fichiers vides laissés par le rendu échoué sont d'abord supprimés -- et si toutes les frames sont déjà sur le disque (les autres machines les ont finies), le rendu est carrément sauté : direct à la vérification des frames et à la compilation, sans attendre de worker. Un retry de rendu évite aussi la ou les machines qui ont échoué : le job est réassigné aux autres workers (un job "auto" -- aucune machine assignée -- prend tous les autres workers connus ; un job avec des machines assignées garde le reste de sa liste), visible dans "Assigned to" / "Failed on" du détail du job. S'il n'y a aucun autre worker, il repart sur la même machine. Un job dont le `.blend` n'existe plus (remplacé par une version plus récente, déplacé) ne peut pas être relancé -- soumettre la version actuelle -- et échoue tout de suite au lieu d'être envoyé à tous les workers.

**Recompiler** : un job terminé a un bouton recompiler (liste et détail) qui recompile sa vidéo à partir des frames déjà sur le disque -- ffmpeg seulement, sur la machine du moniteur, ni rendu ni worker. Le rendu revient "à vérifier" une fois fini. Utile après avoir remplacé quelques frames à la main, ou changé le preset ffmpeg.

**Après un crash** : si le Blender qui fait tourner le moniteur de la farm ou un worker crashe, ses jobs sont repris au relancement -- une étape encore en cours est attendue, une étape interrompue est refaite, un rendu interrompu est renvoyé (les frames déjà rendues sont gardées, seules les manquantes sont rendues). Quand une machine sort d'un rendu (son Blender a planté, elle ne répond plus depuis 3 minutes, son worker a été arrêté, ou sa part a été annulée) pendant que d'autres rendent encore le job, le job continue simplement avec elles. Quand plus aucune machine ne le rend, il est jugé sur les frames réellement présentes : toutes là, il passe à la vérification des frames (avertissement dans le log si une machine est sortie) ; frames manquantes après un vrai échec de rendu, il échoue ; Cancel du job sur toutes les machines, il s'arrête (cancelled) ; sinon -- frames laissées par une machine arrêtée en route -- les fichiers vides des frames abandonnées en plein rendu sont supprimés (sans risque à ce moment-là : plus personne ne rend le job) et le job est renvoyé pour ce qui reste, jusqu'à 3 fois avant d'échouer. Une annulation ne compte jamais comme un échec de la machine.

**Arrêter un worker** : "Kill this worker" sur une machine en train de rendre demande quoi faire de son rendu : *Stop the render too* (interrompu tout de suite ; le job continue avec ses autres machines, ou est renvoyé pour les frames restantes -- jamais un échec) ou *Let it finish* (aucun nouveau rendu n'est pris ; le worker s'arrête une fois celui-ci fini et publié). Dans les deux cas la machine reste éligible pour ce job si elle est relancée plus tard. Quitter Blender, ou passer à un autre projet, pendant que son worker rend arrête aussi le rendu (*Stop the render too*) : le rendu survivait à Blender, considéré perdu alors qu'il écrivait encore ses frames. N'importe quelle machine peut aussi être arrêtée depuis une autre : le bouton pause sur sa ligne dans l'onglet Workers de Farm monitoring pose la même question (si elle rend) et prend effet au prochain tick de ce worker, environ 10 s ; la ligne affiche alors "stops after this render", puis "stopped".

Toute la farm se coordonne sur le drive partagé du projet, sans SSH ni connexion directe entre machines — voir [Choix de conception](design_fr.md#pas-de-ssh-coordination-push-pull-sur-le-drive-partagé) pour le mécanisme push-pull et ses compromis.

---

**Voir aussi** : [Interface](interface_fr.md#popups-de-vue-densemble) pour le dashboard Jobs/Workers · [Sessions et verrouillage](sessions-and-locking_fr.md) pour le pattern heartbeat/expiration que suivent aussi les workers et le monitor.
