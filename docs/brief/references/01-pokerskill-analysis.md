# PokerSkill — analyse

Source : https://github.com/lbn187/PokerSkill (v2.0.0, CC BY-NC 4.0) et
arXiv 2605.30094, *PokerSkill: LLMs Can Play Expert-Level Poker without Training or
Solvers*, Boning Li, Baoxiang Wang, Longbo Huang (Tsinghua / CUHK-Shenzhen).

Repo cloné et lu intégralement. Papier lu (45 pages, annexes comprises).

---

## Ce que c'est réellement

Pas un solveur, pas une AI de poker. C'est un **framework de prompting structuré** :
un moteur déterministe analyse l'état de jeu, produit des labels compacts, et n'injecte
dans le prompt du LLM que les fragments pertinents d'une bibliothèque de règles écrite
à la main par des experts humains. Le LLM décide **dans les bornes** posées par le
moteur.

Le papier nomme le problème qu'il attaque le **decision-binding problem** : un LLM sait
expliquer les cotes du pot, le MDF, la polarisation — mais échoue à sélectionner
*lequel* de ces concepts doit gouverner une décision précise. L'exemple donné est
frappant : Claude Opus 4.6, tenant 4♥7♠ sur un board 5♥4♣3♥4♠3♠, écrit « j'ai QKo,
air complet, pas de paire » — alors qu'il a un brelan de 4. Ce n'est pas une erreur de
raisonnement, c'est un échec de lecture de l'état.

**C'est directement pertinent pour la v2** : tout ce que le moteur peut établir de
façon déterministe (classe de main, texture, outs, qui est l'agresseur, pression
cumulée) doit être retiré du raisonnement du LLM, pas parce que c'est coûteux en
tokens, mais parce que c'est là qu'il se trompe.

## Résultats réels — à ne pas surestimer

Contre GTOWizard, avec réduction de variance AIVAT, sur ≥5000 mains :

| Agent | mbb/main |
|---|---|
| GPT-5.5 XHigh + PokerSkill | −57 ± 21 |
| Claude Opus 4.6 + PokerSkill | −80 ± 29 |
| Claude Opus 4.7 + PokerSkill | −87 ± 64 |
| **Règles seules, sans LLM** | **−132 ± 19** |
| GPT-5.5 XHigh, prompt par défaut | −132 ± 25 |
| Claude Opus 4.6, prompt par défaut | −204 ± 44 |

Lecture : **ça perd, juste beaucoup moins**. Réduction de 49–61 % par rapport au
prompt nu. Le moteur de règles seul joue au niveau d'un LLM non guidé. La conclusion
des auteurs est que ni les règles ni le LLM ne suffisent, mais que leur combinaison
fonctionne.

Conséquence pour nous : **ne présente jamais ces tables comme du GTO**. Ce sont des
heuristiques expertes calibrées, pas une solution d'équilibre. Le coach doit dire
« référence experte » et non « la solution GTO dit ».

Anomalie notable, mentionnée par les auteurs : en prompt par défaut, la performance
n'est pas monotone avec la capacité du modèle. Leur hypothèse est que le
decision-binding empire quand le modèle considère plus de facteurs sans mécanisme
pour les hiérarchiser. C'est un argument de plus en faveur de la cascade de gates.

## Portabilité — verdict

**Le code est inutilisable.** Structure du repo :

```
pokerskill_agent/
  cli.py, schema.py, __init__.py          ← lisibles, sans intérêt stratégique
  _battle/llm_client.py                   ← lisible, client Anthropic/OpenAI banal
  _core/prompt_builder.so                 ← compilé
  _core/postflop_analyzer.so              ← compilé
  _core/action_line_context.so            ← compilé
  _core/unwanted_outs.so                  ← compilé
  _core/skill_content.so                  ← compilé
  _range/preflop_range.so                 ← compilé
  _battle/{runner,response_parser,gto_client}.so
```

Blocages cumulés :

1. Extensions Cython `cpython-39-x86_64-linux-gnu` — **Python 3.9 + Linux x86_64
   exclusivement**. Le sandbox tourne en 3.12.
2. Compilées avec `CYTHON_COMPRESS_STRINGS` : les constantes texte sont zlib-compressées
   dans le binaire. `strings` ne rend rien d'exploitable sur `skill_content.so`
   (63 ko, 225 chaînes ≥12 caractères, aucune contenant de stratégie).
3. Le `BattleRunner` exige `GTO_WIZARD_API_KEY` (API Researcher payante) — il ne sert
   qu'à jouer contre GTOWizard pour le benchmark, aucun intérêt ici.
4. C'est du heads-up strict : `schema.py` impose `VALID_POSITIONS = {"BTN", "BB"}`,
   200bb, 12 scénarios préflop.

**Mais tout le contenu de valeur est publié dans le papier.** L'annexe E donne les
tables ATT/DEF complètes pour les 23 classes de main, les modificateurs de texture,
la table de pression à 46 seuils, les overrides de boards spéciaux. L'annexe D donne
la taxonomie de classification. L'annexe C donne la structure des couches de prompt.
L'annexe I donne des traces complètes de prompts réels.

C'est de là que viennent les fichiers de `data/`. **Ne perds pas de temps à essayer
d'extraire quoi que ce soit des `.so`** : il n'y a rien dedans qui ne soit pas déjà
dans le papier, sous une forme d'ailleurs plus lisible.

## Piège de lecture du README

Le README ouvre sur un paragraphe qui décrit une AI capable de « crush online Texas
Hold'em », avec résolution d'équilibre en millisecondes en multijoueur, gérant les
scénarios que les solveurs ne gèrent pas (limps multiples, 4+ joueurs au flop).

Ce paragraphe dit explicitement **« Our Poker AI (not PokerSkill) »** et se termine par
un appel à coopération commerciale. C'est un autre produit, non publié, absent du repo.
Rien de ce qui est décrit là n'est disponible.

## Les cinq couches (annexe C)

| Couche | Portée | Contenu |
|---|---|---|
| P1 | toujours | Règles, actions légales, format de sortie, protocole |
| P2 | préflop | La seule entrée de table de ranges du scénario détecté |
| P3 | postflop | Principes stables : séparation value/bluff, position, pot control, discipline de sizing |
| P4 | postflop | Stratégie ciblée par texture × classe de main × action-line × rôle |
| P5 | river | Blockers, bluff et bluff-catch |

Une décision préflop retire P1 + une entrée P2. Une décision flop retire P1 + P3 + les
entrées P4 correspondantes. La river ajoute P5. **Jamais la bibliothèque entière.**

Le papier justifie ça par deux modes d'échec évités : le conseil général vague qui ne
tranche pas la décision, et le détail écrasant qui force le modèle à arbitrer entre des
heuristiques non pertinentes. C'est exactement le problème de la v1 du plugin, qui
charge `decision-factors` + `gto-glossary` + `live-session` intégralement quelle que
soit la décision.

## Le système de budget ATT/DEF (annexe E) — la pièce maîtresse

Principe : **une main a une capacité stratégique finie**. Une main de force moyenne
peut absorber une mise mais pas trois barrels consécutifs.

```
B_att_restant = B_att(classe, contexte) − Σ w(mises précédentes)
B_def_restant = B_def(classe, contexte) − Σ w(mises précédentes)
```

où `w()` est la pression pondérée, fonction croissante de la taille de mise en %pot
(table de 46 seuils, `data/pressure-weights.yaml`).

Les budgets de base viennent de la classe de main (∞ pour les nuts, 0 pour le trash),
puis sont ajustés par : type de pot (limp / SRP / 3BP / 4BP+), texture de board,
position, SPR, et overrides de boards spéciaux.

Les mains de tirage ne fonctionnent pas pareil : leur défense s'exprime en **seuil de
taille de mise défendable en %pot**, pas en budget cumulé, parce que l'équité d'un
tirage dépend des cartes restantes et non de la pression accumulée. Une règle de combo
additionne la contribution du tirage à la baseline de la main faite.

Le papier revendique que ce mécanisme encode trois intuitions GTO sans calcul
d'équilibre : la mise géométrique distribue la pression sur les rues, le MDF gouverne
les continuations, et les situations à faible SPR se simplifient en commit-or-fold.

**Pourquoi c'est la pièce à implémenter en premier ici** : le budget se décrémente à
chaque mise. Une main qui a barrelé flop et turn arrive à la river avec un budget
insuffisant, et l'action est **retirée des options viables**. C'est exactement le leak
documenté de l'utilisateur, converti d'un avertissement contournable en une contrainte
dure.

## Limites reconnues par les auteurs (annexe G) — à traiter

Trois modes d'échec persistants malgré le scaffolding :

1. **Erreur de sizing.** Le budget autorise correctement la mise, le LLM choisit une
   mauvaise taille. L'intuition fine de sizing s'active moins bien que la décision
   binaire miser/checker.
2. **Ambiguïté de frontière de classe.** Une top paire avec un 5e kicker reçoit le
   budget de « top pair » alors que son profil stratégique réel est plus proche de
   « second pair » compte tenu de la texture et du type de pot. La classification
   discrète ne capture pas la nature continue de la force d'une main.
   → *Piste v2 : exposer la distance à la frontière dans le brief, et laisser le gate
   escalader vers le LLM quand la main est près d'une frontière.*
3. **Incohérence multi-rues.** Les budgets sont localement corrects mais la séquence
   des trois rues n'est pas planifiée globalement. Le système ne peut pas anticiper
   que miser le turn crée une river inconfortable.
   → *Piste v2 : `pc brief` peut retourner un plan de rues projeté (sizing géométrique
   sur les rues restantes) pour donner au coach de quoi enseigner la planification.*

Ces trois limites sont des points d'amélioration explicites pour la v2, pas des
fatalités à recopier.

## Ce qu'il ne faut pas reprendre

- **Les ranges préflop.** 12 scénarios heads-up à 200bb. Sans objet.
- **L'absence de modèle adverse.** PokerSkill joue contre un GTO parfait et n'a aucune
  notion de profil. Le plugin actuel a des archétypes HUD et une skill `exploit-coach`.
  C'est un avantage net sur PokerSkill, à conserver et à brancher sur les budgets
  (voir `02-architecture-v2.md`, gate G4).
- **La calibration 200bb.** L'utilisateur joue à 100bb. Les seuils de SPR et de
  commitment ne se transposent pas mécaniquement.
