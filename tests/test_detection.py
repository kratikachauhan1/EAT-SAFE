import pytest
from app.nlp import normalize_text, split_into_sections, extract_phrases
from app.allergen_detector import detect_allergens_in_text

def test_text_normalization():
    raw_ocr = "INGREDIENTS: Wheat-Flour, Milk-Solids, CONLAINS peanul."
    normalized = normalize_text(raw_ocr)
    assert "wheat" in normalized
    assert "milk solids" in normalized
    assert "contains" in normalized
    assert "peanut" in normalized

def test_split_into_sections():
    raw = "Ingredients: Wheat flour, sugar, milk powder. May contain traces of peanuts and soy."
    sections = split_into_sections(raw)
    
    assert "wheat flour" in sections['explicit_text']
    assert "milk powder" in sections['explicit_text']
    assert "peanuts" in sections['precautionary_text']
    assert "soy" in sections['precautionary_text']

def test_extract_phrases():
    text = "wheat flour, milk solids: cocoa powder; sugar"
    phrases = extract_phrases(text)
    assert "wheat flour" in phrases
    assert "milk solids" in phrases
    assert "cocoa powder" in phrases
    assert "sugar" in phrases

def test_exact_allergen_detection():
    sample_text = "Ingredients: Wheat flour, sugar, milk solids, cocoa powder, soya lecithin."
    results = detect_allergens_in_text(sample_text)
    
    cat_codes = [r['category_code'] for r in results]
    assert "GLUTEN" in cat_codes
    assert "MILK" in cat_codes
    assert "SOY" in cat_codes

def test_precautionary_vs_explicit_detection():
    sample_text = "Ingredients: Wheat flour, sugar, milk powder. May contain peanuts."
    results = detect_allergens_in_text(sample_text)
    
    milk_res = [r for r in results if r['category_code'] == 'MILK'][0]
    peanut_res = [r for r in results if r['category_code'] == 'PEANUT'][0]
    
    assert milk_res['statement_type'] == 'explicit'
    assert peanut_res['statement_type'] == 'precautionary'

def test_fuzzy_match_ocr_typo():
    # Test OCR typo: "peanul" matching PEANUT, "soya" matching SOY
    sample_text = "Ingredients: cocoa, peanul oil, soya lecithin"
    results = detect_allergens_in_text(sample_text)
    
    cat_codes = [r['category_code'] for r in results]
    assert "PEANUT" in cat_codes
    assert "SOY" in cat_codes
