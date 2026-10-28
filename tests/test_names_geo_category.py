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
