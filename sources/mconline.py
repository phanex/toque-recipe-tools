import urllib.request
import json
import ssl
import re

ctx = ssl._create_unverified_context()

API_URL = "https://mc-api.tecpal.com"
DEVICE = "MC2.0"

def clean_html(raw_html):
    if not raw_html:
        return ""
    clean = re.sub(r"<[^>]+>", " ", raw_html)
    return re.sub(r"\s+", " ", clean).strip()

def fetch_catalog_page(page, lang="pl-PL", page_size=100):
    url = f"{API_URL}/api/v2/recipes/page/{page}/size/{page_size}?filters%5BdeviceTypes%5D%5B%5D={DEVICE}&filters%5Bsource%5D%5B%5D=official"
    headers = {
        "Accept": "application/json",
        "Accept-Language": lang,
        "device-type": "web"
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))

def fetch_recipe_detail(recipe_id, lang="pl-PL"):
    url = f"{API_URL}/api/v2/recipes/{recipe_id}"
    headers = {
        "Accept": "application/json",
        "Accept-Language": lang,
        "device-type": "web"
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))

def parse_mconline_json(raw_data):
    recipe = raw_data.get("data", {}).get("recipe", raw_data)
    r_id = str(recipe.get("id"))
    title = recipe.get("name", "").strip()
    if not title:
        return None

    toque_id = f"web-{r_id}"
    image_url = ""
    media = recipe.get("media", [])
    if media and isinstance(media, list):
        image_url = media[0].get("fileUrl", "")

    # Parse ingredients
    groups = []
    main_items = []
    for ing in recipe.get("ingredients", []):
        name = ing.get("name", "").strip()
        amount = str(ing.get("amount", "")).strip()
        unit = ing.get("unit", "").strip()
        if name:
            main_items.append({"name": name, "qty": amount, "unit": unit, "note": ""})
    if main_items:
        groups.append({"group": "", "items": main_items})

    # Parse steps
    steps = []
    for s in recipe.get("instructions", []):
        text = clean_html(s.get("description", ""))
        machine = None
        weigh = None

        # Check for machine mode
        modes = s.get("deviceModes", [])
        if modes:
            m = modes[0]
            machine = {
                "program": m.get("mode", "manuel"),
                "seconds": int(m.get("duration", 0)),
                "speed": int(m.get("speed", 0)),
                "tempC": int(m.get("temperature", 0)),
                "reverse": bool(m.get("reverseDirection", False)),
                "accessory": "blade",
                "pulses": 0
            }

        # Check for weigh scale
        scale = s.get("scales", [])
        if scale:
            sc = scale[0]
            grams = int(sc.get("targetWeight", 0))
            if grams > 0:
                raw_label = sc.get("ingredientName") or ""
                weigh = {"label": raw_label.strip(), "grams": grams}

        if text or machine or weigh:
            steps.append({
                "text": text,
                "machine": machine,
                "weigh": weigh,
                "needsReview": False
            })

    return {
        "id": toque_id,
        "title": title,
        "category": recipe.get("categoryName", ""),
        "tags": [t.get("name") for t in recipe.get("tags", []) if t.get("name")],
        "servings": int(recipe.get("servings", 4) or 4),
        "prepMinutes": int(recipe.get("preparationTime", 0) or 0),
        "totalMinutes": int(recipe.get("totalTime", 0) or 0),
        "difficulty": int(recipe.get("difficulty", 1) or 1),
        "source": "imported",
        "image": f"{toque_id}.jpg" if image_url else "",
        "image_url": image_url,
        "favorite": False,
        "notes": clean_html(recipe.get("description", "")),
        "author": "Lidl / Monsieur Cuisine",
        "rating": float(recipe.get("rating", 0.0) or 0.0),
        "ratingCount": int(recipe.get("ratingCount", 0) or 0),
        "ingredients": groups,
        "steps": steps,
        "updated": int(recipe.get("updatedAtTimestamp", 0) or 0)
    }
