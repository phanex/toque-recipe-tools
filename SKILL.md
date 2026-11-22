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
