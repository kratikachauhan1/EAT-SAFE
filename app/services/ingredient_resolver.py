import os
import re
import json
import logging
from app.nlp import normalize_text, split_into_sections, extract_phrases
from app.database import get_db, close_connection, is_postgres

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    import difflib
    HAS_RAPIDFUZZ = False

logger = logging.getLogger('eatsafe')
KB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'allergen_kb.json')


def fuzzy_match_ratio(str1, str2):
    """Compute fuzzy similarity ratio between 0 and 100."""
    if HAS_RAPIDFUZZ:
        return fuzz.ratio(str1, str2)
    return difflib.SequenceMatcher(None, str1, str2).ratio() * 100.0


class IngredientResolver:
    """
    Dynamic Relational Ingredient Knowledge Resolver.
    Resolves raw label tokens/phrases to canonical ingredient entities,
    hierarchical relationships (derived_from, contains), and FSSAI/FDA allergen categories.
    """

    def __init__(self):
        self._aliases_map = {}        # { alias_name_lower: { ingredient_id, canonical_name, category_code, category_name } }
        self._canonical_map = {}      # { canonical_name_lower: { ingredient_id, canonical_name, category_code, category_name } }
        self._relationships = []      # [ { parent_name, parent_cat, child_name, child_id, rel_type, confidence } ]
        self._categories_by_code = {} # { category_code: category_name }
        self._loaded = False
        self.load_knowledge_graph()

    def load_knowledge_graph(self):
        """Load relational taxonomy from database with fallback to allergen_kb.json."""
        loaded_from_db = False
        try:
            conn = get_db()
            cursor = conn.cursor()
            
            # 1. Load Allergen Categories
            cursor.execute("SELECT category_code, category_name FROM allergens")
            for row in cursor.fetchall():
                c_code = row['category_code'] if isinstance(row, dict) or hasattr(row, '__getitem__') else row[0]
                c_name = row['category_name'] if isinstance(row, dict) or hasattr(row, '__getitem__') else row[1]
                self._categories_by_code[c_code] = c_name

            # 2. Load Canonical Ingredients
            cursor.execute("SELECT ingredient_id, canonical_name, category_code FROM ingredients")
            ing_rows = cursor.fetchall()
            if ing_rows:
                for row in ing_rows:
                    i_id = row['ingredient_id'] if isinstance(row, dict) or hasattr(row, '__getitem__') else row[0]
                    c_name = row['canonical_name'] if isinstance(row, dict) or hasattr(row, '__getitem__') else row[1]
                    cat_code = row['category_code'] if isinstance(row, dict) or hasattr(row, '__getitem__') else row[2]
                    cat_name = self._categories_by_code.get(cat_code, c_name)

                    entry = {
                        'ingredient_id': i_id,
                        'canonical_name': c_name,
                        'category_code': cat_code,
                        'category_name': cat_name
                    }
                    self._canonical_map[c_name.lower().strip()] = entry

                # 3. Load Aliases
                cursor.execute("""
                    SELECT a.alias_name, i.ingredient_id, i.canonical_name, i.category_code
                    FROM ingredient_aliases a
                    JOIN ingredients i ON a.ingredient_id = i.ingredient_id
                """)
                for row in cursor.fetchall():
                    alias = row['alias_name'] if isinstance(row, dict) or hasattr(row, '__getitem__') else row[0]
                    i_id = row['ingredient_id'] if isinstance(row, dict) or hasattr(row, '__getitem__') else row[1]
                    c_name = row['canonical_name'] if isinstance(row, dict) or hasattr(row, '__getitem__') else row[2]
                    cat_code = row['category_code'] if isinstance(row, dict) or hasattr(row, '__getitem__') else row[3]
                    cat_name = self._categories_by_code.get(cat_code, c_name)

                    self._aliases_map[alias.lower().strip()] = {
                        'ingredient_id': i_id,
                        'canonical_name': c_name,
                        'category_code': cat_code,
                        'category_name': cat_name
                    }

                # 4. Load Relationships
                cursor.execute("""
                    SELECT p.canonical_name as parent_name, p.category_code as parent_cat,
                           c.canonical_name as child_name, c.ingredient_id as child_id,
                           r.relationship_type, r.confidence
                    FROM ingredient_relationships r
                    JOIN ingredients p ON r.parent_ingredient_id = p.ingredient_id
                    JOIN ingredients c ON r.child_ingredient_id = c.ingredient_id
                """)
                for row in cursor.fetchall():
                    self._relationships.append({
                        'parent_name': row['parent_name'] if isinstance(row, dict) or hasattr(row, '__getitem__') else row[0],
                        'parent_cat': row['parent_cat'] if isinstance(row, dict) or hasattr(row, '__getitem__') else row[1],
                        'child_name': row['child_name'] if isinstance(row, dict) or hasattr(row, '__getitem__') else row[2],
                        'child_id': row['child_id'] if isinstance(row, dict) or hasattr(row, '__getitem__') else row[3],
                        'relationship_type': row['relationship_type'] if isinstance(row, dict) or hasattr(row, '__getitem__') else row[4],
                        'confidence': float(row['confidence'] if isinstance(row, dict) or hasattr(row, '__getitem__') else row[5])
                    })

                loaded_from_db = True
            close_connection(conn)
        except Exception as e:
            logger.debug(f"Database knowledge graph fetch unavailable ({e}), using JSON fallback.")

        # Fallback to allergen_kb.json if DB tables were empty or offline
        if not loaded_from_db and os.path.exists(KB_PATH):
            try:
                with open(KB_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for cat in data.get('categories', []):
                    code = cat['code']
                    name = cat['name']
                    self._categories_by_code[code] = name
                    self._canonical_map[name.lower().strip()] = {
                        'ingredient_id': None,
                        'canonical_name': name,
                        'category_code': code,
                        'category_name': name
                    }
                    for term in cat.get('terms', []):
                        self._aliases_map[term.lower().strip()] = {
                            'ingredient_id': None,
                            'canonical_name': name,
                            'category_code': code,
                            'category_name': name
                        }
            except Exception as e:
                logger.error(f"Failed to load KB JSON: {e}")

        self._loaded = True

    def refresh(self):
        """Force reloading the knowledge graph."""
        self._aliases_map.clear()
        self._canonical_map.clear()
        self._relationships.clear()
        self._categories_by_code.clear()
        self.load_knowledge_graph()

    def resolve_term(self, term):
        """
        Resolve a single normalized term/phrase to canonical ingredient & category.
        Returns matching metadata dict or None if unresolved.
        """
        if not term:
            return None
        norm_term = term.lower().strip()

        # 1. Check exact alias map
        if norm_term in self._aliases_map:
            match = self._aliases_map[norm_term]
            return {
                'matched_term': norm_term,
                'canonical_name': match['canonical_name'],
                'category_code': match['category_code'],
                'category_name': match['category_name'],
                'match_method': 'exact_alias',
                'relationship': None,
                'confidence': 1.0
            }

        # 2. Check canonical entities
        if norm_term in self._canonical_map:
            match = self._canonical_map[norm_term]
            return {
                'matched_term': norm_term,
                'canonical_name': match['canonical_name'],
                'category_code': match['category_code'],
                'category_name': match['category_name'],
                'match_method': 'exact_canonical',
                'relationship': None,
                'confidence': 1.0
            }

        # 3. Check derivative relationships (e.g. child -> parent)
        for rel in self._relationships:
            if norm_term == rel['child_name'].lower().strip():
                return {
                    'matched_term': norm_term,
                    'canonical_name': rel['parent_name'],
                    'category_code': rel['parent_cat'],
                    'category_name': self._categories_by_code.get(rel['parent_cat'], rel['parent_name']),
                    'match_method': 'derivative_relationship',
                    'relationship': {
                        'type': rel['relationship_type'],
                        'child': rel['child_name'],
                        'parent': rel['parent_name']
                    },
                    'confidence': rel['confidence']
                }

        return None

    def resolve_text(self, raw_text):
        """
        Analyze full raw food label text. Splits into explicit & precautionary
        sections, scans against all aliases, entities, and relationships,
        and applies fuzzy matching for OCR typos.
        """
        if not raw_text:
            return []

        sections = split_into_sections(raw_text)
        explicit_text = sections.get('explicit_text', '')
        precautionary_text = sections.get('precautionary_text', '')

        explicit_phrases = extract_phrases(explicit_text)
        precautionary_phrases = extract_phrases(precautionary_text)

        detected_items = []
        seen_matches = set() # (category_code, statement_type, term)

        # Build list of terms sorted by length descending so longer phrases match first
        all_terms = sorted(self._aliases_map.keys(), key=len, reverse=True)

        def scan_section(phrases, full_section_text, statement_type):
            if not full_section_text:
                return

            exact_matched_words = set()

            # 1. Regex Exact/Boundary Scanning for known aliases
            for term in all_terms:
                if len(term) < 2:
                    continue
                pattern = r'\b' + re.escape(term) + r'\b'
                match = re.search(pattern, full_section_text)
                if match:
                    alias_info = self._aliases_map[term]
                    cat_code = alias_info['category_code']
                    cat_name = alias_info['category_name']
                    key = (cat_code, statement_type, term)

                    if key not in seen_matches:
                        seen_matches.add(key)
                        for w in term.split():
                            exact_matched_words.add(re.sub(r'[^a-z]', '', w))

                        start = max(0, match.start() - 25)
                        end = min(len(full_section_text), match.end() + 25)
                        snippet = full_section_text[start:end].strip()

                        # Check if this term corresponds to a derivative relationship
                        rel_info = None
                        canonical_target = alias_info['canonical_name']
                        for rel in self._relationships:
                            if term == rel['child_name'].lower().strip():
                                rel_info = {
                                    'type': rel['relationship_type'],
                                    'child': rel['child_name'],
                                    'parent': rel['parent_name']
                                }
                                break

                        detected_items.append({
                            'category_code': cat_code,
                            'category_name': cat_name,
                            'matched_term': term,
                            'canonical_name': canonical_target,
                            'evidence_text': snippet,
                            'statement_type': statement_type,
                            'match_method': 'exact',
                            'relationship': rel_info,
                            'confidence': 1.0
                        })

            # 2. Fuzzy Matching against extracted phrases for OCR degradation
            for term in all_terms:
                if len(term) < 4:
                    continue
                alias_info = self._aliases_map[term]
                cat_code = alias_info['category_code']
                cat_name = alias_info['category_name']

                for phrase in phrases:
                    words = phrase.split()
                    for word in words:
                        clean_w = re.sub(r'[^a-z]', '', word)
                        if clean_w in exact_matched_words:
                            continue
                        if len(clean_w) >= 4 and abs(len(clean_w) - len(term)) <= 2:
                            ratio = fuzzy_match_ratio(clean_w, term)
                            if ratio >= 85.0:
                                key = (cat_code, statement_type, term)
                                if key not in seen_matches:
                                    seen_matches.add(key)
                                    idx = full_section_text.find(word)
                                    start = max(0, idx - 20) if idx != -1 else 0
                                    end = min(len(full_section_text), idx + len(word) + 20) if idx != -1 else len(full_section_text)
                                    snippet = full_section_text[start:end].strip()

                                    detected_items.append({
                                        'category_code': cat_code,
                                        'category_name': cat_name,
                                        'matched_term': f"{term} (fuzzy match from '{clean_w}')",
                                        'canonical_name': alias_info['canonical_name'],
                                        'evidence_text': snippet,
                                        'statement_type': statement_type,
                                        'match_method': 'fuzzy',
                                        'relationship': None,
                                        'confidence': round(ratio / 100.0, 2)
                                    })

        # Process explicit section first, then precautionary
        scan_section(explicit_phrases, explicit_text, 'explicit')
        if precautionary_text:
            scan_section(precautionary_phrases, precautionary_text, 'precautionary')

        return detected_items


# Global singleton instance
_resolver_instance = None

def get_ingredient_resolver():
    """Retrieve or initialize the global IngredientResolver singleton."""
    global _resolver_instance
    if _resolver_instance is None:
        _resolver_instance = IngredientResolver()
    return _resolver_instance
