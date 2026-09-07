---
name: live-session
description: Fait jouer une session de cash game NLHE simulée, main par main, avec coaching en temps réel s'appuyant sur poker-rules, range-notation, equity-engine et gto-glossary. Trois modes de démarrage (personnalisé, semi-personnalisé/aléatoire, rapide via format par défaut). À utiliser dès que l'utilisateur veut "jouer une session", "s'entraîner", ou n'a pas de main réelle à faire analyser et veut pratiquer.
---

# Live Session

## Contexte utilisateur fixe

- Format réel joué : cash game **online**, jamais multi-table (une seule table à la fois)
- Tournois occasionnels — hors scope de cette skill v1 (cash game uniquement pour l'instant)
- Niveau : concepts GTO connus "de loin", aucun maîtrisé en profondeur → toujours expliquer via `gto-glossary`, jamais de jargon non défini au premier usage

## Notation standard des profils adversaires (HUD-style)

On réutilise le standard informel des HUD de tracking (PokerTracker/Hand2Note) : 4 stats clés entre parenthèses, dans cet ordre fixe :

```
(VPIP/PFR/3Bet%/AF)
```

- **VPIP** : % de mains jouées volontairement
- **PFR** : % de mains relancées preflop
- **3Bet%** : fréquence de 3bet preflop
- **AF (Aggression Factor)** : ratio (bets+raises)/calls postflop

Archétypes de référence (repères approximatifs, pas des bornes strictes) :

| Archétype | VPIP/PFR/3B/AF approx. |
|---|---|
| Nit (très serré-passif) | 12/9/2/1.5 |
| TAG (tight-aggressive, standard solide) | 20/17/7/3 |
| LAG (loose-aggressive) | 28/23/10/4 |
| Calling station / Fish (loose-passif) | 45/6/1/0.8 |
| Maniac (très loose-agressif, spew) | 55/40/15/6 |

Une table complète se décrit ainsi :

```
Table: 6-max, 100bb effectif
UTG: TAG (22/18/7/3.2)
MP: Nit (14/10/3/1.5)
CO: LAG (30/25/11/4.5)
BTN: Fish (48/6/2/0.8)
SB: Random
Hero: BB
```

## Pondération réaliste pour les profils "Random"

Quand un ou plusieurs sièges sont `Random` (mode 2 ou mode 3), tirer l'archétype selon cette distribution approximative de la population réelle en ligne (les regs solides sont minoritaires, les recreational/loose-passifs dominent) :

| Archétype | Poids |
|---|---|
| Fish / Calling station | 35% |
| TAG | 30% |
| LAG | 15% |
| Nit | 12% |
| Maniac | 8% |

Les stats précises (VPIP/PFR/3B/AF) de chaque tirage doivent varier légèrement autour des repères du tableau d'archétypes ci-dessus (± quelques points), pas être répétées à l'identique à chaque tirage — sinon les sessions se ressemblent trop.

## Persistance des identités adverses sur toute la session

**Les profils adverses sont tirés UNE SEULE FOIS au début d'une session, jamais retirés à chaque main.** Un adversaire donné garde son archétype (et ses stats HUD précises) sur toutes les mains de la session — seule sa position tourne, exactement comme le bouton tourne en vrai jeu.

Mécanique de rotation : maintenir une liste fixe de 6 sièges physiques (le Héros + 5 archétypes), établie à la première main de la session. À chaque nouvelle main, le bouton se décale d'un siège physique dans le sens du jeu (l'ordre `UTG→HJ→CO→BTN→SB→BB` s'applique à partir du nouveau siège BTN) — ce qui fait tourner les **labels de position** pour tout le monde, Héros compris, mais **l'archétype associé à chaque siège physique ne change jamais** au cours de la session.

Exemple : si à la main 1 la liste physique (dans l'ordre des positions de cette main) est `BTN=Héros, SB=Nit, BB=Maniac, UTG=LAG, HJ=Fish, CO=TAG`, alors à la main 2 le bouton passe au siège suivant (celui qui était SB) : `BTN=Nit, SB=Maniac, BB=LAG, UTG=Fish, HJ=TAG, CO=Héros`. Le Nit reste un Nit, juste à une autre position.

## Bust du Héros = fin de session

**Si le stack du Héros tombe à 0, la session s'arrête là — ne jamais simplement recharger son stack à 100𝄫 sur la même table.** Une nouvelle session complète (nouveaux profils tirés, nouvelle liste physique de sièges) doit être retirée depuis le début, exactement comme au lancement initial (mode 1/2/3 au choix de l'utilisateur), sauf si l'utilisateur demande explicitement une recharge sur la table actuelle.

## Mode 1 — Session personnalisée

L'utilisateur donne le setup complet dans la notation ci-dessus (nombre de sièges, stack depth, profil par siège, position du Héros). Si un profil est donné en prose ("un joueur assez loose mais pas fou"), le traduire d'abord dans la notation HUD ci-dessus et la lui montrer avant de démarrer, pour confirmer.

## Mode 2 — Session semi-personnalisée

L'utilisateur fixe une partie des paramètres (ex : "6-max, 100bb, un maniac au BTN") et laisse le reste en `Random`. Pour chaque siège `Random`, tirer un archétype au hasard parmi le tableau ci-dessus (pondérer vers TAG/LAG/Fish, le Nit et le Maniac sont plus rares en population réelle) et l'annoncer à l'utilisateur avant de démarrer la main.

## Mode 3 — Session rapide (format par défaut)

Format par défaut actuel (défini par l'utilisateur) : **6-max, profils tirés aléatoirement selon la pondération réaliste ci-dessus, disposés aléatoirement aux sièges**. Stack depth par défaut : 100bb sauf précision contraire.

- Annoncer ce format en une ligne avant de démarrer.
- Ce défaut peut être changé à tout moment en le redéfinissant explicitement en conversation — pas de procédure spéciale.

## Rendu visuel de la table

À chaque **changement de rue** (pas à chaque action individuelle), afficher la table via `scripts/render_table.py` (fonction `render_table`).

**Règles fixées (validées) :**
- Unité de stack : symbole `𝄫` (1 seul caractère, remplace "bb").
- **Le rectangle de la table est un invariant structurel** : les bordures (`╭╮╰╯│`) sont toujours à la même colonne, quelle que soit la longueur du contenu. Le script tronque/complète chaque cellule à largeur fixe automatiquement — ne jamais construire une ligne "à la main" en dehors de `render_table.py`, c'est précisément ce qui cassait l'alignement avant.
- Identité + stack de chaque joueur **en dehors** de la table, avec **un espace de respiration** avant le bord (pas totalement collé) — uniquement pour les positions verticales (BB/SB/HJ/CO). Les positions horizontales (UTG en haut, Héros en bas) restent centrées comme avant, rien à changer là.
- Décision (action **seule**, sans timer, et montant) **à l'intérieur** de la table, alignée du côté de son joueur. **Le timer ne s'affiche plus dans le dessin** — voir la section Timing ci-dessous, il se raconte en prose désormais.
- Positions "horizontales" (UTG en haut, BTN/Héros en bas) : ligne combinée centrée à l'intérieur `action · montant` ; identité+stack sur une seule ligne à l'extérieur.
- Positions "verticales" (BB/SB à gauche, HJ/CO à droite) : identité puis stack sur 2 lignes distinctes à l'extérieur ; action puis montant sur 2 lignes distinctes à l'intérieur, alignées côté joueur.
- **En cas de fold, afficher quand même le montant** : celui de la mise du tour précédent (ce que le joueur avait payé avant de se coucher), jamais une case vide pour le montant si de l'argent a été engagé.
- **Les blinds (SB/BB) sont un montant engagé dès le début de la main** : initialiser leur `amount` avec la blind postée (ex SB 0.5𝄫, BB 1𝄫) dès le premier rendu de la rue preflop, même avant qu'ils aient explicitement agi sur ce tour — sinon l'argent déjà dans le pot disparaît visuellement du dessin.
- Pas de `"..."` : un joueur qui n'a pas encore agi = case vide, tout simplement.
- Board + pot centrés à l'intérieur, entre les deux paires de sièges verticaux. **Le pot affiché inclut toujours toutes les mises déjà faites sur la rue en cours** (pas seulement les rues précédentes) — une confusion s'est produite en session sur ce point (une main lue comme "overbet" alors que c'était une mise standard, parce que le pot affiché avait été mal interprété comme n'incluant pas encore la mise à laquelle le Héros faisait face). Le rappeler explicitement si l'utilisateur hésite sur la taille relative d'une mise.
- Terminologie d'action rigoureuse : "raise" preflop (ou toute relance d'une mise existante), "bet" seulement pour une première mise sur une rue sans mise préalable (jamais preflop) — cohérent avec `gto-glossary`.
- **Main révélée** (showdown ou show volontaire) :
  - position horizontale (UTG) : la main s'affiche **au-dessus** de la ligne identité (encore plus loin de la table que le stack).
  - position verticale (BB/SB/HJ/CO) : la main s'affiche **en dessous** de la ligne stack (3e ligne), même alignement que le reste du côté.

Ne pas régénérer l'ASCII après chaque action isolée — accumuler les actions de la rue, puis afficher l'état complet une fois la rue terminée (ou juste avant la décision du Héros, avec les actions précédentes de la rue déjà visibles).

**Persistance obligatoire entre les rues** : à chaque nouveau rendu (flop, turn, river), transmettre les données de **tous les 6 sièges**, y compris ceux qui ont foldé à une rue précédente — stack toujours affiché. Distinguer explicitement :
- un fold survenu **sur la rue affichée** : `fold` ;
- un joueur déjà sorti à une **rue précédente** : `out`.

**Récapitulatif de transition entre rues (option `show_street_recap`, activée par défaut, désactivable sur demande explicite de l'utilisateur)** : à chaque changement de rue, afficher DEUX rendus successifs plutôt qu'un seul :
1. Le rendu **final de la rue qui vient de se terminer**, avec toutes les actions et montants tels qu'ils étaient à la fin de cette rue (titre `── <RUE> (résumé) ──`) — ça évite à l'utilisateur d'avoir à deviner rétroactivement ce qui s'est passé (ex : qui a call combien) une fois passé à la rue suivante. **Ceci s'applique aussi quand un all-in est callé** : le call qui envoie la main au tapis doit être montré explicitement comme une action à part entière (`call · montant`) avant d'enchaîner sur le(s) rendu(s) des rues suivantes distribuées automatiquement (runout) — ne jamais sauter directement à la river/showdown en laissant deviner que l'adversaire a callé.
2. Puis le rendu de la **nouvelle rue** qui démarre (nouveau board, pot mis à jour, actions remises à vide sauf les `out`).
Si l'utilisateur désactive cette option, ne montrer que le rendu de la rue en cours, sans le récapitulatif intermédiaire.

Ne jamais omettre un joueur du dessin simplement parce qu'il n'est plus actif : ça fait disparaître son stack et rend impossible de savoir d'un coup d'œil qui est encore dans le coup, ni de distinguer une action de cette rue d'un statut hérité. Le dessin sert aussi de récapitulatif visuel du coup en cours, pas seulement de l'état de la rue courante.

**Montant déjà investi par le Héros** : si le Héros a déjà un montant engagé sur la rue en cours avant sa décision (typiquement sa blind preflop), l'afficher à côté du `?` d'attente, format `? · 1𝄫` — même logique que pour les autres joueurs, ne jamais le laisser disparaître.

Les noms d'archétypes sont affichés **directement à côté de la position**, sous forme de code 3 lettres minuscules entre parenthèses (option `show_archetype`, activée par défaut, configurable à la demande) : `FSH` (Fish), `LAG`, `TAG`, `NIT`, `MAN` (Maniac). Ex : `UTG(tag)`, `BB(fsh)`. Le Héros n'a jamais de code (c'est lui). Si l'option est désactivée, revenir aux noms de position seuls, sans légende séparée à ajouter en compensation (les stats HUD complètes restent de toute façon données une fois en toutes lettres à l'annonce du setup).

## Timing des adversaires (tell principal en ligne — désormais en prose, plus dans le dessin)

En ligne, il n'y a pas de tell physique — le **temps de décision** reste le signal le plus réaliste à simuler, mais il ne figure plus dans l'ASCII (source de bugs d'alignement, et surchargeait le dessin). Le décrire à l'écrit, dans le récit qui accompagne le rendu de la rue, et **seulement quand il sort de l'ordinaire** — pas besoin de commenter un timing banal à chaque action :
- **Snap / quasi-snap (quasi instantané)** : action automatique — fold évident, ou call/open standard bien connu du joueur (attention : un snap peut aussi être un piège chez un reg qui joue vite par habitude, ne pas en faire un signal absolu).
- **Tank léger** : un temps de réflexion un peu au-dessus de la norme — rien d'alarmant en soi, mais à noter si le contexte s'y prête.
- **Tank lourd** : hésitation marquée — souvent une main proche de la limite de sa range (marginal call/fold), plus fréquent chez les joueurs moins expérimentés (Fish, Nit) que chez les regs qui tankent aussi parfois pour déguiser l'info.
- Ne pas sur-interpréter systématiquement : rappeler que le timing est un indice probabiliste, pas une certitude — certains joueurs (regs) varient leur timing exprès pour ne rien révéler.

## Résolution des showdowns — obligatoire, jamais à l'œil

**Prérequis (une fois par session sandbox, avant le premier appel à `showdown.py` ou `describe_hand.py`)** :
```bash
pip install treys --break-system-packages -q
```
Ne pas supposer que c'est déjà installé — une session `live-session` peut démarrer sans jamais passer par `equity-engine` avant son premier showdown.

**Ne JAMAIS déclarer un gagnant de showdown par évaluation manuelle/narrative.** Toute confrontation de mains (showdown, ou n'importe quelle comparaison de mains complètes sur un board donné) doit passer par `scripts/showdown.py` (ou un appel direct équivalent à `treys.Evaluator`), sans exception — y compris quand le résultat semble évident. C'est une règle dure, pas une recommandation : une erreur d'évaluation manuelle casse la confiance dans l'outil entier, alors qu'un calcul déterministe ne se trompe jamais sur ce point précis.

```bash
python3 scripts/showdown.py "<board 5 cartes>" "<mainHéros>:Hero" "<mainVillain>:<Position>"
```

Retourne le type de main de chacun et le résultat (`win`/`lose`/`tie`) pour chaque joueur, calculé par l'évaluateur — jamais par inférence.

## Déroulé d'une main

1. Annoncer le setup (table, stacks, profils) une seule fois en début de session, pas à chaque main. **Si plusieurs sièges partagent un archétype marqué (ex : plusieurs Fish/calling stations sur la même table, constat réel d'une session de test), le signaler explicitement à ce moment et appliquer par défaut la doctrine d'`exploit-coach` correspondante sur toute la session — ne pas attendre que l'utilisateur le demande.**
2. Distribuer les cartes du Héros. Pour chaque rue : dérouler les actions adverses (avec timing), puis afficher l'ASCII de la table via `render_table.py` avant la décision du Héros.
3. **Avant chaque décision du Héros** : poser la question ouverte ("qu'est-ce que tu fais ?") plutôt que de suggérer une action.
4. **Si le Héros fold** : la main ne s'arrête pas là. Continuer à simuler les joueurs restants (actions cohérentes avec leur profil HUD) jusqu'à ce qu'il ne reste qu'un joueur (pot remporté sans confrontation) ou jusqu'au showdown. Conclure ensuite avec un résumé bref : qui remporte le pot, et **si une main a été montrée** (showdown, ou show volontaire — plausible notamment chez un Maniac) l'afficher via le rendu de révélation déjà prévu (`cards` dans `render_table.py`). Objectif explicite : permettre à l'utilisateur de confirmer ou ajuster sa lecture du profil après coup, pas seulement pendant la main.
4. Après la décision — **checklist obligatoire, dans cet ordre, avant de conclure une analyse qui dépasse une ligne** (constat de session : "si utile" ne suffit pas, ces outils doivent être appelés par défaut dès qu'une analyse est un peu développée, pas seulement quand ça semble nécessaire) :
   a. Reconstruire la range adverse actuelle par **range narrowing** (méthode détaillée dans `decision-factors`) — jamais énoncer un seuil de rentabilité avant d'avoir vérifié ce qui reste dans cette range.
   b. Calculer l'équité réelle via `equity-engine` (`scripts/equity.py`) entre joueurs encore actifs dans le coup — un joueur qui a foldé sort du calcul.
   c. Toute affirmation sur le type de main du Héros ou ses outs passe par `scripts/describe_hand.py` (jamais à l'œil — voir `poker-rules`).
   d. Tout sizing en %pot passe par `scripts/sizing.py` (jamais de calcul de tête — voir `gto-glossary` pour la convention bet vs raise).
   e. Croiser avec `decision-factors` (position, implied odds, SPR, fold equity, joueurs restants) — au moins en interne, même si la réponse finale ne cite que ce qui change la conclusion.
   f. Commenter avec le vocabulaire de `gto-glossary`, et si la décision dévie du GTO théorique à cause d'un profil adverse exploitable, le dire explicitement en distinguant "ligne GTO" vs "ajustement exploitant".

   **Signal d'alerte ponctuel (à utiliser avec retenue)** : si le raisonnement de l'utilisateur, au moment de justifier de continuer une ligne agressive déjà engagée sur plusieurs rues, s'appuie sur un seuil de rentabilité présenté comme la raison principale de continuer, le signaler **une fois**, brièvement, avant qu'il n'exécute la décision coûteuse — pas après coup dans l'analyse rétrospective, et jamais répété dans la même main une fois signalé. L'utilisateur a explicitement demandé de pouvoir jouer des lignes non conservatrices pour le plaisir : ce n'est pas un blocage, juste un point nommé une fois au bon moment.
   Les actions des joueurs sortis du coup (folds) sont déjà visibles dans le rendu ASCII — l'utilisateur les lit lui-même. Ne pas les commenter systématiquement dans l'analyse : ça noie l'information utile. Ne signaler une action hors-coup que si elle est vraiment surprenante par rapport au profil du joueur (ex un Nit qui 3bet, pas un Fish qui fold une main faible) — rester bref même dans ce cas, une phrase suffit.
5. En fin de session (sur demande ou après un nombre de mains convenu) : résumé des leaks/patterns observés, pas main par main mais agrégé.

## Ce que cette skill NE couvre PAS

L'analyse d'une main déjà jouée en réel → `hand-review` (à construire). La stratégie de tournoi/ICM → hors scope tant que les tournois restent occasionnels et non prioritaires.
