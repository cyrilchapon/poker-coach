# poker-coach v2 — brief de démarrage

Tu vas construire la v2 d'un plugin Claude existant, `poker-coach`, qui sert de coach
personnel de No-Limit Texas Hold'em à un seul utilisateur.

**Lis d'abord `references/00-lire-en-premier.md`**, qui te dit dans quel ordre absorber
le reste. Ce fichier-ci est le cadrage ; les références contiennent la matière.

---

## 1. Contexte utilisateur (non négociable)

- Joueur unique, joue sur Winamax, **cash game online, une seule table à la fois**.
  Quelques tournois occasionnels, hors scope prioritaire.
- Niveau : connaît les concepts GTO "de loin", aucun maîtrisé en profondeur.
  Le plugin doit **expliquer avec le jargon standard**, pas le contourner.
- Usage : **coaching, review et session simulée uniquement.** Jamais d'assistance
  pendant une main réelle en cours. Ce n'est pas une contrainte de politesse, c'est
  le périmètre produit : l'objectif est d'apprendre à mieux jouer, pas de recevoir
  une réponse à la table. Toute décision d'architecture qui n'aurait de sens qu'en
  temps réel (latence sub-seconde, capture d'écran, hook client) est hors sujet.
- Leak identifié et documenté par l'utilisateur : **s'acharner à bluffer jusqu'à la
  river en se sentant "commité" dans sa ligne**, notamment face à des joueurs
  loose-passifs. La v2 doit traiter ça structurellement (voir §4, budget ATT/DEF).
- Préférence d'affichage déjà actée : cartes en unicode `♠♥♦♣`, jamais `Kh`.

## 2. Les trois objectifs de la v2

1. **Puissance** — coller à l'état de l'art du "solving" poker version LLM.
   La référence retenue est PokerSkill (Li, Wang, Huang — Tsinghua, arXiv 2605.30094).
   Voir `references/01-pokerskill-analysis.md` pour ce qui est réellement reprenable
   et ce qui ne l'est pas.
2. **Vitesse de décision** — moins d'allers-retours, moins de calculs refaits,
   coupe précoce des branches de décision.
3. **Coût en tokens** — objectif de réduction forte et mesurable. Voir
   `references/04-current-plugin-audit.md` pour la mesure de la v1 et les leviers.

Les trois convergent vers la même solution : **déplacer tout ce qui est déterministe
du raisonnement du LLM vers un moteur scripté à entrée/sortie structurée**, et ne
laisser au LLM que le jugement en zone grise et la pédagogie.

## 3. Portée de format : HU → 8-max

La v1 est 6-max. La v2 doit couvrir **heads-up à 8-max**.

⚠️ **Ne construis pas une table de ranges par format.** C'est le piège qui rend le
travail infaisable (3 formats × 8 positions × 6 types de pot × profondeurs de stack).

L'approche imposée est décrite dans `references/03-multiway-generalization.md` :
indexer par `(joueurs restant à parler derrière, type de pot, profondeur effective)`
plutôt que par label de position. HU, 6-max et 8-max deviennent alors trois vues
d'une même table paramétrée. Lis ce document avant d'écrire la moindre ligne de
`ranges/`.

## 4. Ce qu'il faut reprendre de PokerSkill

Les tables sont déjà réencodées pour toi en YAML dans `data/` (source : annexe E du
papier, réécrite en données structurées — le code du repo est compilé et inutilisable,
voir `references/01-pokerskill-analysis.md`).

Le mécanisme central est le **budget ATT/DEF** : chaque classe de main reçoit un
budget d'agression et de défense exprimé en "rues pondérées", décrémenté par la
pression de chaque mise déjà engagée dans la main. Budget épuisé → l'action est
**retirée des options viables**, pas déconseillée.

C'est la réponse structurelle au leak de l'utilisateur : la troisième barrel devient
mécaniquement indisponible quand le budget est consommé, au lieu d'être un
avertissement que le raisonnement peut contourner en se justifiant.

## 5. Architecture cible

Détaillée dans `references/02-architecture-v2.md` (schéma d'état, API du CLI,
cascade de gates, découpage des modules). En résumé :

- **Couche A** — un état de main canonique JSON, unique source de vérité, mis à jour
  incrémentalement. Fin de la ré-narration en prose de la table à chaque rue.
- **Couche B** — un moteur Python unique exposé par un CLI `pc`, tout en JSON.
  **Un seul appel par décision** (`pc brief`), pas 4–5 allers-retours bash.
- **Couche C** — une cascade de gates à discriminants early : chaque niveau peut
  clore la décision sans raisonnement LLM. Seul le dernier niveau charge les skills
  de raisonnement complet.

## 6. Contraintes techniques

- **Python**, pas Node. Le sandbox Claude a Python et l'écosystème poker y est.
- Dépendances : privilégier `eval7` ou `phevaluator` (backend C) sur `treys`
  (Python pur, actuellement utilisé, ~40× plus lent). Vérifie la disponibilité par
  `pip install` dans le sandbox avant de t'engager ; garde un fallback `treys`.
- **Aucune dépendance réseau à l'exécution.** Pas d'API solveur, pas de clé.
- Tout ce qui est calculable une fois doit être **précalculé en fichier statique**,
  pas recalculé par run.
- Le moteur doit être testable seul : `pytest`, fixtures de mains, pas de LLM dans
  la boucle de test.
- Sortie du CLI : JSON strict sur stdout, erreurs sur stderr, code de retour non nul
  en cas d'état invalide. Jamais de prose sur stdout.

## 7. Ordre de travail recommandé

L'utilisateur a validé que le budget ATT/DEF seul, implémenté proprement, apporte
probablement l'essentiel du gain. Ne pars donc pas sur une réécriture totale d'emblée.

1. **Squelette moteur** — package `pokercoach/`, schéma d'état, `pc state` qui valide
   et dérive (pot, SPR, stack effectif, cotes, MDF, qui parle). Tests.
2. **Classification déterministe** — `pc hand` : les 23 classes de main, la texture
   de board, les outs, les blockers. C'est le socle de tout le reste. Tests exhaustifs
   sur des mains connues, y compris les boards spéciaux (paired, trips, quads,
   monotone, 4-flush, double-paired).
3. **Budget ATT/DEF** — `pc budget` : tables `data/*.yaml`, pression pondérée,
   modificateurs de texture et de type de pot, décrémentation par l'historique.
   C'est la pièce à plus fort rendement. Tests sur les traces du papier.
4. **Équité rapide** — réécriture de `equity.py` : énumération exhaustive quand le
   nombre de combos le permet, Monte-Carlo vectorisé sinon, cache par
   `(range1, range2, board)`. Support d'une main exacte à deux cartes (limitation
   connue de la v1). Support de la pondération `@xx%`.
5. **Cascade de gates** — `pc brief`, qui orchestre tout ce qui précède et retourne
   un verdict + un niveau de gate.
6. **Ranges paramétrées** — le gros morceau, voir §3.
7. **Refonte des skills** — les 11 SKILL.md deviennent des enveloppes minces autour
   du CLI. Voir `references/04-current-plugin-audit.md` pour le détail fichier par
   fichier de ce qui reste, ce qui descend dans le code, ce qui disparaît.

Après chaque étape : mesure. Le brief demande une réduction de tokens, donc chaque
étape doit produire un chiffre avant/après, pas une impression.

## 8. Ce sur quoi il faut interroger l'utilisateur plutôt que décider seul

- La valeur exacte des seuils de gate (à quel écart de bornes on tranche sans LLM) —
  c'est un curseur qualité/coût qui lui appartient.
- Le niveau de verbosité par gate.
- L'arbitrage sur les ranges 7/8-max si la généralisation paramétrée s'avère trop
  imprécise en pratique (voir §3 et le doc dédié).
- Toute suppression de comportement existant qu'il a explicitement demandé en v1 —
  le rendu ASCII de la table, la persistance des archétypes sur la session, le
  récapitulatif de transition entre rues, la résolution obligatoire des showdowns
  par script. Ces éléments sont des décisions produit déjà prises, pas des accidents.

## 9. Ce qu'il ne faut pas faire

- Ne pas transformer le coach en bot. Il pose des questions ouvertes ("qu'est-ce que
  tu fais ?") avant de donner un avis. Le moteur calcule, le coach enseigne.
- Ne pas supprimer la couche exploitante (archétypes HUD, `exploit-coach`). C'est ce
  que le plugin a en plus de PokerSkill, qui n'a aucun modèle adverse.
- Ne pas gonfler les SKILL.md. Tout ce qui est un contrat de script descend dans le
  docstring ou le `--help` du script.
- Ne pas laisser le LLM recalculer ce que le moteur a déjà calculé.
