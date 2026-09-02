# Choix de conception

*[← Index de la documentation](README.md) · [English version](design.md)*

---

## Tout en JSON, rien en base de données

Aucun service à installer ni à maintenir. N'importe quel poste qui peut déjà ouvrir le projet (accès au dossier partagé) peut lire/écrire le pipeline sans configuration supplémentaire. Lisible et diffable sans l'addon — un `tracking.json` ou un `.wipmeta` a du sens ouvert dans un éditeur de texte. Les écritures passent par un verrou fichier (`acquire_lock`/`locked_json`) + écriture atomique (fichier temporaire puis `os.replace`), pour rester safe si deux postes écrivent au même moment sur le même NAS.

<br>

## Un seul fichier par asset, pas un par département

Une version antérieure découpait un asset en un fichier par département (modeling, rig, texture...), liés entre eux, avec des checksums (nombre de verts/faces/volume) pour détecter quand un fichier en aval devenait périmé en silence parce que ce dont il dépendait avait changé sous lui — le problème classique du "qui possède quoi, et est-ce que ça a changé" qu'un pipeline découpé par département doit résoudre lui-même. Ce modèle a été abandonné pour un seul fichier, une seule lignée de versions, par asset (voir [Structure de projet, nommage, création en masse](project-and-naming_fr.md)) : celui qui l'a ouvert possède l'ensemble pour cette session, et un link pointe toujours vers une version `-stable` précise, jamais une cible mouvante.

Les checksums sont partis avec, et pas comme une perte : avec un seul fichier et un seul propriétaire, il n'y a plus de second fichier avec lequel désynchroniser — la question à laquelle un checksum sert à répondre ("est-ce que ce dont je dépends a changé depuis la dernière fois") n'a plus d'objet à qui la poser. Retirer la condition qui créait un problème, plutôt qu'ajouter un mécanisme pour le détecter, c'est la forme que prennent la plupart des choix de cette page.

<br>

## Pas de SSH, coordination "push-pull" sur le drive partagé

La farm de rendu ne se connecte à aucune machine directement — pas de clés SSH, pas d'IP à connaître, pas de port à ouvrir. Toute la coordination passe par des fichiers JSON dans `config/.farm/`, sur le même partage réseau qui héberge déjà le projet :

- Le monitor **pousse** une demande de rendu dans `queue/requests/request_{job}_{uuid}.json`, ciblant l'uuid d'un worker précis.
- Chaque worker **tire** (poll son propre timer) les requêtes qui le ciblent et lance le rendu en local.

Conséquence directe : n'importe quel poste qui peut ouvrir le projet peut devenir worker ou monitor d'un clic, sans qu'un admin réseau touche à quoi que ce soit. Le prix à payer : c'est du polling (latence de l'ordre de la dizaine de secondes entre étapes), pas du temps réel — acceptable pour une équipe de 2-5, pas conçu pour scaler à une vraie farm de studio. Voir [Rendu (farm)](farm_fr.md) pour la mécanique que ça permet.

Le périmètre est aussi plus étroit que ce que "render farm" pourrait laisser penser, volontairement : chaque job, c'est une machine qui termine une frame complète toute seule — jamais plusieurs machines qui coopèrent sur la *même* frame (fusion de tuiles, split de passes GPU). C'est un problème plus simple que celui que résout un outil dédié de distribution de rendu multi-GPU, et c'est pour ça que le construire en interne valait le coup ici plutôt que d'en dépendre : pas de synchronisation au niveau de la frame, pas de fusion de résultats partiels, rien qui nécessite son propre protocole. Si ça grossit un jour au point de coûter plus cher à maintenir que ce que l'addon autour peut porter, l'extraire en extension séparée est la soupape prévue à l'avance — un choix pris en amont, pas subi après coup.

<br>

## Une table de chemins centrale, pas de chemins construits à la main

Chaque fichier et dossier d'un projet — le `.blend` d'un asset, son `tracking.json`, un dossier de sortie de rendu, un lock de session, une entrée de la queue farm — est résolu via une seule table de correspondance, jamais reconstruit à coups de concaténation de strings au fil du code. Combiné au fait que la regex de nommage est reconstruite depuis la config plutôt que figée en dur (voir [Structure de projet, nommage, création en masse](project-and-naming_fr.md)), la forme réelle du projet — noms de dossiers, préfixes, nombre de digits — est une donnée lue dans `project_config.json`, pas une logique éparpillée dans l'addon. Renommer un dossier ou changer un préfixe dans la config prend effet partout d'un coup ; rien à traquer et corriger à la main ailleurs.

<br>

## Un seul type d'erreur, et le code de fond ne lève jamais

Chaque échec dans la logique cœur du pipeline lève le même type d'erreur (un message + une sévérité), et chaque opérateur — un vrai clic sur un bouton ou un menu — l'attrape une fois, la logge, et la rapporte via la barre de statut de Blender ou une popup. C'est ce que "ne jamais agir en silence" (voir [Pour qui, pourquoi](../README_fr.md#pour-qui-pourquoi)) veut dire en code, pas juste dans les popups : c'est imposé à chaque point d'appel, pas laissé au hasard fonctionnalité par fonctionnalité.

La règle joue aussi dans l'autre sens. Le code qui tourne *sans* action utilisateur derrière lui — un handler d'ouverture de fichier, un timer en tâche de fond, le `draw()` d'un panneau — n'a aucun point d'attrape de ce genre : Blender ne lui donne aucun canal de retour, et une exception dans un callback de timer tue ce timer en silence, pour de bon, sans que rien ne signale qu'il s'est arrêté. Les fonctions atteignables depuis ces contextes sont écrites pour ne jamais lever : elles attrapent en interne, loggent, et retombent sur une valeur par défaut sûre plutôt que de faire remonter une erreur que personne ne verrait.

<br>

## Verrouillage par expiration, pas par serveur central

Locks de fichiers (JSON, sessions, monitor, `.blend` eux-mêmes) : un fichier `.lock` sibling avec un timestamp, considéré périmé après un délai fixe (`LOCK_STALE_SECONDS`). Pas d'arbitre central à interroger, pas de single point of failure — si un poste crashe en tenant un lock, il se libère tout seul après expiration au lieu de bloquer les autres indéfiniment. Les locks tenus longtemps (session, fichier `.blend` ouvert) sont rafraîchis périodiquement par le heartbeat pour ne pas expirer en cours d'usage légitime ; ceux qui ne le sont pas sont volontairement de très courte durée (le temps d'une écriture JSON). Voir [Sessions et verrouillage](sessions-and-locking_fr.md) pour l'application aux sessions de fichier.

<br>

## Un seul pattern d'interaction pour tout : `PipelineAction`

Toute détection (fichier daté, save sur un stable...) construit le même objet — titre, message, sévérité, liste de choix (label + callback, éventuellement un tooltip) — affiché par un unique opérateur popup. Pas de UI ad-hoc par fonctionnalité : ajouter une nouvelle détection ne demande pas de nouveau code d'affichage. Exception : les deux propositions déclenchées directement à l'ouverture du fichier (lecture seule, lib obsolète) utilisent le dialogue de confirmation natif de Blender à la place — la popup partagée ne se ferme de façon fiable que si elle est ouverte depuis un vrai opérateur (un bouton, un raccourci), pas depuis un handler.

Sortir d'une popup sans répondre n'est pas non plus une échappatoire silencieuse : la fermer sans cliquer un choix (Échap, clic à côté) déclenche quand même le nettoyage qu'un vrai choix aurait fait — relâcher un verrou pris pour la sauvegarde qui a déclenché la popup, par exemple — plutôt que de laisser quelque chose à moitié fait parce que l'artiste n'a pas explicitement cliqué "Cancel".

<br>

## La durée de travail est loggée, jamais affichée par personne

Chaque début/fin de session écrit sa durée dans `sessions_log.jsonl` (voir [Sessions et verrouillage](sessions-and-locking_fr.md)) — la donnée existe, en JSONL brut, par poste et par nom d'utilisateur. Rien dans l'addon ne la relit. Aucun panneau, aucun dashboard, aucun total par personne, nulle part.

C'est délibéré, pas inachevé. Le suivi de temps entre des gens qui se font confiance crée une dynamique de surveillance même sans que personne ne le demande et sans aucune hiérarchie derrière — la simple existence visible d'un "Alice : 24h32, Bob : 18h15" change la façon dont les gens travaillent, que quelqu'un le regarde vraiment sous cet angle ou non. La cible de l'addon (2-5 personnes, souvent des amis ou un petit studio) est exactement le contexte où ce coût est le plus élevé et le bénéfice le plus faible — personne ici n'a besoin d'un dashboard de coordinateur.

Il y a une seconde raison, indépendante de l'aspect social : la durée brute est solide (temps réel basé sur le heartbeat), mais l'attribuer à un *département* ne l'est pas — ça demanderait les toggles "travaillé cette session" (voir [Sessions et verrouillage](sessions-and-locking_fr.md)), qui sont auto-déclarés, optionnels, et triviaux à oublier de cocher en cours de session. Une répartition construite là-dessus n'inviterait pas seulement la dynamique décrite plus haut ; elle habillerait une donnée molle, auto-cochée, en chiffre par département soi-disant objectif que personne n'a vérifié.

Le log reste quand même, parce que logger ne coûte rien et ne ferme aucune porte : une future vue par personne, opt-in, reste possible sans rien changer à ce qui est déjà sur disque. Ce qui est exclu, c'est une répartition par défaut, toujours active, que personne n'a demandé à voir, apparaissant comme effet de bord le jour où quelqu'un ajoute un panneau qui lit ce fichier. Si ce panneau voit le jour un jour, ce doit être un choix explicite et opt-in — jamais un effet de bord de données déjà présentes.

Ce qui n'est pas exclu : un simple **total** par asset/shot — la somme des durées de toutes les sessions, tout le monde confondu, aucun nom accroché à quoi que ce soit dans le chiffre. Ça évite les deux objections d'un coup : personne n'est pointé du doigt (pas de dynamique de surveillance à créer), et rien n'est attribué à un département (pas de donnée auto-cochée qui prétend être précise) — c'est juste "ça a pris N heures, au total, sur toute son histoire", ce qui est réel, utile pour sanity-checker un scope, et déjà entièrement calculable depuis les entrées `session_end` (`filepath` + `duration_seconds`) regroupées par asset/shot. Pas encore fait, mais rien ci-dessus ne va contre.

<br>

## Solo-first, équipe-compatible

Tout fonctionne à un seul artiste sur un seul poste sans qu'aucune notion d'équipe n'entre en jeu — sessions, verrous et farm sont des couches qui s'activent d'elles-mêmes dès qu'un deuxième poste touche le même projet, jamais une case à cocher séparée à l'installation.

---

**Voir aussi** : [Sessions et verrouillage](sessions-and-locking_fr.md) · [Rendu (farm)](farm_fr.md) · [Structure de projet, nommage, création en masse](project-and-naming_fr.md) pour le JSON sur lequel tout ça repose.
