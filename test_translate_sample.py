import json
import os
from engine.translate import TranslationEngine
from engine.database import init_database, insert_recipes

def main():
    sample_file = "cache/cookomix_sample.json"
    if not os.path.exists(sample_file):
        print("Sample file not found!")
        return

    with open(sample_file, "r", encoding="utf-8") as f:
        recipes = json.load(f)

    print(f"Loaded {len(recipes)} recipes from {sample_file}")

    # Re-parse recipes through the latest parser logic if needed, or translate directly
    translator = TranslationEngine(cache_file="cache/translations_cm.json")

    phrases = set()
    for r in recipes:
        if r.get("title"):
            phrases.add(r["title"])
        if r.get("notes"):
            phrases.add(r["notes"])
        if r.get("category"):
            phrases.add(r["category"])
        for g in r.get("ingredients", []):
            for item in g.get("items", []):
                if item.get("name"):
                    phrases.add(item["name"])
        for s in r.get("steps", []):
            if s.get("text"):
                phrases.add(s["text"])
            weigh = s.get("weigh")
            if weigh and weigh.get("label"):
                phrases.add(weigh["label"])

    print(f"Total unique French phrases to translate: {len(phrases)}")
    translator.translate_batch(list(phrases), sl="fr", tl="uk", max_workers=6)

    # Apply translations
    for r in recipes:
        r["title"] = translator.get(r.get("title"), "fr", "uk")
        r["notes"] = translator.get(r.get("notes"), "fr", "uk")
        r["category"] = translator.get(r.get("category"), "fr", "uk")
        for g in r.get("ingredients", []):
            for item in g.get("items", []):
                item["name"] = translator.get(item.get("name"), "fr", "uk")
        for s in r.get("steps", []):
            s["text"] = translator.get(s.get("text"), "fr", "uk")
            if s.get("weigh") and s["weigh"].get("label"):
                s["weigh"]["label"] = translator.get(s["weigh"]["label"], "fr", "uk")

    # Build test sqlite
    db_test = "cache/test_cookomix_25.db"
    conn = init_database(db_test, locale="uk_UA")
    insert_recipes(conn, recipes)
    conn.close()

    print(f"\n--- Translation & SQLite Build Complete ---")
    print(f"Sample DB created: {db_test}")
    for r in recipes[:5]:
        print(f"  - [{r['id']}] {r['title']} (Автор: {r['author']}, Категорія: {r['category']})")
        for s in r["steps"]:
            if s.get("weigh"):
                print(f"     -> Ваги: {s['weigh']['label']} : {s['weigh']['grams']} г")
                break

if __name__ == "__main__":
    main()
