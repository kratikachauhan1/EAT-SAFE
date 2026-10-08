import os
import re
import json
import logging
import requests
from app.nlp import normalize_text, split_into_sections, extract_phrases
from app.services.ingredient_resolver import get_ingredient_resolver

logger = logging.getLogger('eatsafe')

# Common E-number and food additive deterministic mappings
DETERMINISTIC_ADDITIVES = {
    'e322': {'normalized': 'lecithin', 'canonical_entity': 'Soy', 'category_code': 'SOY', 'confidence': 0.9},
    'e1105': {'normalized': 'lysozyme', 'canonical_entity': 'Egg', 'category_code': 'EGG', 'confidence': 0.95},
    'e220': {'normalized': 'sulfur dioxide', 'canonical_entity': 'Sulfites', 'category_code': 'SULFITES', 'confidence': 0.95},
    'e221': {'normalized': 'sodium sulfite', 'canonical_entity': 'Sulfites', 'category_code': 'SULFITES', 'confidence': 0.95},
    'e222': {'normalized': 'sodium bisulfite', 'canonical_entity': 'Sulfites', 'category_code': 'SULFITES', 'confidence': 0.95},
    'e223': {'normalized': 'sodium metabisulfite', 'canonical_entity': 'Sulfites', 'category_code': 'SULFITES', 'confidence': 0.95},
    'e224': {'normalized': 'potassium metabisulfite', 'canonical_entity': 'Sulfites', 'category_code': 'SULFITES', 'confidence': 0.95},
    'e226': {'normalized': 'calcium sulfite', 'canonical_entity': 'Sulfites', 'category_code': 'SULFITES', 'confidence': 0.95},
    'e227': {'normalized': 'calcium hydrogen sulfite', 'canonical_entity': 'Sulfites', 'category_code': 'SULFITES', 'confidence': 0.95},
    'e228': {'normalized': 'potassium hydrogen sulfite', 'canonical_entity': 'Sulfites', 'category_code': 'SULFITES', 'confidence': 0.95},
}


class IngredientUnderstandingService:
    """
    Hybrid Ingredient Understanding Service.
    Combines structured LLM parsing (Gemini) with deterministic NLP and
    relational knowledge verification.
    
    SAFETY RULE: The LLM is strictly an extraction & normalization helper.
    All safety/allergen evaluations remain 100% deterministic against the database knowledge base.
    """

    def __init__(self, api_key=None, model=None, timeout=6.0):
        self.api_key = api_key or os.environ.get('GEMINI_API_KEY', os.environ.get('LLM_API_KEY', '')).strip()
        self.model = model or os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash')
        self.timeout = timeout
        self.resolver = get_ingredient_resolver()

    @property
    def is_configured(self):
        """Returns True if a valid API key is present."""
        return bool(self.api_key)

    def extract_structured_ingredients(self, raw_text):
        """
        Extract and normalize ingredients from raw label text.
        If LLM is configured, queries structured JSON parsing from Gemini.
        Otherwise falls back to deterministic extraction.
        """
        if not raw_text or not raw_text.strip():
            return []

        if self.is_configured:
            try:
                llm_results = self._call_llm_extraction(raw_text)
                if llm_results:
                    return self._verify_and_ground_candidates(llm_results, raw_text)
            except Exception as e:
                logger.warning(f"LLM extraction call failed ({e}). Falling back to deterministic NLP.")

        return self._deterministic_extraction(raw_text)

    def _call_llm_extraction(self, raw_text):
        """Call Gemini REST API for structured ingredient token parsing."""
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        
        system_instruction = (
            "You are a food ingredient text extraction assistant. "
            "Given a raw food ingredient label, extract all distinct ingredients, chemical additives, and E-numbers. "
            "Output valid JSON ONLY as an array of objects with keys: "
            "'raw' (exact substring), 'normalized' (clean common name), "
            "'canonical_entity' (parent source food e.g. Milk, Peanut, Soy, Wheat, Egg, etc. or 'None'), "
            "'relationship' ('derived_from' or 'direct' or 'none'), "
            "'confidence' (float between 0.0 and 1.0). "
            "Do NOT output markdown or explanations."
        )

        prompt = f"Label Text:\n{raw_text}\n\nJSON array:"

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"{system_instruction}\n\n{prompt}"}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 1024,
                "responseMimeType": "application/json"
            }
        }

        resp = requests.post(
            endpoint,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=self.timeout
        )

        if resp.status_code == 200:
            data = resp.json()
            candidates = data.get('candidates', [])
            if candidates and 'content' in candidates[0]:
                parts = candidates[0]['content'].get('parts', [])
                if parts and 'text' in parts[0]:
                    json_str = parts[0]['text'].strip()
                    # Clean markdown fence if present
                    if json_str.startswith("```"):
                        json_str = re.sub(r"^```(?:json)?", "", json_str).rstrip("`").strip()
                    parsed = json.loads(json_str)
                    if isinstance(parsed, list):
                        return parsed
        else:
            logger.warning(f"Gemini API returned status code {resp.status_code}: {resp.text[:200]}")

        return None

    def _verify_and_ground_candidates(self, candidates, full_text):
        """
        Ground all LLM candidates deterministically against the knowledge base.
        Never trust an ungrounded LLM output directly.
        """
        grounded = []
        for item in candidates:
            raw = item.get('raw', '').strip()
            norm = item.get('normalized', '').strip()
            if not norm and not raw:
                continue

            # Ground against deterministic IngredientResolver
            resolved = self.resolver.resolve_term(norm) or self.resolver.resolve_term(raw)
            if resolved:
                grounded.append({
                    'raw': raw or norm,
                    'normalized': norm or raw,
                    'canonical_entity': resolved['canonical_name'],
                    'category_code': resolved['category_code'],
                    'relationship': resolved.get('relationship'),
                    'confidence': min(float(item.get('confidence', 0.95)), resolved['confidence']),
                    'source': 'hybrid_llm_verified'
                })
            else:
                grounded.append({
                    'raw': raw or norm,
                    'normalized': norm or raw,
                    'canonical_entity': item.get('canonical_entity', 'Unknown'),
                    'category_code': None,
                    'relationship': item.get('relationship'),
                    'confidence': float(item.get('confidence', 0.5)),
                    'source': 'llm_unverified'
                })
        return grounded

    def _deterministic_extraction(self, raw_text):
        """100% deterministic rule-based ingredient extraction and additive mapping."""
        norm_text = normalize_text(raw_text)
        phrases = extract_phrases(norm_text)
        results = []

        for phrase in phrases:
            clean_phrase = phrase.strip().lower()
            if len(clean_phrase) < 2:
                continue

            # Check E-number match
            e_match = re.search(r'\b(e\s*[-]?\s*\d{3,4}[a-z]?)\b', clean_phrase)
            if e_match:
                e_clean = re.sub(r'[\s\-]', '', e_match.group(1)).lower()
                if e_clean in DETERMINISTIC_ADDITIVES:
                    add_info = DETERMINISTIC_ADDITIVES[e_clean]
                    results.append({
                        'raw': phrase,
                        'normalized': add_info['normalized'],
                        'canonical_entity': add_info['canonical_entity'],
                        'category_code': add_info['category_code'],
                        'relationship': {'type': 'contains_additive', 'additive': e_clean},
                        'confidence': add_info['confidence'],
                        'source': 'deterministic_e_number'
                    })
                    continue

            # Check resolver
            resolved = self.resolver.resolve_term(clean_phrase)
            if resolved:
                results.append({
                    'raw': phrase,
                    'normalized': resolved['matched_term'],
                    'canonical_entity': resolved['canonical_name'],
                    'category_code': resolved['category_code'],
                    'relationship': resolved.get('relationship'),
                    'confidence': resolved['confidence'],
                    'source': 'deterministic_knowledge_base'
                })
            else:
                results.append({
                    'raw': phrase,
                    'normalized': clean_phrase,
                    'canonical_entity': 'Unknown',
                    'category_code': None,
                    'relationship': None,
                    'confidence': 1.0,
                    'source': 'deterministic_raw'
                })

        return results


# Global singleton instance
_llm_service = None

def get_ingredient_understanding_service():
    """Retrieve or initialize the global IngredientUnderstandingService singleton."""
    global _llm_service
    if _llm_service is None:
        _llm_service = IngredientUnderstandingService()
    return _llm_service
