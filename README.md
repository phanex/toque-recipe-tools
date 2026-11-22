# Toque Recipe Tools 🍳

Universal recipe ingestion, multilingual translation, media optimizer, and SQLite database deployment toolkit for the [Toque](https://github.com/Wuki60/MrCuisineVibeConnect) launcher (Silvercrest Monsieur Cuisine Connect / SKMC 1200).

---

## Overview

Toque is an open-source, lightweight launcher and machine controller designed for smart kitchen appliances. While Toque itself remains strictly offline and lightweight, **Toque Recipe Tools** provides an external desktop pipeline to:

1. **Ingest Recipes from Multiple Sources**:
   - **Lidl MC Online**: Structured JSON catalog with studio photography.
   - **Factory Database**: Original `/data/data/de.silpion.mc2/databases/Recipes` extracted from device firmware.
   - **Cookomix (Beta / Community Driver)**: Public recipe schema parser for Thermomix / Monsieur Cuisine community recipes.
2. **Translate to Any Target Language**:
   - Batch translation engine with disk-backed phrase caching.
   - Full JSON traversal: titles, ingredients, notes, and clean culinary noun labels for scale weigh steps.
3. **Optimize Embedded Media**:
   - Downscales photographs to 800×480 px (matching the 7" 1024×600 aspect ratio).
   - Reduces multi-gigabyte collections to ~90 KB per recipe without visual degradation on embedded screens.
4. **Build and Deploy SQLite Database**:
   - Generates production-ready `recettes.db`.
   - Sets required `PRAGMA user_version = 1`.
   - Pre-initializes `adjustments`, `cooked`, `favorites`, and `android_metadata`.
   - Configures Android SELinux Multi-Category Security (MCS) sandbox permissions.

---

## Quick Start

### 1. Requirements
- Python 3.9+
- ADB (Android Debug Bridge) connected to the appliance via Wi-Fi or USB.

```bash
git clone https://github.com/phanex/toque-recipe-tools.git
cd toque-recipe-tools
pip install -r requirements.txt
```

### 2. Build & Translate a Database
To build an offline database translated into your chosen language (e.g., Ukrainian `uk`, German `de`, Czech `cs`, etc.):

```bash
python pipeline.py --source mconline --source-lang pl --target-lang uk --output recettes.db
```

### 3. Deploy to Device
```bash
python pipeline.py --deploy recettes.db --device-ip 192.168.0.218:5555
```

---

## Critical Device Configuration: Disable Auto-Sync

> [!WARNING]
> By default, Toque enables automatic nightly catalog synchronization (`autoSync = true`).
> Because custom/third-party translations do not exist on manufacturer servers, Toque's background sync will eventually overwrite custom databases with official stock recipes (French/German/Polish).

### Disabling via UI:
In Toque: **Settings (Налаштування)** › under the Lidl section, toggle off **«Synchro automatique chaque nuit»**.

### Disabling via ADB:
```bash
adb shell "su -c 'sed -i \"s/<boolean name=\\\"autoSync\\\" value=\\\"true\\\" \/>/<boolean name=\\\"autoSync\\\" value=\\\"false\\\" \/>/g\" /data/data/app.toque/shared_prefs/toque.xml'"
```

---

## Architecture & Adapters

```
toque-recipe-tools/
├── pipeline.py            # Main CLI orchestrator
├── sources/               # Source ingestion adapters
│   ├── mconline.py        # Lidl MC Online API adapter (Stable)
│   ├── factory_db.py      # Original firmware SQLite adapter (Stable)
│   └── cookomix.py        # Cookomix JSON-LD adapter (Beta)
├── engine/                # Core processing engine
│   ├── translate.py       # Cached multi-threaded translation
│   ├── database.py        # SQLite builder & schema enforcement
│   └── media.py           # Image downscaling & compression
└── SKILL.md               # Antigravity / Cursor / Claude agent protocol
```

---

## License
MIT License. Created by the community for Monsieur Cuisine Connect & Toque enthusiasts.
