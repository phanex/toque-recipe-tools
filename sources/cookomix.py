import urllib.request
import json
import ssl
import re

ctx = ssl._create_unverified_context()

def parse_iso_duration(duration_str):
    if not duration_str or not isinstance(duration_str, str):
        return 0
    # Example: PT30M, PT1H15M
    hours = 0
    minutes = 0
    m_h = re.search(r"(\d+)H", duration_str)
    if m_h:
        hours = int(m_h.group(1))
    m_m = re.search(r"(\d+)M", duration_str)
    if m_m:
        minutes = int(m_m.group(1))
    return hours * 60 + minutes

def parse_cookomix_html(html, source_url=""):
    lds = re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
    recipe_meta = None
    for ld in lds:
        try:
            data = json.loads(ld.strip())
            graph = data.get("@graph", [data])
            for item in graph:
                if item.get("@type") == "Recipe":
                    recipe_meta = item
                    break
        except Exception:
            continue

    if not recipe_meta:
        return None

    title = recipe_meta.get("name", "").strip()
    if not title:
        return None

    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", title.lower()).strip("-")
    toque_id = f"cookomix-{slug}"

    # Image
    image_url = ""
    img = recipe_meta.get("image")
    if isinstance(img, list) and img:
        image_url = img[0]
    elif isinstance(img, dict):
        image_url = img.get("url", "")
    elif isinstance(img, str):
        image_url = img

    # Ingredients
    items = []
    for raw_ing in recipe_meta.get("recipeIngredient", []):
        m = re.match(r"^(\d+(?:[.,]\d+)?\s*(?:g|kg|ml|cl|l|c\.\s*à\s*soupe|c\.\s*à\s*café|pincée)?)\s*(?:de\s+|d'|du\s+)?(.*)$", raw_ing.strip(), re.IGNORECASE)
        if m:
            qty_unit = m.group(1).strip()
            name = m.group(2).strip()
            items.append({"name": name, "qty": qty_unit, "unit": "", "note": ""})
        else:
            items.append({"name": raw_ing.strip(), "qty": "", "unit": "", "note": ""})

    # Instructions
    steps = []
    instructions = recipe_meta.get("recipeInstructions", [])
    for inst in instructions:
        text = ""
        if isinstance(inst, dict):
            text = inst.get("text", "")
        elif isinstance(inst, str):
            text = inst

        text = re.sub(r"<[^>]+>", " ", text).strip()
        if not text:
            continue

        # Simple appliance parameter extractor from French Thermomix recipe steps
        # E.g. "Régler 5 min / 100°C / vitesse 2" or "10 sec / vitesse 5"
        machine = None
        m_params = re.search(r"(\d+)\s*(min|sec).*?(\d+)\s*°C.*?vitesse\s*(\d+)", text, re.IGNORECASE)
        if m_params:
            dur = int(m_params.group(1)) * (60 if m_params.group(2).lower() == "min" else 1)
            temp = int(m_params.group(3))
            spd = int(m_params.group(4))
            machine = {
                "program": "manuel",
                "seconds": dur,
                "speed": spd,
                "tempC": temp,
                "reverse": bool("sens inverse" in text.lower()),
                "accessory": "blade",
                "pulses": 0
            }

        steps.append({
            "text": text,
            "machine": machine,
            "weigh": None,
            "needsReview": machine is not None
        })

    prep = parse_iso_duration(recipe_meta.get("prepTime"))
    total = parse_iso_duration(recipe_meta.get("totalTime"))

    return {
        "id": toque_id,
        "title": title,
        "category": "Cookomix",
        "tags": ["cookomix", "community"],
        "servings": 4,
        "prepMinutes": prep,
        "totalMinutes": total,
        "difficulty": 1,
        "source": "imported",
        "image": f"{toque_id}.jpg" if image_url else "",
        "image_url": image_url,
        "favorite": False,
        "notes": recipe_meta.get("description", ""),
        "author": "Cookomix Community",
        "rating": 4.5,
        "ratingCount": 10,
        "ingredients": [{"group": "", "items": items}],
        "steps": steps,
        "updated": 0
    }

def fetch_cookomix_recipe(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
        html = resp.read().decode("utf-8", errors="ignore")
    return parse_cookomix_html(html, source_url=url)
