"""Card parsing and formatting.

Display convention (non négociable, cf. PROMPT.md §1) : les cartes sortent
toujours en unicode ``A♠``, jamais ``As``. En entrée, les deux notations sont
acceptées et normalisées.
"""
from __future__ import annotations

from dataclasses import dataclass

RANKS = "23456789TJQKA"

# Unicode <-> letter suit mapping. Unicode is canonical for output.
SUITS_UNICODE = ("♠", "♥", "♦", "♣")
_SUIT_TO_LETTER = {"♠": "s", "♥": "h", "♦": "d", "♣": "c"}
_LETTER_TO_SUIT = {v: k for k, v in _SUIT_TO_LETTER.items()}


class CardError(ValueError):
    """Raised on a malformed or duplicate card."""


@dataclass(frozen=True, order=False)
class Card:
    rank: str  # one of RANKS
    suit: str  # one of SUITS_UNICODE (canonical, unicode)

    @property
    def rank_index(self) -> int:
        return RANKS.index(self.rank)

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"

    def to_letter(self) -> str:
        """Letter notation (e.g. ``Ah``), for interop with libraries like treys/eval7."""
        return f"{self.rank}{_SUIT_TO_LETTER[self.suit]}"


def parse_card(token: str) -> Card:
    """Parse a single 2-character card token, unicode or letter suit.

    Accepts ``"A♠"`` or ``"As"``. Rank is case-insensitive for letters
    (``t``/``T``), suit letter is case-insensitive (``S``/``s``).
    """
    if not isinstance(token, str):
        raise CardError(f"carte invalide (attendu une chaîne) : {token!r}")
    token = token.strip()
    if len(token) != 2:
        raise CardError(f"carte invalide (2 caractères attendus) : {token!r}")

    rank_char, suit_char = token[0].upper(), token[1]
    if rank_char not in RANKS:
        raise CardError(f"rang de carte invalide : {token!r}")

    if suit_char in SUITS_UNICODE:
        suit = suit_char
    elif suit_char.lower() in _LETTER_TO_SUIT:
        suit = _LETTER_TO_SUIT[suit_char.lower()]
    else:
        raise CardError(f"couleur de carte invalide : {token!r}")

    return Card(rank=rank_char, suit=suit)


def parse_cards(tokens: list[str]) -> list[Card]:
    """Parse a list of card tokens, raising on any duplicate within the list."""
    cards = [parse_card(t) for t in tokens]
    seen: set[tuple[str, str]] = set()
    for c in cards:
        key = (c.rank, c.suit)
        if key in seen:
            raise CardError(f"carte en double : {c}")
        seen.add(key)
    return cards


def format_card(card: Card) -> str:
    return str(card)


def format_cards(cards: list[Card]) -> list[str]:
    return [format_card(c) for c in cards]
