---
name: live-session
description: Fait jouer une session de cash game NLHE simulée, main par main, avec coaching en temps réel s'appuyant sur `pc brief`. Trois modes de démarrage (personnalisé, semi-personnalisé/aléatoire, rapide via format par défaut). À utiliser dès que l'utilisateur veut "jouer une session", "s'entraîner", ou n'a pas de main réelle à faire analyser et veut pratiquer.
---

# Live Session

## v2 : le contrat de rendu et de showdown descend dans le code

En v1, plus de la moitié de ce fichier (18,5 ko) était la spécification du rendu ASCII de la table. Elle est maintenant l'implémentation de `pokercoach/render.py` (docstring + `pc render --help`) — **les règles d'alignement, d'unité de stack, de placement identité/action ne sont plus à réciter ici, elles sont appliquées automatiquement**. Idem pour la résolution de showdown (`pokercoach/showdown.py` / `pc showdown`). Ce fichier garde uniquement les décisions produit : quand appeler quoi, et les règles qui ne sont pas mécanisables.

Les transitions de rue et le passage à la main suivante (rotation du bouton, persistance des archétypes) sont eux aussi mécanisés — voir "Transitions de rue et main suivante" ci-dessous. Ce sont volontairement des scripts **de cette skill**, pas du moteur `pokercoach` : `pc` reste unitaire et standalone (un `hand.json`, une seule main, aucune notion de session) pour rester utilisable ailleurs (`hand-review`, par exemple) sans rien connaître de `live-session`.

⚠️ Ces règles de rendu sont le fruit de corrections successives en session v1 (alignement cassé, blinds disparues du pot, joueurs foldés omis, timer qui cassait les colonnes) et ont été préservées à l'identique dans `render.py` — ne pas les réinventer si un problème de rendu apparaît, lire le docstring du module d'abord.

## Contexte utilisateur fixe

- Format réel joué : cash game **online**, jamais multi-table (une seule table à la fois).
- Tournois occasionnels — hors scope prioritaire.
- Niveau : concepts GTO connus "de loin" → toujours expliquer avec le jargon standard (`pc glossary`), jamais de terme non défini au premier usage.
- Leak documenté : s'acharner à bluffer jusqu'à la river en se sentant "commité", notamment face aux loose-passifs — traité structurellement par la gate G4 (`bluff_multi_street_blocked`), voir `exploit-coach`.

## Notation standard des profils adversaires (HUD-style), archétypes, pondération de population

Inchangé de la v1 — voir `data/multiway-adjustment.yaml` (`random_archetype_weights`, `archetype_baselines`) pour les tables, et `exploit-coach` pour la doctrine par archétype. Format : `(VPIP/PFR/3Bet%/AF)`. Une table complète se décrit :

```
Table: 6-max, 100bb effectif
UTG: TAG (22/18/7/3.2)
MP: Nit (14/10/3/1.5)
CO: LAG (30/25/11/4.5)
BTN: Fish (48/6/2/0.8)
SB: Random
Hero: BB
```

Les stats précises de chaque tirage `Random` doivent varier légèrement autour des repères (± quelques points), pas être répétées à l'identique.

## Persistance des identités adverses sur toute la session — décision produit, préservée

**Les profils adverses sont tirés UNE SEULE FOIS au début d'une session, jamais retirés à chaque main.** Un adversaire garde son archétype sur toutes les mains — seule sa position tourne. C'est exactement ce que le schéma `hand.json` encode structurellement : `seats[].archetype` est attaché au **siège physique** (stable), jamais à la position (dérivée de `button_seat`, qui tourne). `scripts/new_hand.py` (voir plus bas) applique cette règle automatiquement à chaque passage de main — ne pas la reconstituer à la main.

## Bust du Héros = fin de session

**Si le stack du Héros tombe à 0, la session s'arrête là — ne jamais recharger silencieusement.** `scripts/new_hand.py` **refuse** de produire une main suivante si le nouveau stack du Héros serait ≤ 0 (erreur explicite) — c'est la garantie mécanique de cette règle, pas seulement une consigne à suivre. Une nouvelle session complète (nouveaux profils tirés, nouvelle liste physique de sièges) redémarre depuis le mode 1/2/3 au choix de l'utilisateur, sauf demande explicite de recharge sur la table actuelle.

## Mode 1 — Session personnalisée

L'utilisateur donne le setup complet (sièges, stack depth, profil par siège, position du Héros). Un profil donné en prose est traduit dans la notation HUD et confirmé avant de démarrer.

## Mode 2 — Session semi-personnalisée

Une partie des paramètres est fixée, le reste en `Random` — tirer selon la pondération de `data/multiway-adjustment.yaml` et annoncer avant de démarrer.

## Mode 3 — Session rapide (format par défaut)

6-max, profils tirés aléatoirement selon la pondération réaliste, disposés aléatoirement. Stack depth par défaut 100bb sauf précision contraire. Annoncer ce format en une ligne avant de démarrer ; redéfinissable à tout moment en conversation.

## Rendu visuel de la table

À chaque **changement de rue** (pas à chaque action individuelle) :

```bash
pc render --hand hand.json
```

Génère automatiquement le rendu ASCII conforme aux règles v1 préservées dans `render.py` : unité `𝄫`, rectangle invariant, identité/stack dehors, action/montant dedans, fold affiche quand même le montant engagé, pas de `"..."`, board+pot toujours centrés et incluant toutes les mises de la rue en cours, terminologie stricte bet (première mise, jamais preflop) vs raise.

**Récapitulatif de transition entre rues (activé par défaut)** : à chaque changement de rue, deux rendus successifs — le rendu final de la rue qui vient de se terminer (titre `── <RUE> (résumé) ──`), puis le rendu de la nouvelle rue. S'applique aussi quand un all-in est callé : montrer le call comme une action à part entière avant d'enchaîner sur le(s) runout(s). Désactivable sur demande explicite de l'utilisateur (alors un seul rendu par rue).

Ne pas régénérer après chaque action isolée — accumuler les actions de la rue, afficher juste avant la décision du Héros.

## Timing des adversaires (tell principal en ligne — en prose, pas dans le rendu)

Décrire le temps de décision dans le récit qui accompagne le rendu, **seulement quand il sort de l'ordinaire** :
- **Snap/quasi-snap** : action automatique (attention, peut aussi être un piège chez un reg).
- **Tank léger** : rien d'alarmant en soi.
- **Tank lourd** : souvent une main proche de la limite de sa range, plus fréquent chez Fish/Nit que chez les regs (qui varient parfois exprès leur timing).
Ne pas sur-interpréter systématiquement — indice probabiliste, pas certitude.

## Transitions de rue et main suivante

```bash
python3 skills/live-session/scripts/advance_street.py --hand hand.json --deal "5♦"
python3 skills/live-session/scripts/new_hand.py --hand hand.json --winner 1
python3 skills/live-session/scripts/new_hand.py --hand hand.json --split 0,1   # égalité au showdown
```

`advance_street.py` : ouvre la rue suivante (preflop→flop attend 3 cartes, flop→turn et turn→river en attendent 1). Refuse si l'action de la rue courante n'est pas close (il manque une décision), si le nombre de cartes ne correspond pas, si une carte est déjà connue dans la main, ou si on est déjà à la river. Réécrit `hand.json` en place et pointe `to_act` sur le bon siège (ordre postflop : la SB en premier, le Bouton en dernier).

`new_hand.py` : fait tourner le bouton d'un cran, reconduit stacks/archétypes par siège physique, poste les blindes, réinitialise la main (cartes/rues vides). `--winner SEAT` pour un pot non partagé, `--split SEAT1,SEAT2,...` pour une égalité (partage égal). **Ne gère pas les side pots multiway** (simplification connue) ni le rétrécissement de table (un bust qui change le nombre de joueurs actifs, avec les règles de "dead button" que ça implique) — refuse plutôt que produire un état incorrect ; ajuster `hand.json` à la main dans ces cas-là.

Ces deux scripts sont volontairement hors du moteur `pokercoach` (voir la note en tête de fichier) : à consulter à chaque changement de rue et à chaque fin de main, plutôt que d'éditer `hand.json` directement.

## Résolution des showdowns — obligatoire, jamais à l'œil

```bash
pc showdown --board "<5 cartes séparées par des virgules>" --hand "Hero:<2 cartes>" --hand "<Position>:<2 cartes>"
```

Aucune exception, même quand le résultat semble évident — une erreur d'évaluation manuelle casse la confiance dans l'outil entier, un calcul déterministe ne se trompe jamais sur ce point.

## Déroulé d'une main

1. Annoncer le setup (table, stacks, profils) une seule fois en début de session. **Si plusieurs sièges partagent un archétype marqué** (plusieurs Fish/calling stations), le signaler et appliquer par défaut la doctrine `exploit-coach` correspondante sur toute la session sans attendre la demande.
2. Distribuer les cartes du Héros. Pour chaque rue : dérouler les actions adverses (avec timing si notable), `pc apply` pour chaque action (héros compris), `pc render` avant la décision du Héros. Une fois l'action d'une rue close, `scripts/advance_street.py` ouvre la suivante (distribuer les cartes cohérentes avec le deck restant) avant de reprendre les actions.
3. **Avant chaque décision du Héros** : poser la question ouverte ("qu'est-ce que tu fais ?") plutôt que de suggérer une action.
4. **Si le Héros fold** : la main ne s'arrête pas là. Continuer à simuler les joueurs restants (cohérents avec leur profil HUD) jusqu'à un seul joueur restant ou un showdown. Résumer ensuite brièvement qui remporte le pot, et afficher toute main montrée (`cards` dans `pc render`, plausible chez un Maniac) — objectif : permettre à l'utilisateur de confirmer sa lecture du profil après coup.
5. **Après chaque décision du Héros qui dépasse une ligne** : `pc brief --hand hand.json [--villain-archetype X]`, un seul appel. Verbosité pilotée par le `gate` retourné (voir `docs/brief/references/02-architecture-v2.md`) — ne pas produire une analyse en 6 points sur une décision déjà tranchée en G0-G2.

   **Signal d'alerte ponctuel (à utiliser avec retenue)** : si l'utilisateur justifie de continuer une ligne agressive déjà engagée en s'appuyant sur un seuil de rentabilité bas comme raison principale, le signaler **une fois**, brièvement, avant qu'il n'exécute la décision coûteuse — pas répété dans la même main. L'utilisateur peut jouer des lignes non conservatrices pour le plaisir : ce n'est pas un blocage, un point nommé une fois au bon moment.

   Les folds hors-coup sont déjà visibles dans le rendu ASCII — ne pas les commenter systématiquement, sauf s'ils sont vraiment surprenants par rapport au profil (un Nit qui 3bet, pas un Fish qui fold une main faible), et rester bref même alors.
6. **La main terminée** (pot remporté sans confrontation, ou showdown résolu) : `scripts/new_hand.py --winner SEAT` (ou `--split ...` en cas d'égalité) prépare la main suivante — bouton tourné, archétypes reconduits, blindes postées. S'il refuse (Héros bust, ou table rétrécie par un bust adverse hors scope du script), le signaler à l'utilisateur plutôt que de contourner. Sinon, retour à l'étape 2 pour la main suivante.
7. En fin de session (sur demande ou après un nombre de mains convenu) : résumé des leaks/patterns observés, agrégé, pas main par main.

## Ce que cette skill NE couvre PAS

L'analyse d'une main déjà jouée en réel → `hand-review`. La stratégie de tournoi/ICM → hors scope tant que les tournois restent occasionnels.
