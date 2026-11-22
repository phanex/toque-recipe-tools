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

CANONICAL_CATEGORIES = [
    "Випічка",
    "Десерти",
    "Основні страви",
    "Супи",
    "Закуски",
    "Гарніри",
    "Соуси та пасти",
    "Салати",
    "Сніданки",
    "Напої",
    "Джеми та варення",
    "Веганське",
    "Все в одному",
    "Вечеря"
]

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
    t = re.sub(r"\s+(?:au\s+)?thermomix[®™]?\s*$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*\((?:au\s+)?thermomix[®™]?\)\s*$", "", t, flags=re.IGNORECASE)
    return t.strip()

def clean_weigh_label(label):
    if not label:
        return ""
    lbl = clean_text(label)
    # Strip unclosed parentheses e.g. "Blancs d'oeufs (environ le blanc de" -> "Blancs d'oeufs"
    lbl = re.sub(r"\s*\([^)]*$", "", lbl).strip()
    # Strip balanced parentheses if they wrap extra notes
    lbl = re.sub(r"\s*\([^)]*\)", "", lbl).strip()
    # Strip any stray parentheses
    lbl = lbl.replace("(", " ").replace(")", " ")
    # Normalize whitespace and trailing punctuation
    lbl = re.sub(r"\s+", " ", lbl).strip(" ,.;:-_")
    if not lbl:
        return ""
    return lbl[:35].strip().capitalize()

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

def map_to_canonical_category(raw_categories, title="", context_hint=""):
    combined = " ".join([c for c in raw_categories if c] + [context_hint, title]).lower()
    
    # 1. Baking (Випічка)
    if any(k in combined for k in [
        "pain", "pains", "baguette", "brioche", "viennoiserie", "viennoiseries",
        "boulange", "boulangerie", "pâte à pain", "pâte levée", "fougasse", "batbout",
        "pain de mie", "bun", "buns"
    ]):
        return "Випічка"

    # 2. Soups (Супи)
    if any(k in combined for k in [
        "soupe", "soupes", "potage", "velouté", "veloute", "bouillon",
        "gazpacho", "gaspacho", "mouliné"
    ]):
        return "Супи"

    # 3. Salads (Салати)
    if any(k in combined for k in [
        "salade", "salades", "taboulé", "taboule"
    ]):
        return "Салати"

    # 4. Sauces & spreads (Соуси та пасти)
    if any(k in combined for k in [
        "sauce", "sauces", "pesto", "tartinade", "mayonnaise", "ketchup",
        "béchamel", "vinaigrette", "dip", "houmous", "guacamole", "tapenade", "chutney"
    ]):
        return "Соуси та пасти"

    # 5. Jams & preserves (Джеми та варення)
    if any(k in combined for k in [
        "confiture", "confitures", "gelée", "gelee", "compote", "compotes",
        "marmelade", "pâte à tartiner", "curd"
    ]):
        return "Джеми та варення"

    # 6. Beverages (Напої)
    if any(k in combined for k in [
        "boisson", "boissons", "cocktail", "cocktails", "smoothie", "smoothies",
        "jus", "sirop", "limonade", "chocolat chaud", "infusion", "thé", "café"
    ]):
        return "Напої"

    # 7. Breakfast (Сніданки)
    if any(k in combined for k in [
        "petit-déjeuner", "petit dejeuner", "brunch", "pancake", "pancakes",
        "crêpe", "crepe", "crêpes", "crepes", "gaufre", "gaufres", "granola", "muesli", "porridge"
    ]):
        return "Сніданки"

    # 8. Desserts (Десерти)
    if any(k in combined for k in [
        "dessert", "desserts", "pâtisserie", "patisserie", "pâtisseries", "patisseries",
        "gâteau", "gateau", "gâteaux", "gateaux", "tarte", "tartes", "biscuit", "biscuits",
        "cookie", "cookies", "crème", "creme", "mousse", "flan", "flans", "glace", "glaces",
        "sorbet", "sorbets", "chocolat", "muffin", "muffins", "confiserie", "confiseries",
        "clafoutis", "fondant", "cheesecake", "brownie", "brownies"
    ]):
        return "Десерти"

    # 9. Appetizers (Закуски)
    if any(k in combined for k in [
        "apéritif", "aperitif", "apéro", "apero", "entrée", "entree", "entrées", "entrees",
        "terrine", "terrines", "amuse-bouche", "bouchée", "bouchee", "bouchées", "bouchees",
        "tartine", "crostini", "verrine", "verrines", "feuilleté", "feuillete", "feuilletés",
        "rillons", "rillettes"
    ]):
        return "Закуски"

    # 10. Side dishes (Гарніри)
    if any(k in combined for k in [
        "accompagnement", "purée", "puree", "purées", "légumes", "legumes",
        "pommes de terre", "épinards", "haricots", "frites"
    ]):
        return "Гарніри"

    # 11. Vegan (Веганське)
    if any(k in combined for k in [
        "vegan", "végétalien", "vegetalien", "végane", "vegane"
    ]):
        return "Веганське"

    # 12. Main dishes (Основні страви)
    if any(k in combined for k in [
        "plat", "plats", "plat principal", "viande", "viandes", "poisson", "poissons",
        "poulet", "boeuf", "porc", "veau", "pâtes", "pates", "riz", "risotto",
        "ragoût", "ragout", "gratin", "gratins", "quiche", "quiches", "pizza", "pizzas",
        "lasagne", "lasagnes", "hachis", "curry", "tajine", "chili", "dhal"
    ]):
        return "Основні страви"

    # 13. One-Pot (Все в одному)
    if any(k in combined for k in ["one pot", "one-pot", "tout-en-un"]):
        return "Все в одному"

    # 14. Dinner (Вечеря)
    if any(k in combined for k in ["dîner", "diner", "souper"]):
        return "Вечеря"

    return "Основні страви"

def parse_cookomix_html(raw_html, source_url="", context_hint=""):
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
    if not author_name:
        author_name = "Cookomix Community"

    # Raw Category extraction
    raw_cats = []
    cat_field = recipe_meta.get("recipeCategory")
    if isinstance(cat_field, list):
        for c in cat_field:
            raw_cats.append(clean_text(str(c)))
    elif isinstance(cat_field, str):
        raw_cats.append(clean_text(cat_field))

    # Canonical Category mapping
    canonical_cat = map_to_canonical_category(raw_cats, title=title, context_hint=context_hint)

    # Secondary tags
    tags = ["Cookomix", "CM"]
    for rc in raw_cats:
        if rc and rc not in tags and len(rc) <= 30:
            tags.append(rc)

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

        # Machine step filtering:
        # 1. Oven preheating / baking ("four", "préchauffer", "> 130°C") -> NOT an appliance step!
        is_oven = bool(re.search(r"\b(?:four|préchauffer|enfourner|cuire au four)\b", text, re.IGNORECASE))
        m_temp_check = re.search(r"(\d+)\s*°C", text)
        if m_temp_check and int(m_temp_check.group(1)) > 130:
            is_oven = True

        # 2. Passive dough resting / rising ("réserver", "laisser reposer") without active appliance mixing
        is_passive_rest = bool(re.search(r"\b(?:réserver|laisser reposer|faire lever)\b", text, re.IGNORECASE)) and not re.search(r"\bvitesse\b", text, re.IGNORECASE)

        machine = None
        if not is_oven and not is_passive_rest:
            program = "manuel"
            seconds = 0
            speed = 0
            tempC = 0
            reverse = bool("sens inverse" in text.lower())

            # Check duration - support composite durations e.g. "1 min 30 sec"
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
            if m_temp_check:
                cand_temp = int(m_temp_check.group(1))
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
                # Safety Policy Clamping (appliance physical limits)
                if program == "manuel":
                    if tempC > 0 and speed > 3:
                        speed = 3
                    if reverse and speed > 3:
                        speed = 3
                    if speed == 0 and tempC > 120:
                        tempC = 120
                elif program == "petrir":
                    if speed > 4:
                        speed = 4
                    if tempC > 0:
                        tempC = 0
                elif program == "rissoler":
                    if seconds > 840:
                        seconds = 840
                    if speed > 1:
                        speed = 1
                elif program == "vapeur":
                    if speed > 1:
                        speed = 1

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
        m_weigh = re.search(r"(?:mettre|ajouter|peser|verser|incorporer)\s+(\d+)\s*(?:grammes?|g)\s+(?:de\s+|d'|du\s+|des\s+)?([^,.;\n]+)", text, re.IGNORECASE)
        if m_weigh:
            grams = int(m_weigh.group(1))
            ing_name = m_weigh.group(2).strip()
            # Clean trailing words
            ing_name = re.sub(r"\s+(?:dans|sur|avec|sous|puis|et)\s+.*$", "", ing_name, flags=re.IGNORECASE).strip()
            cleaned_lbl = clean_weigh_label(ing_name)
            if 0 < grams <= 5000 and len(cleaned_lbl) >= 2:
                weigh = {"label": cleaned_lbl, "grams": grams}

        # Smart Split: If kneading duration exceeds hardware limit (120 s), split into consecutive cycles
        if machine and machine.get("program") == "petrir" and machine.get("seconds", 0) > 120:
            total_sec = machine["seconds"]
            # Split into chunks of max 120 s
            chunks = []
            rem = total_sec
            while rem > 0:
                chunk = min(rem, 120)
                chunks.append(chunk)
                rem -= chunk

            for part_idx, chunk_sec in enumerate(chunks):
                sub_machine = dict(machine)
                sub_machine["seconds"] = chunk_sec
                sub_text = text
                if len(chunks) > 1:
                    sub_text = f"{text} (Частина {part_idx + 1}/{len(chunks)} — {chunk_sec} с)"
                steps.append({
                    "text": sub_text,
                    "machine": sub_machine,
                    "weigh": weigh if part_idx == 0 else None,
                    "needsReview": False
                })
        else:
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
        "category": canonical_cat,
        "tags": tags,
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

def fetch_cookomix_recipe(url, context_hint=""):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
        html_content = resp.read().decode("utf-8", errors="ignore")
    return parse_cookomix_html(html_content, source_url=url, context_hint=context_hint)
