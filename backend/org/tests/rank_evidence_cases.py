"""Profile field sets and whether each counts as a declared rank.

Shared by the org 0010 backfill test and the runtime has_rank_evidence test
so the two rules cannot drift apart.
"""

RANK_EVIDENCE_CASES: dict[str, tuple[dict[str, object], bool]] = {
    "active": ({"rank_status": "active"}, True),
    "previous": ({"rank_status": "previous"}, True),
    "screenshot": ({"rank_status": "never", "rank_screenshot": "x"}, True),
    "battlecup_shot": ({"rank_status": "never", "battlecup_screenshot": "x"}, True),
    "medal": ({"rank_status": "never", "rank_medal": "Herald"}, True),
    "tier": ({"rank_status": "never", "battle_cup_tier": 3}, True),
    "default": ({"rank_status": "never"}, False),
    "positions_only": (
        {"rank_status": "never", "pos_1": True},
        False,
    ),
}
