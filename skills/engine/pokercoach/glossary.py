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


def lookup(term: str) -> str | None:
    return TERMS.get(term.strip().lower())
