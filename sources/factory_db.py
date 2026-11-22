import sqlite3
import json

def parse_stock_factory_db(sqlite_path):
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    recipes = []
    try:
        cur.execute("SELECT * FROM RECIPE;")
        rows = cur.fetchall()
        for row in rows:
            r_id = f"stock_{row['ID']}"
            title = row["NAME"]
            recipes.append({
                "id": r_id,
                "title": title,
                "category": "Stock",
                "tags": ["stock", "factory"],
                "servings": 4,
                "prepMinutes": 0,
                "totalMinutes": 0,
                "difficulty": 1,
                "source": "imported",
                "image": f"{r_id}.jpg",
                "favorite": False,
                "notes": "",
                "author": "Silvercrest",
                "rating": 5.0,
                "ratingCount": 1,
                "ingredients": [],
                "steps": [],
                "updated": 0
            })
    except Exception as e:
        print(f"Error reading stock factory db: {e}")
    finally:
        conn.close()

    return recipes
