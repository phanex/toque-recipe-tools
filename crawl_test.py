import urllib.request
import re
import json
import time
import os
import sys

from sources.cookomix import parse_cookomix_html

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def get_recipe_links_from_category(cat_url, max_count=15):
    print(f"Scanning category: {cat_url}...")
    req = urllib.request.Request(cat_url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=12) as r:
        html = r.read().decode("utf-8")
    
    links = set(re.findall(r'href=["\'](https://www.cookomix.com/recettes/[^"/]+-thermomix/)["\']', html))
    return list(links)[:max_count]

def main():
    target_count = 25
    categories = [
        "https://www.cookomix.com/recettes/categories/pains/",
        "https://www.cookomix.com/recettes/categories/patisseries/",
        "https://www.cookomix.com/recettes/categories/pates/"
    ]
    
    all_links = []
    for cat in categories:
        links = get_recipe_links_from_category(cat, max_count=10)
        for l in links:
            if l not in all_links:
                all_links.append(l)
        if len(all_links) >= target_count:
            break

    all_links = all_links[:target_count]
    print(f"Collected {len(all_links)} candidate recipes to crawl.")

    os.makedirs("cache", exist_ok=True)
    results = []
    for i, link in enumerate(all_links):
        print(f"[{i+1}/{len(all_links)}] Fetching: {link}")
        try:
            req = urllib.request.Request(link, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=12) as r:
                html = r.read().decode("utf-8", errors="ignore")
            parsed = parse_cookomix_html(html, source_url=link)
            if parsed:
                results.append(parsed)
                print(f"   -> OK: '{parsed['title']}' | Author: {parsed['author']} | Steps: {len(parsed['steps'])}")
            else:
                print(f"   -> Failed to parse recipe JSON-LD")
        except Exception as e:
            print(f"   -> Error: {e}")
        time.sleep(0.3)

    cache_file = "cache/cookomix_sample.json"
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n--- Crawl & Parse Summary ---")
    print(f"Total parsed: {len(results)} / {target_count}")
    
    with_author = sum(1 for r in results if r["author"] and r["author"] != "Cookomix Community")
    total_steps = sum(len(r["steps"]) for r in results)
    machine_steps = sum(sum(1 for s in r["steps"] if s["machine"] is not None) for r in results)
    weigh_steps = sum(sum(1 for s in r["steps"] if s["weigh"] is not None) for r in results)
    
    print(f"Recipes with identified human author: {with_author} ({with_author/len(results)*100:.1f}%)")
    print(f"Total instruction steps: {total_steps}")
    print(f"Machine operational steps (speed/temp/knead): {machine_steps} ({machine_steps/total_steps*100:.1f}%)")
    print(f"Weigh scale steps extracted: {weigh_steps}")

    # Inspect sample machine and weigh steps
    print("\n--- Sample Extracted Machine Steps ---")
    shown = 0
    for r in results:
        for s in r["steps"]:
            if s["machine"]:
                m = s["machine"]
                print(f"[{r['title']}] text: '{s['text'][:60]}...' -> program: {m['program']}, sec: {m['seconds']}, spd: {m['speed']}, temp: {m['tempC']}C, rev: {m['reverse']}")
                shown += 1
                if shown >= 5:
                    break
        if shown >= 5:
            break

    print("\n--- Sample Extracted Weigh Steps ---")
    shown_w = 0
    for r in results:
        for s in r["steps"]:
            if s["weigh"]:
                w = s["weigh"]
                print(f"[{r['title']}] label: '{w['label']}' -> {w['grams']}g")
                shown_w += 1
                if shown_w >= 5:
                    break
        if shown_w >= 5:
            break

if __name__ == "__main__":
    main()
