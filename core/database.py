
import json
import os

ITEMS_DB = []

def load_items_db():
    global ITEMS_DB

    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'items.json')
    try:
        with open(db_path, 'r', encoding='utf-8') as f:
            ITEMS_DB = json.load(f)
        print(f"[+] Database loaded: {len(ITEMS_DB)} items available.")
    except FileNotFoundError:
        print(f"[!] WARNING: 'items.json' was not found at {db_path}.")
    except Exception as e:
        print(f"[!] Error reading items.json: {e}")

def search_item(query: str) -> list:
    query_lower = query.lower()
    exact_matches, partial_matches = [], []
    for item in ITEMS_DB:
        name_en = (item.get('name') or "").lower()
        name_es = (item.get('name_es') or "").lower()
        internal = (item.get('internal_name') or "").lower()
        item_id = item.get('id')

        if str(item_id) == query_lower: return [item]
        if query_lower in (name_en, name_es, internal): exact_matches.append(item)
        elif query_lower in name_en or query_lower in name_es or query_lower in internal: partial_matches.append(item)

    return exact_matches if exact_matches else partial_matches
