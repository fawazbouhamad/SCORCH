"""Heatwave labelling tests against the canonical per-box rules."""
import pandas as pd

from scorch.labeling import label_heatwaves


def _series(bits, start="2000-06-01"):
    idx = pd.date_range(start, periods=len(bits), freq="D")
    return pd.Series(list(bits), index=idx, dtype=int)


def test_run_of_three_labelled():
    s = _series([0, 1, 1, 1, 0])
    labels, episodes = label_heatwaves(s)
    assert len(episodes) == 1
    hw_id, start, end, length, ones, zeros = episodes[0]
    assert length == 3 and ones == 3 and zeros == 0
    assert labels.sum() == 3  # exactly the three exceedance days carry id 1
    assert set(labels.unique()) == {0, 1}


def test_run_of_two_not_labelled():
    s = _series([0, 1, 1, 0, 0])
    labels, episodes = label_heatwaves(s)
    assert episodes == []
    assert (labels == 0).all()


def test_single_zero_bridged():
    # 1 1 0 1 : one segment (no "00"), trimmed length 4, three exceedance days
    s = _series([1, 1, 0, 1])
    labels, episodes = label_heatwaves(s)
    assert len(episodes) == 1
    _hw, _s, _e, length, ones, zeros = episodes[0]
    assert (length, ones, zeros) == (4, 3, 1)
    assert (labels.values == [1, 1, 1, 1]).all()  # bridge day is inside


def test_unlimited_single_zero_bridging():
    # Multiple isolated zeros inside one event are all bridged.
    s = _series([1, 0, 1, 0, 1, 0, 1])
    labels, episodes = label_heatwaves(s)
    assert len(episodes) == 1
    _hw, _s, _e, length, ones, zeros = episodes[0]
    assert (length, ones, zeros) == (7, 4, 3)


def test_two_zero_split():
    # "00" splits into two independent qualifying events.
    s = _series([1, 1, 1, 0, 0, 1, 1, 1])
    labels, episodes = label_heatwaves(s)
    assert len(episodes) == 2
    assert sorted(set(labels.unique())) == [0, 1, 2]
    assert (labels.values[:3] == 1).all()
    assert (labels.values[5:] == 2).all()
    assert (labels.values[3:5] == 0).all()


def test_trim_rule_event_starts_and_ends_with_one():
    # Leading/trailing zeros in a segment are trimmed before qualification.
    s = _series([0, 1, 1, 1, 0])
    labels, episodes = label_heatwaves(s)
    assert len(episodes) == 1
    _hw, start, end, length, _ones, _zeros = episodes[0]
    assert start == s.index[1].date() and end == s.index[3].date()
    assert length == 3
    assert labels.iloc[0] == 0 and labels.iloc[4] == 0


def test_trim_can_disqualify_short_core():
    # Segment 0 1 1 0 (no "00" inside): trims to length 2 -> rejected.
    s = _series([0, 1, 1, 0])
    labels, episodes = label_heatwaves(s)
    assert episodes == []
    assert (labels == 0).all()
