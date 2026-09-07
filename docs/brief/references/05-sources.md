# Sources et attributions

## PokerSkill

- **Papier** : Boning Li, Baoxiang Wang, Longbo Huang, *PokerSkill: LLMs Can Play
  Expert-Level Poker without Training or Solvers*, arXiv:2605.30094 [cs.AI], 28 mai 2026.
  45 pages, 3 figures. Sous licence perpétuelle non exclusive arXiv.
  - `https://arxiv.org/abs/2605.30094`
  - `https://arxiv.org/html/2605.30094v1` (version HTML, annexes comprises)
- **Code** : `https://github.com/lbn187/PokerSkill`, v2.0.0, licence CC BY-NC 4.0
  (usage non commercial). Cloné et inspecté ; cœur compilé et non utilisé.
- **Affiliations** : IIIS Tsinghua University ; CUHK-Shenzhen.
- **Contact** : li-bn22@mails.tsinghua.edu.cn

Les fichiers de `data/att-def-budgets.yaml`, `pressure-weights.yaml`,
`texture-modifiers.yaml` et `hand-classes.yaml` sont une **réécriture en données
structurées** des tables publiées aux annexes D et E du papier. Aucune extraction
n'a été faite depuis les binaires compilés du repo.

**Attribution à conserver** dans le README du projet v2 et dans le `--help` du CLI :
mention du papier, des auteurs et du lien. C'est le minimum décent et ça coûte
trois lignes.

## Benchmark cité par le papier

- GTOWizard Benchmark : Marc-Antoine Provost, Nejc Ilenic, Christopher Solinas,
  Philippe Beardsell, arXiv:2603.23660, 2026.
- AIVAT (réduction de variance) : Neil Burch, Michael Johanson, Michael Bowling,
  AAAI 2018.
- Slumbot : Eric Jackson, AAAI Workshop on Computer Poker, 2013.

## Ce qui vient du plugin v1

Tout `current-plugin/` est la production de l'utilisateur et des sessions de
conception précédentes. Les décisions produit qui y figurent (rendu ASCII,
persistance des archétypes, doctrine anti-calling-station, méthode de range
narrowing, obligation de résolution des showdowns par script) sont des acquis,
pas des suggestions.

## Ce qui n'a aucune source

`data/multiway-adjustment.yaml` et `data/preflop-rfi.yaml` sont des propositions
construites pour ce projet. Elles sont marquées comme telles dans leurs en-têtes.
Ne les présente jamais comme issues de PokerSkill ni comme du GTO.
