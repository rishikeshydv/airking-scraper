from ingestion.scoring import hvac_score, hvac_tier


def test_tier_a_building_types() -> None:
    assert hvac_tier("hotel", None) == "A"
    assert hvac_tier("cannabis_cultivation", None) == "A"


def test_mixed_use_is_tier_b() -> None:
    assert hvac_tier("mixed_use", None) == "B"


def test_bulk_warehouse_is_tier_c() -> None:
    assert hvac_tier("bulk_warehouse_distribution", None) == "C"


def test_one_to_three_family_is_tier_d() -> None:
    assert hvac_tier("residential_1_3_family", None) == "D"


def test_multifamily_of_four_or_more_stories_is_tier_b() -> None:
    assert hvac_tier("multifamily", 4) == "B"


def test_shorter_or_unknown_height_multifamily_is_tier_c() -> None:
    assert hvac_tier("multifamily", 3) == "C"
    assert hvac_tier("multifamily", None) == "C"


def test_unknown_building_type_has_no_tier() -> None:
    assert hvac_tier(None, 10) is None
    assert hvac_tier("spaceport", 10) is None


def test_no_tier_means_no_score() -> None:
    assert hvac_score(None, True, 100000, ["d1"]) is None


def test_score_starts_from_tier_points() -> None:
    assert hvac_score("A", False, None, []) == 400
    assert hvac_score("D", False, None, []) == 100


def test_ground_up_adds_fifty() -> None:
    assert hvac_score("B", True, None, []) == 350


def test_d1_variance_adds_forty() -> None:
    assert hvac_score("B", False, None, ["d1"]) == 340


def test_other_d_variance_adds_twenty_five() -> None:
    assert hvac_score("B", False, None, ["d5"]) == 325


def test_d1_outweighs_other_d_variances_listed_with_it() -> None:
    assert hvac_score("B", False, None, ["d5", "d1"]) == 340


def test_c_variances_add_two_each() -> None:
    assert hvac_score("B", False, None, ["c", "c"]) == 304


def test_c_variance_bonus_is_capped_at_ten() -> None:
    assert hvac_score("B", False, None, ["c"] * 11) == 310


def test_square_footage_adds_one_per_five_thousand() -> None:
    assert hvac_score("B", False, 25000, []) == 305


def test_square_footage_bonus_is_capped_at_twenty() -> None:
    assert hvac_score("B", False, 1_000_000, []) == 320


def test_variance_codes_are_case_and_whitespace_insensitive() -> None:
    assert hvac_score("B", False, None, [" D1 "]) == 340


def test_ground_up_mixed_use_with_eleven_c_variances_scores_352() -> None:
    """CPB-25-111 (760-766 Clinton Avenue), the MILESTONES M4 acceptance case.

    Extraction lists each variance code once, so 11 'c' variances arrive as ["c"].
    """
    tier = hvac_tier("mixed_use", None)

    assert hvac_score(tier, True, None, ["c"]) == 352
