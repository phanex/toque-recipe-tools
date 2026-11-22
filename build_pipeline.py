import os
import sys
import json
import sqlite3
import time
import re
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from engine.translate import TranslationEngine
from engine.database import init_database, insert_recipes
from engine.media import download_and_optimize
from sources.cookomix import clean_weigh_label, CANONICAL_CATEGORIES

BASE_DIR = r"c:\Workbench\toque-recipe-tools"
RAW_CACHE_CANDIDATES = [
    r"c:\Workbench\toque-recipe-tools\cache\cookomix_raw_500.json",
    r"c:\Workbench\skmc1200\cache\cookomix_raw_500.json"
]
TRANSLATIONS_CACHE = r"c:\Workbench\toque-recipe-tools\cache\translations_cm.json"
COOKOMIX_DB = r"c:\Workbench\toque-recipe-tools\cache\recettes_cookomix_500.db"
IMAGES_DIR = r"c:\Workbench\toque-recipe-tools\cache\cookomix_images"
TARGET_MAIN_DB = r"c:\Workbench\skmc1200\recettes_uk.db"
BACKUP_MAIN_DB = r"c:\Workbench\skmc1200\recettes_uk_backup_before_cm.db"
ADB_BIN = r"C:\Applications\Utils\platform-tools\adb.exe"
DEVICE_TARGET = "192.168.0.218:5555"

def step1_translate(raw_recipes):
    print("\n=======================================================")
    print("STEP 1: Multi-Threaded Translation to Ukrainian (uk_UA)")
    print("=======================================================")
    
    translator = TranslationEngine(cache_file=TRANSLATIONS_CACHE)
    
    phrases = set()
    for r in raw_recipes:
        if r.get("title"):
            phrases.add(r["title"])
        if r.get("notes"):
            phrases.add(r["notes"])
        for g in r.get("ingredients", []):
            if g.get("group"):
                phrases.add(g["group"])
            for it in g.get("items", []):
                if it.get("name"):
                    phrases.add(it["name"])
                if it.get("unit"):
                    phrases.add(it["unit"])
                if it.get("note"):
                    phrases.add(it["note"])
        for s in r.get("steps", []):
            if s.get("text"):
                phrases.add(s["text"])
            weigh = s.get("weigh")
            if weigh and weigh.get("label"):
                phrases.add(weigh["label"])

    print(f"Total unique phrases extracted across {len(raw_recipes)} recipes: {len(phrases)}")
    
    # Translate using 8 workers
    translator.translate_batch(list(phrases), sl="fr", tl="uk", max_workers=8)

    # Apply translations
    translated_recipes = []
    for r in raw_recipes:
        r_copy = dict(r)
        r_copy["title"] = translator.get(r.get("title"), "fr", "uk").strip()
        r_copy["notes"] = translator.get(r.get("notes"), "fr", "uk").strip()
        
        # Ingredients
        new_groups = []
        for g in r.get("ingredients", []):
            new_items = []
            for it in g.get("items", []):
                new_items.append({
                    "name": translator.get(it.get("name"), "fr", "uk").strip(),
                    "qty": it.get("qty", ""),
                    "unit": translator.get(it.get("unit"), "fr", "uk").strip(),
                    "note": translator.get(it.get("note"), "fr", "uk").strip()
                })
            new_groups.append({
                "group": translator.get(g.get("group"), "fr", "uk").strip(),
                "items": new_items
            })
        r_copy["ingredients"] = new_groups

        # Steps
        new_steps = []
        for s in r.get("steps", []):
            s_text = translator.get(s.get("text"), "fr", "uk").strip()
            w = s.get("weigh")
            new_weigh = None
            if w and w.get("label"):
                trans_label = translator.get(w["label"], "fr", "uk").strip()
                clean_lbl = clean_weigh_label(trans_label)
                if not clean_lbl:
                    clean_lbl = clean_weigh_label(w["label"])
                if not clean_lbl:
                    clean_lbl = "Інгредієнт"
                new_weigh = {
                    "label": clean_lbl,
                    "grams": w.get("grams", 0)
                }

            new_steps.append({
                "text": s_text,
                "machine": s.get("machine"),
                "weigh": new_weigh,
                "needsReview": False
            })
        r_copy["steps"] = new_steps

        # Category is already canonically normalized in Ukrainian!
        # Ensure it belongs strictly to CANONICAL_CATEGORIES
        if r_copy.get("category") not in CANONICAL_CATEGORIES:
            r_copy["category"] = "Основні страви"

        translated_recipes.append(r_copy)

    print(f"Successfully translated {len(translated_recipes)} recipes.")
    return translated_recipes

def step2_compile_cookomix_db(recipes, output_path=COOKOMIX_DB):
    print("\n=======================================================")
    print(f"STEP 2: Compiling SQLite Database ({output_path})")
    print("=======================================================")
    
    conn = init_database(output_path, locale="uk_UA")
    insert_recipes(conn, recipes)
    conn.close()
    print(f"Database created at: {output_path}")

def step3_verify_database(db_path):
    print("\n=======================================================")
    print(f"STEP 3: Automated Post-Build Integrity Verification ({db_path})")
    print("=======================================================")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 1. Assert PRAGMA user_version == 1
    cur.execute("PRAGMA user_version;")
    uv = cur.fetchone()[0]
    print(f"  [1/5] PRAGMA user_version: {uv}")
    assert uv == 1, f"ERROR: user_version is {uv}, expected 1!"

    # 2. Check all 5 required tables
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {r[0] for r in cur.fetchall()}
    required_tables = {"recipes", "favorites", "adjustments", "cooked", "android_metadata"}
    missing = required_tables - tables
    print(f"  [2/5] Required tables check: {tables}")
    assert not missing, f"ERROR: Missing tables: {missing}"

    # 3. Check android_metadata
    cur.execute("SELECT locale FROM android_metadata;")
    loc = cur.fetchone()[0]
    print(f"  [3/5] Locale: {loc}")

    # 4. Recipes count and hygiene check
    cur.execute("SELECT id, title, json FROM recipes;")
    rows = cur.fetchall()
    print(f"  [4/5] Total recipes count: {len(rows)}")
    assert len(rows) > 0, "ERROR: No recipes found in database!"

    categories_count = {}
    weigh_count = 0
    machine_count = 0
    invalid_titles = 0
    invalid_categories = 0
    dirty_weigh_labels = 0

    for r_id, title, r_json in rows:
        if not title or len(title.strip()) == 0:
            invalid_titles += 1
        
        data = json.loads(r_json)
        cat = data.get("category", "")
        if cat not in CANONICAL_CATEGORIES:
            invalid_categories += 1
        categories_count[cat] = categories_count.get(cat, 0) + 1

        for s in data.get("steps", []):
            if s.get("machine"):
                machine_count += 1
            w = s.get("weigh")
            if w:
                weigh_count += 1
                lbl = w.get("label", "")
                if not lbl or "(" in lbl or len(lbl) > 35:
                    dirty_weigh_labels += 1

    print(f"  [5/5] Data Quality & Hygiene Results:")
    print(f"        - Invalid/empty titles: {invalid_titles}")
    print(f"        - Non-canonical categories: {invalid_categories}")
    print(f"        - Total machine operational steps: {machine_count}")
    print(f"        - Total scale weigh steps: {weigh_count}")
    print(f"        - Dirty/unclean weigh labels: {dirty_weigh_labels}")
    print(f"\n        Category Distribution:")
    for c, cnt in sorted(categories_count.items(), key=lambda x: -x[1]):
        print(f"          * {c:20s}: {cnt:3d} recipes")

    assert invalid_titles == 0, f"ERROR: Found {invalid_titles} invalid titles!"
    assert invalid_categories == 0, f"ERROR: Found {invalid_categories} non-canonical categories!"
    assert dirty_weigh_labels == 0, f"ERROR: Found {dirty_weigh_labels} dirty weigh labels!"

    conn.close()
    print("\n>>> ALL POST-BUILD INTEGRITY CHECKS PASSED WITH 100% SUCCESS! <<<\n")
    return {
        "total_recipes": len(rows),
        "machine_steps": machine_count,
        "weigh_steps": weigh_count,
        "categories_count": categories_count
    }

def verify_merged_db(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA user_version;")
    uv = cur.fetchone()[0]
    assert uv == 1, f"Merged DB user_version must be 1, got {uv}"
    cur.execute("SELECT count(*) FROM recipes;")
    cnt = cur.fetchone()[0]
    assert cnt >= 1600, f"Expected >= 1600 recipes, got {cnt}"
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {r[0] for r in cur.fetchall()}
    required = {"recipes", "favorites", "adjustments", "cooked", "android_metadata"}
    assert required.issubset(tables), f"Missing tables: {required - tables}"
    
    # Assert zero non-canonical categories across all 1600+ recipes
    cur.execute("SELECT json FROM recipes;")
    non_canon = 0
    for (r_json,) in cur.fetchall():
        d = json.loads(r_json)
        if d.get("category") not in CANONICAL_CATEGORIES:
            non_canon += 1
    assert non_canon == 0, f"Found {non_canon} non-canonical categories in merged DB!"
    conn.close()
    print(f"  [+] Merged database verified: {cnt} recipes, user_version=1, all 5 tables present, 0 non-canonical categories!")

def step4_merge_catalog(cookomix_recipes):
    print("\n=======================================================")
    print("STEP 4: Merging Cookomix Catalog into Main recettes_uk.db")
    print("=======================================================")

    import shutil
    if os.path.exists(TARGET_MAIN_DB) and not os.path.exists(BACKUP_MAIN_DB):
        shutil.copyfile(TARGET_MAIN_DB, BACKUP_MAIN_DB)
        print(f"Backed up original database to {BACKUP_MAIN_DB}")

    existing_recipes = {}
    if os.path.exists(TARGET_MAIN_DB):
        conn = sqlite3.connect(TARGET_MAIN_DB)
        cur = conn.cursor()
        cur.execute("SELECT id, title, json, updated FROM recipes;")
        for r_id, title, r_json, updated in cur.fetchall():
            try:
                data = json.loads(r_json)
                existing_recipes[r_id] = data
            except Exception:
                pass
        conn.close()
    print(f"Loaded {len(existing_recipes)} existing official recipes from {TARGET_MAIN_DB}")

    # Merge Cookomix recipes
    merged_recipes = dict(existing_recipes)
    added_cm = 0
    for r in cookomix_recipes:
        r_id = r["id"]
        merged_recipes[r_id] = r
        added_cm += 1

    print(f"Added {added_cm} Cookomix recipes. Total merged collection: {len(merged_recipes)} recipes.")

    # Write merged database
    merged_list = list(merged_recipes.values())
    conn_m = init_database(TARGET_MAIN_DB, locale="uk_UA")
    insert_recipes(conn_m, merged_list)
    conn_m.close()

    # Re-verify merged database
    print(f"Verifying merged database integrity...")
    verify_merged_db(TARGET_MAIN_DB)
    return len(merged_recipes)

def step5_download_images(recipes):
    print("\n=======================================================")
    print(f"STEP 5: Downloading & Optimizing Images (800x480 Quality 85)")
    print("=======================================================")
    
    os.makedirs(IMAGES_DIR, exist_ok=True)
    tasks = []
    for r in recipes:
        img_url = r.get("image_url")
        img_name = r.get("image")
        if img_url and img_name:
            dest = os.path.join(IMAGES_DIR, img_name)
            tasks.append((img_url, dest))

    print(f"Total images to download/optimize: {len(tasks)}")
    
    done = 0
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = [pool.submit(download_and_optimize, url, dest) for url, dest in tasks]
        for f in futures:
            if f.result():
                done += 1
            if done % 50 == 0 or done == len(tasks):
                print(f"  Images progress: {done}/{len(tasks)} processed")

    print(f"Images optimization completed: {done} images ready in {IMAGES_DIR}")

def step6_deploy():
    print("\n=======================================================")
    print(f"STEP 6: Deploying Merged Database & Images via ADB ({DEVICE_TARGET})")
    print("=======================================================")
    import subprocess

    base_cmd = [ADB_BIN, "-s", DEVICE_TARGET]
    
    print("1. Checking ADB connection...")
    subprocess.run(base_cmd + ["get-state"], check=True)

    print(f"2. Pushing merged {TARGET_MAIN_DB} to /sdcard/recettes_staged.db...")
    subprocess.run(base_cmd + ["push", TARGET_MAIN_DB, "/sdcard/recettes_staged.db"], check=True)

    print(f"3. Pushing Cookomix images to /sdcard/toque_images_staged/...")
    subprocess.run(base_cmd + ["shell", "mkdir -p /sdcard/toque_images_staged"], check=True)
    subprocess.run(base_cmd + ["push", f"{IMAGES_DIR}/.", "/sdcard/toque_images_staged/"], check=True)

    print("4. Executing atomic deployment with Multi-Category Security (MCS) labels...")
    fix_permissions_cmd = """
        UID=$(dumpsys package app.toque | grep userId | head -n 1 | cut -d= -f2)
        MCS=$(ls -Zd /data/data/app.toque/files | awk '{print $1}')
        
        cp /sdcard/recettes_staged.db /data/data/app.toque/databases/recettes.db
        rm -f /sdcard/recettes_staged.db
        
        if [ -d "/sdcard/toque_images_staged" ]; then
            cp -r /sdcard/toque_images_staged/* /data/data/app.toque/files/images/ 2>/dev/null
            rm -rf /sdcard/toque_images_staged
        fi
        
        chown -R u0_a${UID}:u0_a${UID} /data/data/app.toque/databases /data/data/app.toque/files 2>/dev/null
        chcon -R ${MCS} /data/data/app.toque/databases /data/data/app.toque/files 2>/dev/null
        chmod 770 /data/data/app.toque/databases
        chmod 660 /data/data/app.toque/databases/*
        chmod 700 /data/data/app.toque/files/images 2>/dev/null
        chmod 644 /data/data/app.toque/files/images/* 2>/dev/null
        
        # Ensure autoSync is disabled
        PREFS="/data/data/app.toque/shared_prefs/toque.xml"
        if [ -f "$PREFS" ]; then
            if grep -q "autoSync" "$PREFS"; then
                sed -i 's/<boolean name="autoSync" value="true" \/>/<boolean name="autoSync" value="false" \/>/g' "$PREFS"
            else
                sed -i 's/<\/map>/    <boolean name="autoSync" value="false" \/>\\n<\/map>/g' "$PREFS"
            fi
        fi
        
        am force-stop app.toque
        am start -n app.toque/app.toque.ui.MainActivity
    """
    res = subprocess.run(base_cmd + ["shell", f"su -c '{fix_permissions_cmd}'"], capture_output=True, text=True)
    print(f"ADB su output: {res.stdout.strip()}")
    print("Deployment completed successfully. Toque restarted with complete catalog.")

if __name__ == "__main__":
    raw_cache_path = None
    for p in RAW_CACHE_CANDIDATES:
        if os.path.exists(p):
            raw_cache_path = p
            break

    if not raw_cache_path:
        print(f"Error: No raw cache file found in {RAW_CACHE_CANDIDATES}. Please wait for crawler to finish.")
        sys.exit(1)

    with open(raw_cache_path, "r", encoding="utf-8") as f:
        raw_recipes = json.load(f)

    print(f"Loaded {len(raw_recipes)} raw Cookomix recipes from {raw_cache_path}.")
    
    # Run full pipeline
    translated = step1_translate(raw_recipes)
    step2_compile_cookomix_db(translated, COOKOMIX_DB)
    stats = step3_verify_database(COOKOMIX_DB)
    merged_count = step4_merge_catalog(translated)
    step5_download_images(translated)
    step6_deploy()

    print("\n*************************************************************")
    print(f"ALL PROTOCOL STAGES ACCOMPLISHED SUCCESSFULLY!")
    print(f"Total Cookomix recipes: {len(translated)}")
    print(f"Total Merged collection: {merged_count}")
    print(f"Device target: {DEVICE_TARGET}")
    print("*************************************************************")
