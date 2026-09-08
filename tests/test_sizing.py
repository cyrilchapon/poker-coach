import pytest

from pokercoach.sizing import preflop_open_to


def test_preflop_open_to_rfi_is_just_the_base():
    r = preflop_open_to(0)
    assert r["raise_to_bb"] == pytest.approx(3.0)
    assert r["n_limpers"] == 0
    assert r["exploit_bump_bb"] == 0.0


def test_preflop_open_to_adds_a_bb_per_limper():
    r = preflop_open_to(3)
    assert r["raise_to_bb"] == pytest.approx(6.0)  # 3 + 1*3
    assert r["limpers_bb"] == pytest.approx(3.0)


def test_preflop_open_to_bumps_for_passive_stations_only():
    station = preflop_open_to(1, villain_archetype="calling_station")
    fish = preflop_open_to(1, villain_archetype="fish")
    tag = preflop_open_to(1, villain_archetype="tag")
    plain = preflop_open_to(1)
    assert station["raise_to_bb"] == pytest.approx(5.0)  # 3 + 1 + 1
    assert fish["raise_to_bb"] == pytest.approx(5.0)
    assert tag["raise_to_bb"] == pytest.approx(4.0)  # no bump
    assert plain["raise_to_bb"] == pytest.approx(4.0)


def test_preflop_open_to_rejects_negative_limpers():
    with pytest.raises(ValueError):
        preflop_open_to(-1)
