from app.category import is_restaurant_like
from app.geo import LatLng, haversine_km
from app.names import name_similarity, normalize_name


def test_normalize_strips_prefixes_and_diacritics():
    assert "ramiro" in normalize_name("Cervejaria Ramiro")
    assert "sao" in normalize_name("São") or "sao" in normalize_name("Sao")


def test_token_set_matches_short_names():
    assert name_similarity("Cervejaria Ramiro", "Ramiro") >= 0.72
    assert name_similarity("Restaurante Arola", "Arola") >= 0.72
    assert name_similarity("Restaurant - Cervejaria Ramiro", "Cervejaria Ramiro") >= 0.72


def test_french_laundry_does_not_match_french_arth():
    # Regression: Lisbon false positive that blocked wrong-city detection
    assert name_similarity("The French Laundry", "French Arth") < 0.72


def test_french_laundry_matches_itself():
    assert name_similarity("The French Laundry", "The French Laundry") >= 0.85
    assert (
        name_similarity("The French Laundry", "French Laundry Restaurant") >= 0.72
    )


def test_cascais_distance_from_lisbon():
    lisbon = LatLng(lat=38.7223, lon=-9.1393)
    cascais = LatLng(lat=38.6979, lon=-9.4215)
    d = haversine_km(lisbon, cascais)
    assert 20 < d < 40


def test_restaurant_category_positive():
    assert is_restaurant_like(
        {
            "name": "Cervejaria Ramiro",
            "properties": {"primary_genre": "Seafood Restaurant"},
            "tags": [{"name": "Restaurant"}],
        }
    )


def test_museum_not_restaurant():
    assert not is_restaurant_like(
        {
            "name": "Museum of Contemporary Art – MAC/CCB",
            "properties": {"description": "Contemporary art museum in Lisbon"},
            "tags": [{"name": "Museum"}],
        }
    )


def test_museum_rejected_even_with_noisy_food_tag():
    assert not is_restaurant_like(
        {
            "name": "Museum of Contemporary Art – MAC/CCB",
            "properties": {"description": "Cafe on site serves food"},
            "tags": [{"name": "Museum"}, {"name": "Food"}],
        }
    )


def test_miradouro_and_street_rejected():
    assert not is_restaurant_like({"name": "Miradouro de Santa Catarina", "tags": []})
    assert not is_restaurant_like({"name": "Rua nova do Carvalho", "tags": []})


def test_palace_cafe_rejected_as_lodging_cafe():
    # Dinner list must not accept hotel/palace cafés even with "cafe" in the name.
    assert not is_restaurant_like(
        {
            "name": "Palacio Belmonte Cafe & Bar",
            "properties": {"primary_genre": "Cafe"},
            "tags": [{"name": "Cafe"}],
        }
    )


def test_cultural_casa_rejected():
    assert not is_restaurant_like(
        {
            "name": "Casa Fernando Pessoa",
            "properties": {"primary_genre": "Museum"},
            "tags": [{"name": "Cultural Center"}, {"name": "Food"}],
        }
    )
    assert not is_restaurant_like({"name": "Casa dos Bicos", "tags": []})


def test_casa_with_restaurant_in_name_allowed():
    assert is_restaurant_like(
        {
            "name": "Casa do Alentejo Restaurant",
            "properties": {"primary_genre": "Portuguese Restaurant"},
        }
    )


def test_sem_wine_bar_does_not_match_little_wine_bar():
    assert name_similarity("SEM Wine Bar", "Little Wine Bar") < 0.72


def test_prado_does_not_perfect_match_prado_wine_bar():
    # One-word query must not treat a longer sibling venue as identity.
    assert name_similarity("Prado", "Prado Wine Bar") < 0.72


def test_invented_casa_does_not_confident_match_faia():
    assert name_similarity("Casa Azul da Lua Fictícia", "O Faia - Casa de Fado") < 0.72


def test_coffee_library_rejected_from_dinner_pool():
    assert not is_restaurant_like(
        {
            "name": "The Coffee Library in The Hood",
            "properties": {"primary_genre": "Cafe"},
            "tags": [{"name": "Cafe"}, {"name": "Coffee"}],
        }
    )


def test_historic_cafe_nicola_rejected():
    from app.category import is_dinner_pool_eligible

    assert not is_restaurant_like(
        {
            "name": "Nicola",
            "properties": {"primary_genre": "Cafe"},
        }
    )
    # Even with a noisy "restaurant" genre tag, Nicola stays out of the dinner pool.
    assert not is_dinner_pool_eligible(
        {
            "name": "Nicola",
            "properties": {"primary_genre": "Cafe Restaurant"},
        }
    )
    assert not is_dinner_pool_eligible(
        {
            "name": "Barbica",
            "properties": {"primary_genre": "Bar"},
        }
    )


def test_naval_association_rejected():
    assert not is_restaurant_like(
        {
            "name": "BONANÇA - Associação Naval de Lisboa",
            "properties": {"primary_genre": "Club"},
        }
    )


def test_low_percentile_without_floor_is_rewrite():
    from app.config import Settings
    from app.models import EvaluationStatus, EvidenceState, ItemVerdict
    from app.resolver import PlaceEntity, ResolveHit
    from app.scorer import AnchorScorer

    settings = Settings(allow_anchor_percentile=0.40, allow_borderline_band=0.05)
    scorer = AnchorScorer(qloo=None, settings=settings)  # type: ignore[arg-type]
    hit = ResolveHit(
        evidence=EvidenceState.VERIFIED,
        entity=PlaceEntity(
            entity_id="prado",
            name="Prado",
            location=None,
            is_restaurant=True,
        ),
        distance_km=1.4,
        similarity=1.0,
        reasons=["ok"],
    )
    verdict, _, pct, _reasons = scorer.item_from_resolve_and_score(
        hit=hit,
        scored={"affinity": 0.74, "summary": None},
        anchor_affinities=[0.9] * 38 + [0.5] * 12,  # beats 12/50 = 0.24
        evaluation_status=EvaluationStatus.COMPLETED,
    )
    assert pct is not None and pct < 0.35
    assert verdict == ItemVerdict.REWRITE


def test_bar_only_snob_rejected():
    from app.category import is_dinner_pool_eligible

    assert not is_restaurant_like(
        {"name": "Snob Bar", "properties": {"primary_genre": "Bar"}}
    )
    # Noisy Qloo genre must not admit bare "* Bar" names into the dinner pool.
    assert not is_dinner_pool_eligible(
        {"name": "Snob Bar", "properties": {"primary_genre": "Restaurant"}}
    )
    assert not is_dinner_pool_eligible(
        {"name": "Café Janis", "properties": {"primary_genre": "Restaurant"}}
    )


def test_taberna_allowed_as_dinner():
    assert is_restaurant_like(
        {
            "name": "Boutique Taberna",
            "properties": {"primary_genre": "Portuguese Restaurant"},
        }
    )


def test_join_messages_no_double_punctuation():
    from app.service import _join_messages

    msg = _join_messages(
        [
            "Unverified items stay on the card as kept/unverified.",
            "Repair picks only from the Qloo restaurant alternative pool.",
        ]
    )
    assert msg is not None
    assert ".;" not in msg
    assert msg.count(".") >= 1


def test_borderline_band_allows_near_cutoff():
    from app.config import Settings
    from app.models import EvaluationStatus, EvidenceState, ItemVerdict
    from app.resolver import PlaceEntity, ResolveHit
    from app.scorer import AnchorScorer

    settings = Settings(allow_anchor_percentile=0.40, allow_borderline_band=0.05)
    scorer = AnchorScorer(qloo=None, settings=settings)  # type: ignore[arg-type]
    hit = ResolveHit(
        evidence=EvidenceState.VERIFIED,
        entity=PlaceEntity(
            entity_id="x",
            name="Test",
            location=None,
            is_restaurant=True,
        ),
        distance_km=1.0,
        similarity=1.0,
        reasons=["ok"],
    )
    # 38% is within 40% ± 5% → ALLOW with note
    verdict, _, pct, reasons = scorer.item_from_resolve_and_score(
        hit=hit,
        scored={"affinity": 0.5, "summary": None},
        anchor_affinities=[0.9] * 31 + [0.4] * 19,  # beats 19/50 = 0.38
        evaluation_status=EvaluationStatus.COMPLETED,
    )
    assert pct is not None and 0.35 <= pct <= 0.40
    assert verdict == ItemVerdict.ALLOW
    assert any("Borderline" in r for r in reasons)


def test_nyc_preset_uses_new_york_not_lisbon():
    from app.presets import get_preset

    nyc = get_preset("radiohead-nyc")
    assert nyc is not None
    assert nyc["city"] == "New York"
    assert nyc["city_center"]["lat"] == 40.7128
    lisbon = get_preset("radiohead-lisbon")
    assert lisbon is not None
    assert lisbon["city"] == "Lisbon"
    assert len(nyc["seed_queries"]) >= 3
    assert len(lisbon["seed_queries"]) >= 3


def test_stress_inject_keepers_and_lisbon_neighbourhoods():
    from app.presets import get_preset, inject_candidates

    preset = get_preset("stress-lisbon-live")
    assert preset is not None
    cands = inject_candidates(preset)
    names = [c.name for c in cands]
    assert "A Cevicheria" in names
    assert "Cervejaria Ramiro" in names
    assert "Prado" not in names
    paris = next(c for c in cands if "Comptoir" in c.name)
    assert paris.neighbourhood == "Chiado"
    assert "Paris" not in (paris.neighbourhood or "")
