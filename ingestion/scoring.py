"""Deterministic hvac_tier / hvac_score computation from Claude-derived fields.

Pure functions only — no I/O, no Claude calls. Claude produces building_type,
is_ground_up, square_footage, and variance_types (ingestion/extract_fields.py);
this module turns those into a tier and a sortable score, per the scoring
model in docs/ARCHITECTURE.md.
"""

from __future__ import annotations

_TIER_A = {
    "medical_lab",
    "restaurant_commercial_kitchen",
    "cannabis_cultivation",
    "data_center",
    "cold_storage",
    "hotel",
    "school",
    "house_of_worship",
}
_TIER_B = {
    "office",
    "retail",
    "mixed_use",
    "fitness",
    "climate_controlled_self_storage",
}
_TIER_C = {
    "bulk_warehouse_distribution",
    "industrial_shell",
    "parking_structure",
}
_TIER_D = {
    "residential_1_3_family",
    "fences_decks_sheds_signs",
    "parking_only",
    "subdivision_no_building",
}

# "multifamily 4+ stories" is explicitly tier B in the docs; the tier table
# has no bucket for shorter multifamily, so it isn't in any set above —
# hvac_tier() resolves it separately using `stories`.
BUILDING_TYPES = frozenset(_TIER_A | _TIER_B | _TIER_C | _TIER_D | {"multifamily"})


def hvac_tier(building_type: str | None, stories: int | None) -> str | None:
    """A/B/C/D per docs/ARCHITECTURE.md's scoring model, or None when
    building_type is unknown — never guess a tier from missing information."""
    if building_type in _TIER_A:
        return "A"
    if building_type in _TIER_B:
        return "B"
    if building_type in _TIER_C:
        return "C"
    if building_type in _TIER_D:
        return "D"
    if building_type == "multifamily":
        # Shorter multifamily is still real multi-unit HVAC scope, just less
        # definitively than 4+ stories — treat it as C rather than unscored.
        return "B" if stories is not None and stories >= 4 else "C"
    return None


_TIER_POINTS = {"A": 400, "B": 300, "C": 200, "D": 100}
_GROUND_UP_BONUS = 50
# 'd' variances (change of use, d1 strongest) are a strong positive signal;
# 'c' variances (dimensional) carry almost no signal alone — capped low so
# a project with many 'c' variances still scores on its tier, not its count.
_D1_VARIANCE_BONUS = 40
_OTHER_D_VARIANCE_BONUS = 25
_C_VARIANCE_BONUS_PER = 2
_C_VARIANCE_BONUS_CAP = 10
# Square footage is "filtered second, never first" — a small, capped
# tiebreaker that can never outweigh tier.
_SQFT_UNIT = 5000
_SQFT_BONUS_PER_UNIT = 1
_SQFT_BONUS_CAP = 20


def hvac_score(
    tier: str | None,
    is_ground_up: bool | None,
    square_footage: int | None,
    variance_types: list[str],
) -> int | None:
    """One sortable number combining tier, ground-up vs. alteration, square
    footage, and variance type, per docs/ARCHITECTURE.md. None when tier is
    unknown — there's nothing to score."""
    if tier is None:
        return None

    score = _TIER_POINTS[tier]

    if is_ground_up:
        score += _GROUND_UP_BONUS

    normalized = [v.strip().lower() for v in variance_types]
    if any(v.startswith("d1") for v in normalized):
        score += _D1_VARIANCE_BONUS
    elif any(v.startswith("d") for v in normalized):
        score += _OTHER_D_VARIANCE_BONUS
    elif any(v.startswith("c") for v in normalized):
        c_count = sum(1 for v in normalized if v.startswith("c"))
        score += min(c_count * _C_VARIANCE_BONUS_PER, _C_VARIANCE_BONUS_CAP)

    if square_footage:
        score += min((square_footage // _SQFT_UNIT) * _SQFT_BONUS_PER_UNIT, _SQFT_BONUS_CAP)

    return score
