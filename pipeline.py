#!/usr/bin/env python3
import argparse
import sys
import os
import json

from engine.translate import TranslationEngine
from engine.database import init_database, insert_recipes, deploy_to_device
from sources.mconline import fetch_catalog_page, fetch_recipe_detail, parse_mconline_json
from sources.cookomix import fetch_cookomix_recipe
from sources.factory_db import parse_stock_factory_db

def main():
    parser = argparse.ArgumentParser(description="Toque Recipe Tools: Ingestion, Translation & Deployment Pipeline")
    parser.add_argument("--source", choices=["mconline", "factory", "cookomix"], default="mconline", help="Recipe ingestion source")
    parser.add_argument("--source-lang", default="pl", help="Source language code (e.g. pl, fr, de)")
    parser.add_argument("--target-lang", default="uk", help="Target translation language code (e.g. uk, en, de, cs)")
    parser.add_argument("--pages", type=int, default=1, help="Number of pages to ingest (for mconline)")
    parser.add_argument("--url", help="Recipe URL (for cookomix)")
    parser.add_argument("--factory-db", help="Path to original factory database Recipes.db")
    parser.add_argument("--output", default="recettes.db", help="Path to generated SQLite database")
    parser.add_argument("--cache", default="cache/translations.json", help="Path to persistent translation cache")
    parser.add_argument("--deploy", action="store_true", help="Deploy generated database to connected device")
    parser.add_argument("--adb", default="adb", help="Path to ADB binary")
    parser.add_argument("--device", help="ADB device serial or IP (e.g. 192.168.0.218:5555)")

    args = parser.parse_args()

    # Step 1: Ingest
    recipes = []
    print(f"--- Ingestion Stage [Source: {args.source}] ---")
    if args.source == "mconline":
        lang_header = f"{args.source_lang}-{args.source_lang.upper()}"
        print(f"Fetching catalog pages from Lidl MC Online (lang={lang_header})...")
        for p in range(1, args.pages + 1):
            try:
                page_data = fetch_catalog_page(p, lang=lang_header)
                items = page_data.get("data", {}).get("recipes", [])
                print(f"Page {p}: Found {len(items)} recipe entries")
                for it in items:
                    r_id = it.get("id")
                    if r_id:
                        detail = fetch_recipe_detail(r_id, lang=lang_header)
                        parsed = parse_mconline_json(detail)
                        if parsed:
                            recipes.append(parsed)
            except Exception as e:
                print(f"Error fetching page {p}: {e}")
                break

    elif args.source == "cookomix":
        if not args.url:
            print("Error: --url is required when source is cookomix")
            sys.exit(1)
        print(f"Fetching recipe from Cookomix: {args.url}")
        parsed = fetch_cookomix_recipe(args.url)
        if parsed:
            recipes.append(parsed)

    elif args.source == "factory":
        if not args.factory_db:
            print("Error: --factory-db is required when source is factory")
            sys.exit(1)
        print(f"Parsing factory database: {args.factory_db}")
        recipes = parse_stock_factory_db(args.factory_db)

    print(f"Total recipes ingested: {len(recipes)}")
    if not recipes:
        print("No recipes to process. Exiting.")
        return

    # Step 2: Translation (if source_lang != target_lang)
    if args.source_lang != args.target_lang:
        print(f"--- Translation Stage [{args.source_lang} -> {args.target_lang}] ---")
        translator = TranslationEngine(cache_file=args.cache)

        # Extract all unique strings
        phrases = set()
        for r in recipes:
            if r.get("title"):
                phrases.add(r["title"])
            if r.get("notes"):
                phrases.add(r["notes"])
            for g in r.get("ingredients", []):
                if g.get("group"):
                    phrases.add(g["group"])
                for item in g.get("items", []):
                    if item.get("name"):
                        phrases.add(item["name"])
                    if item.get("unit"):
                        phrases.add(item["unit"])
                    if item.get("note"):
                        phrases.add(item["note"])
            for s in r.get("steps", []):
                if s.get("text"):
                    phrases.add(s["text"])
                weigh = s.get("weigh")
                if weigh and weigh.get("label"):
                    phrases.add(weigh["label"])

        translator.translate_batch(list(phrases), sl=args.source_lang, tl=args.target_lang)

        # Apply translations
        for r in recipes:
            r["title"] = translator.get(r.get("title"), args.source_lang, args.target_lang)
            r["notes"] = translator.get(r.get("notes"), args.source_lang, args.target_lang)
            for g in r.get("ingredients", []):
                g["group"] = translator.get(g.get("group"), args.source_lang, args.target_lang)
                for item in g.get("items", []):
                    item["name"] = translator.get(item.get("name"), args.source_lang, args.target_lang)
                    item["unit"] = translator.get(item.get("unit"), args.source_lang, args.target_lang)
                    item["note"] = translator.get(item.get("note"), args.source_lang, args.target_lang)
            for s in r.get("steps", []):
                s["text"] = translator.get(s.get("text"), args.source_lang, args.target_lang)
                if s.get("weigh") and s["weigh"].get("label"):
                    s["weigh"]["label"] = translator.get(s["weigh"]["label"], args.source_lang, args.target_lang)

    # Step 3: SQLite generation
    print(f"--- Database Compilation Stage [{args.output}] ---")
    locale_code = f"{args.target_lang}_{args.target_lang.upper()}"
    conn = init_database(args.output, locale=locale_code)
    insert_recipes(conn, recipes)
    conn.close()
    print(f"Database successfully generated at {args.output}")

    # Step 4: Optional deployment
    if args.deploy:
        print("--- Deployment Stage ---")
        deploy_to_device(args.adb, args.device, args.output, images_dir="images")

if __name__ == "__main__":
    main()
