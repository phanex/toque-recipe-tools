import os
import urllib.request
import ssl
from io import BytesIO

ctx = ssl._create_unverified_context()

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

def optimize_image(raw_bytes, target_size=(800, 480), quality=85):
    if not HAS_PIL:
        return raw_bytes

    try:
        with Image.open(BytesIO(raw_bytes)) as img:
            img = img.convert("RGB")
            img.thumbnail(target_size, Image.Resampling.LANCZOS)
            out = BytesIO()
            img.save(out, format="JPEG", quality=quality, optimize=True)
            return out.getvalue()
    except Exception:
        return raw_bytes

def download_and_optimize(url, dest_path, target_size=(800, 480), quality=85):
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1024:
        return True

    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            data = resp.read()
        optimized = optimize_image(data, target_size=target_size, quality=quality)
        with open(dest_path, "wb") as f:
            f.write(optimized)
        return True
    except Exception as e:
        print(f"Failed to fetch {url}: {e}")
        return False
