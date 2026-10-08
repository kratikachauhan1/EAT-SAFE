import pytest
from app import create_app
from app.database import init_db
from app.services.ingredient_resolver import IngredientResolver, get_ingredient_resolver
from app.services.llm_service import IngredientUnderstandingService, get_ingredient_understanding_service


@pytest.fixture
def app():
    test_app = create_app({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'ENVIRONMENT': 'development'
    })
    with test_app.app_context():
        init_db()
    yield test_app


def test_resolver_direct_aliases(app):
    """Test resolving common Indian and international allergen aliases."""
    with app.app_context():
        resolver = get_ingredient_resolver()
        resolver.refresh()

        # Peanut aliases
        res = resolver.resolve_term("mungfali")
        assert res is not None
        assert res['category_code'] == 'PEANUT'
        assert res['canonical_name'] == 'Peanut'

        # Tree nut aliases
        res_kaju = resolver.resolve_term("kaju")
        assert res_kaju is not None
        assert res_kaju['category_code'] == 'TREENUT'

        res_badam = resolver.resolve_term("badam")
        assert res_badam is not None
        assert res_badam['category_code'] == 'TREENUT'


def test_resolver_derivative_relationships(app):
    """Test hierarchical derivative relationships (e.g., Whey -> Milk)."""
    with app.app_context():
        resolver = get_ingredient_resolver()
        resolver.refresh()

        # Whey -> Milk & Dairy
        res_whey = resolver.resolve_term("whey")
        assert res_whey is not None
        assert res_whey['category_code'] == 'MILK'
        assert 'Milk' in res_whey['canonical_name']

        # Ovalbumin -> Egg
        res_egg = resolver.resolve_term("ovalbumin")
        assert res_egg is not None
        assert res_egg['category_code'] == 'EGG'


def test_resolver_full_label_text(app):
    """Test scanning a complex food label with explicit and precautionary warnings."""
    with app.app_context():
        resolver = get_ingredient_resolver()
        label_text = (
            "Ingredients: refined wheat flour (maida), sugar, milk solids, cocoa butter, "
            "emulsifier (soy lecithin). May contain traces of tree nuts and peanuts."
        )
        matches = resolver.resolve_text(label_text)
        assert len(matches) > 0

        categories = {m['category_code'] for m in matches}
        assert 'GLUTEN' in categories
        assert 'MILK' in categories
        assert 'SOY' in categories
        assert 'TREENUT' in categories or 'PEANUT' in categories

        # Precautionary check
        precautionary = [m for m in matches if m['statement_type'] == 'precautionary']
        assert len(precautionary) > 0
        precautionary_cats = {p['category_code'] for p in precautionary}
        assert 'TREENUT' in precautionary_cats or 'PEANUT' in precautionary_cats


def test_llm_service_deterministic_fallback(app):
    """Ensure LLM service works cleanly with 100% deterministic fallback without API key."""
    with app.app_context():
        llm_svc = IngredientUnderstandingService(api_key=None)
        assert not llm_svc.is_configured

        # Test extraction of ingredients with E-numbers
        raw = "Ingredients: sugar, modified starch, E322, E220"
        extracted = llm_svc.extract_structured_ingredients(raw)
        assert len(extracted) > 0

        e322_item = next((item for item in extracted if 'e322' in item['raw'].lower()), None)
        assert e322_item is not None
        assert e322_item['category_code'] == 'SOY'
        assert e322_item['normalized'] == 'lecithin'

        e220_item = next((item for item in extracted if 'e220' in item['raw'].lower()), None)
        assert e220_item is not None
        assert e220_item['category_code'] == 'SULFITES'


def test_llm_grounding_safety_principle(app):
    """Test that candidate outputs from LLM are strictly grounded against the knowledge base."""
    with app.app_context():
        llm_svc = IngredientUnderstandingService(api_key=None)
        
        # Simulate candidates that an LLM might return
        mock_candidates = [
            {"raw": "caseinate", "normalized": "casein", "canonical_entity": "Milk", "confidence": 0.98},
            {"raw": "unknown artificial dye 42", "normalized": "color 42", "canonical_entity": "Unknown", "confidence": 0.5}
        ]

        grounded = llm_svc._verify_and_ground_candidates(mock_candidates, "sample text")
        assert len(grounded) == 2

        # Caseinate must be verified and grounded to MILK
        casein_result = grounded[0]
        assert casein_result['category_code'] == 'MILK'
        assert casein_result['source'] == 'hybrid_llm_verified'

        # Unknown dye must NOT be given a false allergen category
        dye_result = grounded[1]
        assert dye_result['category_code'] is None
        assert dye_result['source'] == 'llm_unverified'
