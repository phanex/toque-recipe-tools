import sqlite3
import json
import os
import subprocess

def init_database(db_path, locale="uk_UA"):
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    conn.isolation_level = None  # Crucial for PRAGMA statements to take effect
    cur = conn.cursor()

    cur.execute("PRAGMA user_version = 1;")
    cur.execute("""
        CREATE TABLE recipes (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            json TEXT NOT NULL,
            updated INTEGER NOT NULL
        );
    """)
    cur.execute("CREATE TABLE favorites (id TEXT PRIMARY KEY);")
    cur.execute("CREATE TABLE IF NOT EXISTS adjustments (id TEXT PRIMARY KEY, json TEXT NOT NULL);")
    cur.execute("CREATE TABLE IF NOT EXISTS cooked (id TEXT PRIMARY KEY, count INTEGER NOT NULL, last INTEGER NOT NULL);")
    cur.execute("CREATE TABLE android_metadata (locale TEXT);")
    cur.execute("INSERT INTO android_metadata VALUES (?);", (locale,))

    conn.commit()
    return conn

def insert_recipes(conn, recipes):
    cur = conn.cursor()
    rows = []
    for r in recipes:
        r_id = r.get("id")
        title = r.get("title", "")
        updated = r.get("updated", 0)
        r_json = json.dumps(r, ensure_ascii=False)
        rows.append((r_id, title, r_json, updated))

    cur.executemany("INSERT OR REPLACE INTO recipes (id, title, json, updated) VALUES (?, ?, ?, ?);", rows)
    conn.commit()
    print(f"Inserted {len(rows)} recipes into database.")

def deploy_to_device(adb_bin, device_target, db_path, images_dir=None):
    base_cmd = [adb_bin]
    if device_target:
        base_cmd.extend(["-s", device_target])

    print("Checking connection to device...")
    subprocess.run(base_cmd + ["get-state"], check=True)

    print(f"Staging {db_path} to device (/sdcard/)...")
    subprocess.run(base_cmd + ["push", db_path, "/sdcard/recettes_staged.db"], check=True)

    if images_dir and os.path.exists(images_dir):
        print(f"Staging images from {images_dir}...")
        subprocess.run(base_cmd + ["shell", "mkdir -p /sdcard/toque_images_staged"], check=True)
        subprocess.run(base_cmd + ["push", f"{images_dir}/.", "/sdcard/toque_images_staged/"], check=True)

    print("Configuring permissions and SELinux MCS categories...")
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
    subprocess.run(base_cmd + ["shell", f"su -c '{fix_permissions_cmd}'"], check=True)
    print("Deployment completed successfully. Toque database is ready and AutoSync is disabled.")
