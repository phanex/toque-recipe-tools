import urllib.request
import re
import json
import time
import os
import sys

# Ensure sources can be imported
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from sources.cookomix import parse_cookomix_html, CANONICAL_CATEGORIES

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

SOURCES = [
    # type-plat (General classifications)
    ("https://www.cookomix.com/recettes/type-plat/plat-principal/", "Основні страви", 3),
    ("https://www.cookomix.com/recettes/type-plat/boisson/", "Напої", 3),
    ("https://www.cookomix.com/recettes/type-plat/aperitif/", "Закуски", 3),
    ("https://www.cookomix.com/recettes/type-plat/entree/", "Закуски", 3),
    ("https://www.cookomix.com/recettes/type-plat/petit-dejeuner/", "Сніданки", 3),
    ("https://www.cookomix.com/recettes/type-plat/accompagnement/", "Гарніри", 3),
    ("https://www.cookomix.com/recettes/type-plat/dessert/", "Десерти", 3),
    # categories (Specific culinary areas)
    ("https://www.cookomix.com/recettes/categories/soupes/", "Супи", 3),
    ("https://www.cookomix.com/recettes/categories/pains/", "Випічка", 3),
    ("https://www.cookomix.com/recettes/categories/patisseries/", "Десерти", 3),
    ("https://www.cookomix.com/recettes/categories/pates/", "Основні страви", 3),
    ("https://www.cookomix.com/recettes/categories/salades/", "Салати", 3),
    ("https://www.cookomix.com/recettes/categories/sauces/", "Соуси та пасти", 3),
    ("https://www.cookomix.com/recettes/categories/confitures/", "Джеми та варення", 3),
    ("https://www.cookomix.com/recettes/categories/viennoiseries/", "Випічка", 3),
    ("https://www.cookomix.com/recettes/categories/purees/", "Гарніри", 2),
    ("https://www.cookomix.com/recettes/categories/quiches/", "Основні страви", 2),
    ("https://www.cookomix.com/recettes/categories/ragout/", "Основні страви", 2),
    ("https://www.cookomix.com/recettes/categories/gratins/", "Основні страви", 2),
    ("https://www.cookomix.com/recettes/categories/riz/", "Основні страви", 2),
    ("https://www.cookomix.com/recettes/categories/glaces/", "Десерти", 2),
    ("https://www.cookomix.com/recettes/categories/flans/", "Десерти", 2),
    ("https://www.cookomix.com/recettes/categories/terrines/", "Закуски", 2),
    ("https://www.cookomix.com/recettes/categories/pizzas/", "Основні страви", 2),
]

def collect_candidate_links(target_min=550):
    print("=== Step 1: Collecting Recipe URLs Across Categories ===")
    all_candidates = []
    seen_links = set()

    for base_url, hint, max_pages in SOURCES:
        for page in range(1, max_pages + 1):
            url = base_url if page == 1 else f"{base_url}page/{page}/"
            try:
                req = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=10) as r:
                    html = r.read().decode("utf-8", errors="ignore")
                links = re.findall(r'href=["\'](https://www.cookomix.com/recettes/[^"/]+-thermomix/)["\']', html)
                added = 0
                for l in links:
                    if l not in seen_links:
                        seen_links.add(l)
                        all_candidates.append((l, hint))
                        added += 1
                print(f"[{hint}] {url} -> {added} new links (Total unique: {len(all_candidates)})")
            except Exception as e:
                print(f"Error fetching {url}: {e}")
            time.sleep(0.15)
            if len(all_candidates) >= target_min:
                break
        if len(all_candidates) >= target_min:
            break

    print(f"Collected total of {len(all_candidates)} unique candidate recipe URLs.\n")
    return all_candidates

def crawl_recipes(candidates, target_count=500, checkpoint_path="cache/cookomix_raw_500.json"):
    print(f"=== Step 2: Crawling & Ingesting up to {target_count} Recipes ===")
    os.makedirs(os.path.dirname(checkpoint_path) or ".", exist_ok=True)
    
    recipes = []
    seen_ids = set()

    # Load existing checkpoint if available
    if os.path.exists(checkpoint_path):
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
                for r in existing:
                    recipes.append(r)
                    seen_ids.add(r["id"])
            print(f"Resumed from checkpoint: {len(recipes)} recipes already loaded.")
        except Exception as e:
            print(f"Failed to load checkpoint: {e}")

    start_time = time.time()
    for idx, (url, hint) in enumerate(candidates):
        if len(recipes) >= target_count:
            break

        print(f"[{len(recipes)+1}/{target_count}] Fetching: {url} ({hint})", end=" ... ")
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=12) as r:
                html = r.read().decode("utf-8", errors="ignore")
            
            parsed = parse_cookomix_html(html, source_url=url, context_hint=hint)
            if parsed and parsed["id"] not in seen_ids:
                seen_ids.add(parsed["id"])
                recipes.append(parsed)
                print(f"OK: '{parsed['title']}' | {parsed['category']} | author: {parsed['author']} | steps: {len(parsed['steps'])}")
            elif parsed and parsed["id"] in seen_ids:
                print("Skipped (Duplicate ID)")
            else:
                print("Failed (No Recipe JSON-LD)")
        except Exception as e:
            print(f"HTTP/Network Error: {e}")

        # Polite inter-request delay
        time.sleep(0.3)

        # Periodic checkpoint
        if len(recipes) % 25 == 0 and len(recipes) > 0:
            with open(checkpoint_path, "w", encoding="utf-8") as f:
                json.dump(recipes, f, ensure_ascii=False, indent=2)
            print(f"--> Checkpoint saved ({len(recipes)} recipes) to {checkpoint_path}")

    # Final save
    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump(recipes, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - start_time
    print(f"\nCrawling complete in {elapsed:.1f}s. Total recipes in checkpoint: {len(recipes)}")
    return recipes

if __name__ == "__main__":
    candidates = collect_candidate_links(target_min=550)
    recipes = crawl_recipes(candidates, target_count=500, checkpoint_path="cache/cookomix_raw_500.json")
