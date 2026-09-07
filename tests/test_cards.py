import pytest

from pokercoach.cards import Card, CardError, parse_card, parse_cards, format_card, format_cards


def test_parse_unicode():
    assert parse_card("A♠") == Card("A", "♠")
    assert parse_card("t♦") == Card("T", "♦")  # rang insensible à la casse


def test_parse_letter_notation_normalizes_to_unicode():
    assert parse_card("Ah") == Card("A", "♥")
    assert parse_card("Kc") == Card("K", "♣")
    assert parse_card("2S") == Card("2", "♠")  # couleur lettre insensible à la casse


def test_format_is_always_unicode():
    assert format_card(parse_card("Ah")) == "A♥"
    assert format_cards([parse_card("Ah"), parse_card("Kc")]) == ["A♥", "K♣"]


@pytest.mark.parametrize("bad", ["", "A", "A♠♠", "1♠", "Az", "AAA"])
def test_invalid_card_raises(bad):
    with pytest.raises(CardError):
        parse_card(bad)


def test_duplicate_card_in_list_raises():
    with pytest.raises(CardError):
        parse_cards(["A♠", "As"])  # même carte, deux notations


def test_parse_cards_ok():
    cards = parse_cards(["A♠", "K♦"])
    assert [str(c) for c in cards] == ["A♠", "K♦"]
