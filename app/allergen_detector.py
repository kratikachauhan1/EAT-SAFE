import os
import json
import re

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    import difflib
    HAS_RAPIDFUZZ = False

from app.nlp import normalize_text, split_into_sections, extract_phrases

KB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'allergen_kb.json')

_KB_CACHE = None

def load_allergen_kb():
    global _KB_CACHE
    if _KB_CACHE is None:
        if os.path.exists(KB_PATH):
            with open(KB_PATH, 'r', encoding='utf-8') as f:
                _KB_CACHE = json.load(f)
        else:
            _KB_CACHE = {"categories": []}
    return _KB_CACHE


def fuzzy_match_ratio(str1, str2):
    """Compute fuzzy match ratio between 0 and 100."""
    if HAS_RAPIDFUZZ:
        return fuzz.ratio(str1, str2)
    else:
        return difflib.SequenceMatcher(None, str1, str2).ratio() * 100.0


def detect_allergens_in_text(raw_text):
    """
    Detect allergens in raw OCR text.
    Returns a list of dicts:
    [
        {
            'category_code': 'MILK',
            'category_name': 'Milk',
            'matched_term': 'milk solids',
            'evidence_text': 'ingredients: wheat flour, milk solids...',
            'statement_type': 'explicit', # or 'precautionary'
            'match_method': 'exact', # or 'fuzzy'
            'confidence': 1.0
        }
    ]
    """
    kb = load_allergen_kb()
    categories = kb.get('categories', [])
    
    sections = split_into_sections(raw_text)
    explicit_text = sections['explicit_text']
    precautionary_text = sections['precautionary_text']
    
    explicit_phrases = extract_phrases(explicit_text)
    precautionary_phrases = extract_phrases(precautionary_text)

    detected_items = []
    seen_matches = set() # Avoid duplicate (category_code, statement_type, matched_term)

    def process_section(phrases, full_section_text, statement_type):
        for category in categories:
            cat_code = category['code']
            cat_name = category['name']
            terms = category.get('terms', [])

            for term in terms:
                norm_term = term.lower().strip()
                pattern = r'\b' + re.escape(norm_term) + r'\b'

                # 1. Exact phrase / Regex match in section text
                if re.search(pattern, full_section_text):
                    key = (cat_code, statement_type, norm_term)
                    if key not in seen_matches:
                        seen_matches.add(key)
                        
                        # Find snippet context
                        match_obj = re.search(pattern, full_section_text)
                        start = max(0, match_obj.start() - 20)
                        end = min(len(full_section_text), match_obj.end() + 20)
                        snippet = full_section_text[start:end].strip()

                        detected_items.append({
                            'category_code': cat_code,
                            'category_name': cat_name,
                            'matched_term': norm_term,
                            'evidence_text': snippet,
                            'statement_type': statement_type,
                            'match_method': 'exact',
                            'confidence': 1.0
                        })
                        continue

                # 2. Fuzzy match against extracted phrase tokens if term length >= 4
                if len(norm_term) >= 4:
                    for phrase in phrases:
                        words = phrase.split()
                        for word in words:
                            clean_w = re.sub(r'[^a-z]', '', word)
                            if len(clean_w) >= 4 and abs(len(clean_w) - len(norm_term)) <= 2:
                                ratio = fuzzy_match_ratio(clean_w, norm_term)
                                if ratio >= 85.0:
                                    key = (cat_code, statement_type, norm_term)
                                    if key not in seen_matches:
                                        seen_matches.add(key)
                                        
                                        idx = full_section_text.find(word)
                                        start = max(0, idx - 20) if idx != -1 else 0
                                        end = min(len(full_section_text), idx + len(word) + 20) if idx != -1 else len(full_section_text)
                                        snippet = full_section_text[start:end].strip()

                                        detected_items.append({
                                            'category_code': cat_code,
                                            'category_name': cat_name,
                                            'matched_term': f"{norm_term} (fuzzy match from '{clean_w}')",
                                            'evidence_text': snippet,
                                            'statement_type': statement_type,
                                            'match_method': 'fuzzy',
                                            'confidence': round(ratio / 100.0, 2)
                                        })

    # Process explicit section first
    process_section(explicit_phrases, explicit_text, 'explicit')
    # Process precautionary section
    if precautionary_text:
        process_section(precautionary_phrases, precautionary_text, 'precautionary')

    return detected_items
