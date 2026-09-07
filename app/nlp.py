import re

PRECAUTIONARY_INDICATORS = [
    r'\bmay contain\b',
    r'\bmay contain traces of\b',
    r'\bcontains traces of\b',
    r'\bprocessed in a facility\b',
    r'\bmade in a factory\b',
    r'\bmanufactured in a facility\b',
    r'\bproduced in a facility\b',
    r'\bpacked in a plant\b',
    r'\balso handles\b',
    r'\bmay also contain\b',
    r'\btrace amounts of\b',
    r'\bprecautionary statement\b'
]

EXPLICIT_INDICATORS = [
    r'\bingredients:\b',
    r'\bingredients\b',
    r'\bcontains:\b',
    r'\bcontains\b',
    r'\ballergen info:\b',
    r'\ballergens:\b',
    r'\ballergen declaration\b'
]


def normalize_text(text):
    """Clean and normalize OCR text."""
    if not text:
        return ""
    # Convert to lowercase
    cleaned = text.lower()
    # Replace newlines with spaces
    cleaned = re.sub(r'[\r\n]+', ' ', cleaned)
    # Standardize common OCR mistakes
    ocr_fixes = {
        r'\bconlains\b': 'contains',
        r'\bingredienls\b': 'ingredients',
        r'\bpeanul\b': 'peanut',
        r'\bwhei\b': 'whey',
        r'\bsoya\b': 'soy',
        r'\bmilk-solids\b': 'milk solids',
        r'\bwheal\b': 'wheat',
        r'\balmoncl\b': 'almond'
    }
    for pattern, replacement in ocr_fixes.items():
        cleaned = re.sub(pattern, replacement, cleaned)

    # Clean multiple spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def split_into_sections(text):
    """
    Split clean OCR text into:
    - explicit_text: Ingredients list / direct "Contains" section
    - precautionary_text: "May contain" / "Produced in a facility" section
    """
    normalized = normalize_text(text)
    
    # Check for precautionary phrases
    precautionary_matches = []
    for pattern in PRECAUTIONARY_INDICATORS:
        for match in re.finditer(pattern, normalized):
            precautionary_matches.append(match.start())

    if not precautionary_matches:
        return {
            'explicit_text': normalized,
            'precautionary_text': ''
        }

    # Split at the first precautionary marker found
    split_pos = min(precautionary_matches)
    explicit_part = normalized[:split_pos].strip()
    precautionary_part = normalized[split_pos:].strip()

    return {
        'explicit_text': explicit_part,
        'precautionary_text': precautionary_part
    }


def extract_phrases(text):
    """Extract individual ingredient phrases by splitting on commas, colons, dots, semicolons, brackets."""
    if not text:
        return []
    # Split on punctuation
    raw_phrases = re.split(r'[,:;\.\(\)\[\]\{\}]', text)
    clean_phrases = []
    for p in raw_phrases:
        p_strip = p.strip()
        if len(p_strip) >= 2:
            clean_phrases.append(p_strip)
    return clean_phrases
