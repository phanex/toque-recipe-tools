---
name: toque-recipe-tools
description: Language-agnostic engineering protocol and CLI toolkit for scraping, validating, translating, deduplicating, and deploying offline culinary databases for Monsieur Cuisine Connect (Toque launcher).
---

# Toque Recipe Tools Protocol & Architecture

This document defines the universal protocol for constructing an offline, media-rich recipe database for smart culinary appliances running the Toque launcher.

---

## 1. Upstream Catalog Sources & Ingestion

Smart kitchen appliances typically draw recipes from multiple sources:

### 1. Local Stock Factory Databases
- **Firmware Path**: `/data/data/de.silpion.mc2/databases/Recipes` with cached images in `files/images/`.
- **Value**: Factory-tested machine parameters: motor speed (1–10, Turbo), blade reverse direction, heating element (37°C–130°C), step duration, and scale weigh steps.

### 2. Cloud Appliance APIs (Lidl MC Online)
- **Sources**: Official regional REST API endpoints (`pl_PL`, `de_DE`, `fr_FR`, `es_ES`, `it_IT`).
- **Quality Filter**: Ingest recipes with verified photography (`has_image == true`). Exclude incomplete text-only placeholders or recipes lacking appliance parameters.

### 3. Community Recipe Platforms (e.g., Cookomix)
- Extract structured recipe metadata from public schema blocks (`application/ld+json`, `@type: Recipe`).
- Normalize appliance operations (speeds, temperatures, reverse blade, cooking times) into Toque's `StepMachine` model.

---

## 2. Media Optimization & Storage Strategy

Embedded appliances operate with limited RAM (1 GB RAM on MediaTek MT8163):
1. **Resolution Cap**: Downscale studio photographs to a maximum of **800×480 px** (matching the 7" 1024×600 aspect ratio).
2. **Compression**: Encode at JPEG Quality 80–85. Reduces raw 2–4 MB cloud assets down to ~60–90 KB per image.
3. **Storage Location**: Store images in `/data/data/app.toque/files/images/<image_name>.jpg`.

---

## 3. Translation Engine & String Extraction

1. **Persistent Disk Caching**:
   - Hash-keyed translation cache (`hash(source_phrase) -> translated_phrase`).
   - Repetitive culinary phrases («add 1 tsp salt», «chop for 10 sec / speed 5») cut translation workload significantly.

2. **Full Schema Traversal**:
   Extract and translate every user-facing string across the recipe JSON:
   - `title`
   - `description` / `notes`
   - `ingredients[].group`
   - `ingredients[].items[].name`, `unit`, `note`
   - `steps[].text`
   - **`steps[].weigh.label`**: Scale weigh steps display `weigh.label` during cooking (`CookScreen`). Must be clean, capitalized localized noun phrases (e.g., `Борошно`, `Вода`, `Вершкове масло`), not raw sentences or foreign phrases.

---

## 4. SQLite Schema & The Critical Version Pragma

Target database path on device: `/data/data/app.toque/databases/recettes.db`

### Schema Definition
```sql
CREATE TABLE recipes (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    json TEXT NOT NULL,
    updated INTEGER NOT NULL
);

CREATE TABLE favorites (
    id TEXT PRIMARY KEY
);

-- Pre-initialized for user personal adjustments and cooking statistics:
CREATE TABLE IF NOT EXISTS adjustments (
    id TEXT PRIMARY KEY,
    json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cooked (
    id TEXT PRIMARY KEY,
    count INTEGER NOT NULL,
    last INTEGER NOT NULL
);

CREATE TABLE android_metadata (
    locale TEXT
);
INSERT INTO android_metadata VALUES ('<target_locale>');
```

### CRITICAL: `PRAGMA user_version = 1;`
```sql
PRAGMA user_version = 1;
```
> [!CAUTION]
> In Android's `SQLiteOpenHelper`, a newly created database defaults to `user_version = 0`.
> If deployed with `user_version = 0`, Android assumes the schema has not been initialized and triggers `onCreate()`. Because tables already exist, Toque will crash immediately on launch with:
> `android.database.sqlite.SQLiteException: table recipes already exists`.
> **Always ensure `PRAGMA user_version = 1;` is executed before deployment.**

---

## 5. Permissions & SELinux Multi-Category Security (MCS)

Apply correct ownership and Multi-Category Security labels:
```bash
adb shell "su -c '
    chown -R u0_a47:u0_a47 /data/data/app.toque/databases /data/data/app.toque/files
    chcon -R u:object_r:app_data_file:s0:c512,c768 /data/data/app.toque/databases /data/data/app.toque/files
    chmod 770 /data/data/app.toque/databases
    chmod 660 /data/data/app.toque/databases/*
    chmod 700 /data/data/app.toque/files/images
    chmod 644 /data/data/app.toque/files/images/*
'"
```

---

## 6. Disabling Auto-Sync to Protect Local Translations

> [!CAUTION]
> By default, Toque enables automatic nightly catalog synchronization (`autoSync = true` in `Prefs.kt`).
> Every night or when triggered in settings, `OnlineSync` queries the cloud API (`mc-api.tecpal.com`). Because custom/third-party languages are not published on manufacturer servers, the sync service falls back to default languages and **overwrites localized recipes**, reverting all custom translations and edits!

Disable auto-sync via ADB:
```bash
adb shell "su -c '
    PREFS=\"/data/data/app.toque/shared_prefs/toque.xml\"
    if [ -f \"\$PREFS\" ]; then
        if grep -q \"autoSync\" \"\$PREFS\"; then
            sed -i \"s/<boolean name=\\\"autoSync\\\" value=\\\"true\\\" \/>/<boolean name=\\\"autoSync\\\" value=\\\"false\\\" \/>/g\" \"\$PREFS\"
        else
            sed -i \"s/<\/map>/    <boolean name=\\\"autoSync\\\" value=\\\"false\\\" \/>\\n<\/map>/g\" \"\$PREFS\"
        fi
    fi
'"
```

---

## 7. Category Normalization to Canonical Taxonomies

Toque displays categories as horizontal filter chips. Third-party portals (such as Cookomix) often output comma-separated, multi-tag combinations (e.g. *«Apéritif, Accompagnement»*, *«Petit-déjeuner, Desserts»*). If left unnormalized, these create dozens of redundant hybrid chips.

### Canonical Appliance Taxonomies:
Map every incoming recipe strictly to one of the 14 standard categories:
- **Випічка (Baking)**: Bread, baguettes, buns, brioche, dough, pizza.
- **Десерти (Desserts)**: Cakes, cookies, puddings, creams, chocolate.
- **Основні страви (Main Dishes)**: Meat, poultry, fish, pasta, noodles, risotto, cannelloni.
- **Супи (Soups)**: Soups, broths, potages, curries.
- **Закуски (Appetizers)**: Canapes, croutons, snacks, finger food, spreads.
- **Гарніри (Side Dishes)**: Vegetables, spinach, potatoes, purees.
- **Соуси та пасти (Sauces & Spreads)**: Sauces, dips, pestos, dressings.
- **Салати (Salads)**: Fresh & warm salads.
- **Сніданки (Breakfast)**: Pancakes, cereals, morning meals.
- **Напої (Beverages)**: Smoothies, juices, cocktails.
- **Джеми та варення (Jams & Preserves)**: Sweet spreads, compotes.
- **Веганське (Vegan)** / **Вечеря (Dinner)** / **Все в одному (One-Pot)**.

*All secondary tags, diet indicators (vegan, gluten-free), and source marks (e.g., `["Cookomix", "CM"]`) MUST be pushed into the `tags` array instead of polluting the primary `category`.*

---

## 8. Safety Policy, Appliance Parameter Clamping & Smart Adaptation

Third-party community platforms (such as Cookomix / Thermomix recipes) frequently specify motor and heating combinations that violate Monsieur Cuisine Connect's firmware and physical hardware safety limits (`SafetyPolicy.kt`). If written directly to the database without normalization, Toque marks the step invalid (`violations.isNotEmpty()`), permanently disabling the machine launch button.

### Smart Adaptation Protocols:
**Never destructively clamp cumulative durations or parameters if it compromises culinary results.** Instead, apply the following 4 engineering protocols:

1. **Smart Split: Knead Duration (`petrir` > 120 s)**:
   - *Physical limit*: MCC firmware restricts continuous kneading to **120 seconds (2 minutes)** to protect the drive motor and transmission gears from overheating under dense dough load.
   - *Protocol*: Split the step into consecutive cycles of max 120 s each:
     - 240 s (4 min) $\rightarrow$ Step A (120 s) + Step B (120 s).
     - 180 s (3 min) $\rightarrow$ Step A (120 s) + Step B (60 s).
     - 300 s (5 min) $\rightarrow$ Step A (120 s) + Step B (120 s) + Step C (60 s).
     - Append cycle markers: *«(Частина 1/2 — 120 с)»*, *«(Частина 2/2 — 120 с)»*.

2. **Smart Split: Searing & Toasting (`rissoler` > 840 s / 14 min)**:
   - *Physical limit*: Toasting mode heats the base plate up to 130°C and is hard-capped at **14 minutes (840 s)** to prevent oil smoking and thermal cutoff trips.
   - *Protocol*: Split long searing steps (> 840 s) into two consecutive cycles (e.g. 20 min $\rightarrow$ 10 min + 10 min), allowing base temperature equalization.

3. **Two-Phase Adaptation: Heated High-Speed Blending (`tempC > 0` + `speed ≥ 4`)**:
   - *Physical limit*: MCC's wide 3-liter bowl creates severe vortex forces at speed $\ge 4$; heating with active high speed is mechanically blocked (`Limits.MAX_SPEED_HEATED = 3`) to prevent scalding liquid leaks under steam pressure.
   - *Protocol*:
     - *For stews, soups, and cooking*: Normalize to `speed = 3` (retains 100% of thermal transfer and simmering without blending ingredients into mush).
     - *For sauces/creams requiring hot emulsion* (e.g. *«cook 10 min / 100°C / speed 4»*): Split into:
       - **Phase 1 (Cooking)**: 10 min / 100°C / speed 3 (cooks through thoroughly).
       - **Phase 2 (Emulsion / Finishing)**: 20–30 s / speed 4–5 with heating disabled (`tempC = 0`). The bowl remains near-boiling, creating the requested emulsion without triggering the safety interlock.

4. **No-Stir High Temperature Guard (`speed == 0` + `tempC > 120°C`)**:
   - *Physical limit*: Heating above 120°C (up to 130°C) without blade movement causes immediate bottom scorching and local thermal trips.
   - *Protocol*: Rather than rejecting the step or capping temperature at 120°C, set **`speed = 1, reverse = true`** (gentle reverse rotation). The blunt side of the knife prevents burning while keeping fragile ingredients intact.

5. **Reverse High Speed Normalization (`reverse == true` + `speed > 3`)**:
   - *Physical limit*: Counter-clockwise motor torque on the blunt blade edge is restricted to speeds 1–3 to prevent gear stripping.
   - *Protocol*: Soft-clamp `speed = 3` with `reverse = true`.

---

## 9. Post-Build Automated Integrity Verification

Before deployment, pipelines MUST run an automated validation pass verifying:
1. **User Version Pragma**: Ensure `PRAGMA user_version == 1`.
2. **Table Completeness**: Verify existence of `recipes`, `favorites`, `adjustments`, `cooked`, `android_metadata`.
3. **Category Sanity**: Assert 100% of recipes have a non-empty `category` belonging to the canonical list.
4. **Safety Compliance**: Assert 0 safety violations across all `steps[].machine` definitions (`violations == 0`).
5. **Scale Label Hygiene**: Verify zero empty, truncated (`(`), or raw untranslated strings in `steps[].weigh.label`.
6. **JSON Parseability**: Ensure all records deserialize cleanly through `RecipeCodec`.

