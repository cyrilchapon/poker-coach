"""Couche B — ``pc glossary <terme>`` : une définition, pas 6 ko préchargés.

Condensé de ``skills/gto-glossary/SKILL.md`` (v1). Le coach lit une entrée à
la demande au lieu de charger tout le glossaire en contexte à chaque
décision — le levier de tokens #5 de la stratégie de réduction (voir
docs/brief/references/02-architecture-v2.md).
"""
from __future__ import annotations

TERMS: dict[str, str] = {
    "range": "l'ensemble pondéré des mains qu'un joueur peut avoir dans une situation donnée.",
    "combo": "une combinaison précise de deux cartes (ex : A♠K♥ est un combo parmi les 16 combos d'AK).",
    "equity": "probabilité de gagner la main si elle allait au tapis immédiatement.",
    "équité": "probabilité de gagner la main si elle allait au tapis immédiatement.",
    "ev": "gain moyen espéré d'une décision sur un grand nombre de répétitions (Expected Value).",
    "pot odds": "rapport mise à payer / pot après paiement ; l'équité minimale requise pour un call rentable.",
    "cotes du pot": "rapport mise à payer / pot après paiement ; l'équité minimale requise pour un call rentable.",
    "spr": "Stack-to-Pot Ratio, stack effectif / taille du pot ; conditionne l'agressivité postflop.",
    "mdf": "Minimum Defense Frequency, fréquence minimale à laquelle défendre pour empêcher un bluff automatiquement rentable.",
    "mdf collective": "en multiway, l'obligation de défense combinée de tous les défenseurs (formule heads-up pot/(pot+bet)) — pas l'obligation de chacun.",
    "mdf individuelle": "en multiway, ce que CHAQUE défenseur peut folder individuellement tout en respectant le MDF collectif — plus permissif que le MDF heads-up, chacun peut folder davantage.",
    "blocker": "carte en main qui réduit la probabilité que l'adversaire détienne certains combos.",
    "range polarisée": "range composée de mains très fortes + bluffs, sans mains moyennes.",
    "range linéaire": "range composée des meilleures mains dans l'ordre de force, sans bluffs purs (aussi 'merged').",
    "range condensée": "range resserrée autour de mains moyennes-fortes, sans les meilleures ni les pires combos.",
    "range advantage": "quand un joueur a, en moyenne, une range plus forte que l'autre sur un board donné.",
    "nut advantage": "quand un joueur a une plus grande proportion des toutes meilleures mains possibles sur ce board.",
    "c-bet": "continuation bet, mise faite par le dernier agresseur de la rue précédente.",
    "3bet": "deuxième relance d'une même série d'enchères sur une rue.",
    "4bet": "troisième relance d'une même série d'enchères sur une rue.",
    "squeeze": "3bet après une ouverture ET un ou plusieurs calls, visant les deux ranges à la fois.",
    "iso-raise": "relance visant à isoler un limpeur (l'affronter en heads-up). Aussi 'isolation raise'.",
    "multiway": "pot encore disputé par 3 joueurs ou plus (par opposition à heads-up, 2 joueurs) -- resserre mécaniquement les ranges de bluff/continuation (fold equity divisée entre plus d'adversaires), cf. data/multiway-adjustment.yaml.",
    "stab": "mise d'opportunité sur une rue où personne n'a montré de force (ex. le héros checke le flop derrière un raiser qui checke aussi, puis stab la turn) -- même idée que 'probe bet'.",
    "calling station": "archétype adverse passif qui call trop large et bluffe/relance rarement -- exploitant : ATT abaissé (le bluff ne convertit pas en fold), DEF quasi inchangé (il paie de toute façon ce qu'il aurait payé).",
    "fold equity": "probabilité que l'adversaire fold face à une mise/relance -- avec l'équité brute en cas de call, c'est l'une des deux composantes de l'EV d'un bluff ou d'un semi-bluff.",
    "réalisation d'équité": "la part de l'équité brute d'une main qu'elle parvient réellement à convertir en gains une fois les rues futures jouées (position, taille de range, capacité à barreler/bluffer) -- deux mains de même équité brute ne la 'réalisent' pas forcément pareil.",
    "gto": "Game Theory Optimal, stratégie d'équilibre inexploitable par définition.",
    "exploit": "dévier volontairement du GTO pour maximiser l'EV contre un adversaire déséquilibré.",
    "icm": "Independent Chip Model, convertit les jetons en valeur monétaire réelle en tournoi.",
    "bubble factor": "facteur de risque accru en approche de bulle de tournoi (ICM), resserre les ranges de call.",
    "n_behind": "nombre de joueurs qui doivent encore parler derrière soi au premier tour préflop.",
    "ip_postflop": "sera-t-on en position après le flop contre le caller le plus probable (booléen).",
    "implied odds": "cotes du pot ajustées par les mises futures qu'on peut encore extraire si le tirage touche -- rend rentable un call que les seules cotes actuelles du pot ne justifient pas. Facteur qualitatif (skill decision-factors, gate G5) : pas modélisé dans le budget ATT/DEF chiffré (att-def-budgets.yaml), qui ignore ce à quoi ressemblera la mise suivante.",
    "reverse implied odds": "l'inverse des implied odds : une main qui touche mais reste derrière (ex. top pair petit kicker qui bat un kicker faible mais perd contre un meilleur) -- l'équité brute surestime alors sa vraie valeur, car payer expose à perdre un pot plus gros ensuite.",
    "att": "budget d'agression : cumul de rues pondérées qu'une classe de main peut encore financer.",
    "def": "budget de défense : cumul de mises pondérées qu'une classe de main peut encore payer.",
    "tptk": "Top Pair Top Kicker : paire avec la carte la plus haute du board et le meilleur kicker possible.",
    "gate": "niveau de la cascade de décision qui a tranché sans (ou avec un minimum de) raisonnement LLM.",
}

# Régression : `pc glossary isolation` → « terme inconnu » alors que
# `iso-raise` couvre exactement ce concept -- le coach emploie couramment
# des synonymes, variantes avec/sans tiret, ou la forme "snake_case" que le
# reste du moteur utilise pour ses propres identifiants (villain_archetype,
# etc.), pas la clé exacte de TERMS. ALIASES fait le pont vers la clé
# canonique plutôt que d'exiger une correspondance littérale.
ALIASES: dict[str, str] = {
    "isolation": "iso-raise",
    "isolation raise": "iso-raise",
    "iso raise": "iso-raise",
    "equity realization": "réalisation d'équité",
    "realisation equite": "réalisation d'équité",
    "realisation d'equite": "réalisation d'équité",
    "équité réalisée": "réalisation d'équité",
    "equite realisee": "réalisation d'équité",
}


def _resolve(candidate: str) -> str | None:
    if candidate in TERMS:
        return TERMS[candidate]
    canonical = ALIASES.get(candidate)
    return TERMS.get(canonical) if canonical else None


def lookup(term: str) -> str | None:
    raw = term.strip().lower()
    found = _resolve(raw)
    if found is not None:
        return found
    # Repli "_" -> " " pour les variantes snake_case (fold_equity,
    # equity_realization) -- APRÈS l'essai exact, pour ne pas casser des
    # clés qui contiennent elles-mêmes un "_" à dessein (n_behind,
    # ip_postflop : des identifiants repris tels quels du reste du moteur).
    spaced = raw.replace("_", " ")
    return _resolve(spaced) if spaced != raw else None
