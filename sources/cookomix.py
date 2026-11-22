import urllib.request
import json
import ssl
import re
import html

ctx = ssl._create_unverified_context()

# Emoji removal regex (surrogate pairs and emoji symbols)
EMOJI_REGEX = re.compile(
    r"[\U00010000-\U0010ffff"  # Supplemental symbols, pictographs, flags
    r"\u2600-\u27bf"           # Miscellaneous symbols and dingbats
    r"\u2300-\u23ff"           # Miscellaneous technical
    r"\u2b50-\u2b55"           # Stars and shapes
    r"\u200d\ufe0f]+",         # Zero-width joiner & variant selector
    flags=re.UNICODE
)

def strip_emojis(text):
    if not text:
        return ""
    clean = EMOJI_REGEX.sub("", text)
    return re.sub(r"\s+", " ", clean).strip()

def clean_text(raw):
    if not raw:
        return ""
    unescaped = html.unescape(raw)
    no_html = re.sub(r"<[^>]+>", " ", unescaped)
    no_emoji = strip_emojis(no_html)
    return re.sub(r"\s+", " ", no_emoji).strip()

def clean_title(title_raw):
    t = clean_text(title_raw)
    # Strip trailing " au thermomix" or " thermomix"
    t = re.sub(r"\s+(?:au\s+)?thermomix\s*$", "", t, flags=re.IGNORECASE)
    return t.strip()

def parse_iso_duration(duration_str):
    if not duration_str or not isinstance(duration_str, str):
        return 0
    hours = 0
    minutes = 0
    m_h = re.search(r"(\d+)H", duration_str)
    if m_h:
        hours = int(m_h.group(1))
    m_m = re.search(r"(\d+)M", duration_str)
    if m_m:
        minutes = int(m_m.group(1))
    return hours * 60 + minutes

def parse_cookomix_html(raw_html, source_url=""):
    lds = re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', raw_html, re.DOTALL)
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

    raw_title = recipe_meta.get("name", "").strip()
    title = clean_title(raw_title)
    if not title:
        return None

    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", title.lower()).strip("-")
    toque_id = f"cookomix-{slug}"

    # Extract author and clean emojis
    author_name = "Cookomix Community"
    author_field = recipe_meta.get("author")
    if isinstance(author_field, dict):
        author_name = author_field.get("name", author_name)
    elif isinstance(author_field, list) and author_field:
        first = author_field[0]
        if isinstance(first, dict):
            author_name = first.get("name", author_name)
        elif isinstance(first, str):
            author_name = first
    elif isinstance(author_field, str):
        author_name = author_field
    author_name = clean_text(author_name)

    # Category
    category = "Autre"
    cat_field = recipe_meta.get("recipeCategory")
    if isinstance(cat_field, list) and cat_field:
        category = cat_field[0]
    elif isinstance(cat_field, str):
        category = cat_field
    category = clean_text(category)

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
        raw_s = clean_text(raw_ing)
        m = re.match(r"^(\d+(?:[.,]\d+)?\s*(?:grammes?|g|kg|ml|cl|l|c\.\s*à\s*soupe|c\.\s*à\s*café|pincée[s]?|sachet[s]?|morceau[x]?|tranche[s]?|gousse[s]?)?)\s*(?:de\s+|d'|du\s+|des\s+)?(.*)$", raw_s, re.IGNORECASE)
        if m:
            qty_unit = m.group(1).strip()
            name = m.group(2).strip()
            items.append({"name": name, "qty": qty_unit, "unit": "", "note": ""})
        else:
            items.append({"name": raw_s, "qty": "", "unit": "", "note": ""})

    # Instructions
    steps = []
    instructions = recipe_meta.get("recipeInstructions", [])
    for inst in instructions:
        text = ""
        if isinstance(inst, dict):
            text = inst.get("text", "")
        elif isinstance(inst, str):
            text = inst

        text = clean_text(text)
        if not text:
            continue

        # Machine parameters extraction
        machine = None
        program = "manuel"
        seconds = 0
        speed = 0
        tempC = 0
        reverse = bool("sens inverse" in text.lower())

        # Check if step is for oven / baking ("le four", "préchauffer le four") -> NOT a robot step!
        is_oven = bool(re.search(r"\b(?:four|préchauffer|enfourner|cuire au four)\b", text, re.IGNORECASE))

        # Check if step is just dough resting ("réserver", "laisser reposer") without active mixing
        is_passive_rest = bool(re.search(r"^(?:réserver|laisser reposer|faire lever)\b", text, re.IGNORECASE)) and not re.search(r"\bvitesse\b", text, re.IGNORECASE)

        if not is_oven and not is_passive_rest:
            # Check duration - support composite durations e.g. "1 min 30 sec"
            m_time_segment = re.search(r"(?:(\d+)\s*(?:h|heure[s]?)\s*)?(?:(\d+)\s*min\s*)?(?:(\d+)\s*sec)?", text, re.IGNORECASE)
            total_sec = 0
            for tm in re.finditer(r"(\d+)\s*(h|min|sec)", text, re.IGNORECASE):
                val = int(tm.group(1))
                u = tm.group(2).lower()
                if u == "h":
                    total_sec += val * 3600
                elif u == "min":
                    total_sec += val * 60
                elif u == "sec":
                    total_sec += val
            seconds = total_sec

            # Check temperature (Appliance limit is 130°C)
            m_temp = re.search(r"(\d+)\s*°C", text)
            if m_temp:
                cand_temp = int(m_temp.group(1))
                if cand_temp <= 130:
                    tempC = cand_temp
            elif re.search(r"\bvaroma\b", text, re.IGNORECASE):
                tempC = 120

            # Check speed / knead
            if re.search(r"\b(?:mode\s+)?pétrin\b", text, re.IGNORECASE) or text.lower().startswith("pétrir"):
                program = "petrir"
            elif re.search(r"\bvapeur\b", text, re.IGNORECASE) and tempC == 120:
                program = "vapeur"
            else:
                m_spd = re.search(r"vitesse\s*(\d+(?:[.,]\d+)?)", text, re.IGNORECASE)
                if m_spd:
                    spd_f = float(m_spd.group(1).replace(",", "."))
                    speed = max(1, min(10, int(round(spd_f))))

            if (seconds > 0 or speed > 0 or tempC > 0) and (speed > 0 or tempC > 0 or program != "manuel"):
                machine = {
                    "program": program,
                    "seconds": seconds,
                    "speed": speed,
                    "tempC": tempC,
                    "reverse": reverse,
                    "accessory": "blade",
                    "pulses": 0
                }

        # Weigh scale extraction from instruction text
        weigh = None
        m_weigh = re.search(r"(?:mettre|ajouter|peser)\s+(\d+)\s*(?:grammes?|g)\s+(?:de\s+|d'|du\s+|des\s+)?([^,.;]+)", text, re.IGNORECASE)
        if m_weigh:
            grams = int(m_weigh.group(1))
            ing_name = m_weigh.group(2).strip()
            # clean trailing words like "dans le bol"
            ing_name = re.sub(r"\s+dans\s+.*$", "", ing_name, flags=re.IGNORECASE).strip()
            # clean unclosed parentheses e.g. "Blancs d'oeufs (environ le blanc de" -> "Blancs d'oeufs"
            ing_name = re.sub(r"\s*\([^)]*$", "", ing_name).strip()
            if 0 < grams <= 5000 and len(ing_name) >= 3:
                weigh = {"label": ing_name[:35].capitalize(), "grams": grams}

        steps.append({
            "text": text,
            "machine": machine,
            "weigh": weigh,
            "needsReview": False
        })

    prep = parse_iso_duration(recipe_meta.get("prepTime"))
    total = parse_iso_duration(recipe_meta.get("totalTime"))

    return {
        "id": toque_id,
        "title": title,
        "category": category,
        "tags": ["Cookomix", "CM"],
        "servings": 4,
        "prepMinutes": prep,
        "totalMinutes": total,
        "difficulty": 1,
        "source": "imported",
        "image": f"{toque_id}.jpg" if image_url else "",
        "image_url": image_url,
        "favorite": False,
        "notes": clean_text(recipe_meta.get("description", "")),
        "author": author_name,
        "rating": 4.5,
        "ratingCount": 10,
        "ingredients": [{"group": "", "items": items}],
        "steps": steps,
        "updated": 0
    }

def fetch_cookomix_recipe(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
        html_content = resp.read().decode("utf-8", errors="ignore")
    return parse_cookomix_html(html_content, source_url=url)
