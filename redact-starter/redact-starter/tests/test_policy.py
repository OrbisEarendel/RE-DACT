from core.policy import load_policy


def test_higher_levels_act_on_everything_lower_levels_act_on():
    """If L1 masks PHONE, then L2 and L3 must also act on PHONE (never 'keep' it)."""
    policy = load_policy()
    levels = sorted(policy)
    for lo, hi in zip(levels, levels[1:]):
        acted_lo = {t for t, a in policy[lo].items() if a != "keep"}
        acted_hi = {t for t, a in policy[hi].items() if a != "keep"}
        assert acted_lo <= acted_hi, f"Level {hi} drops {acted_lo - acted_hi} that level {lo} handles"
