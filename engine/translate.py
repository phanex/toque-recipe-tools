import os
import json
import urllib.request
import urllib.parse
import ssl
import time
import threading
from concurrent.futures import ThreadPoolExecutor

ctx = ssl._create_unverified_context()

class TranslationEngine:
    def __init__(self, cache_file="cache/translations.json"):
        self.cache_file = cache_file
        self.cache_lock = threading.Lock()
        self.cache = {}
        os.makedirs(os.path.dirname(cache_file) or ".", exist_ok=True)
        self._load_cache()

    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
            except Exception:
                self.cache = {}

    def save_cache(self):
        with self.cache_lock:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)

    def _fetch_chunk(self, task):
        chunk_idx, items, sl, tl = task
        lines = [x[1] for x in items]
        q = urllib.parse.quote("\n".join(lines))
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={sl}&tl={tl}&dt=t&q={q}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        results = {}
        success = False

        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, context=ctx, timeout=12) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                full_trans = "".join(p[0] for p in data[0] if p[0])
                trans_lines = full_trans.split("\n")
                if len(trans_lines) == len(lines):
                    for (orig, _), tr in zip(items, trans_lines):
                        results[f"{sl}:{tl}:{orig}"] = tr.strip()
                else:
                    for orig, c_line in items:
                        q_s = urllib.parse.quote(c_line)
                        u_s = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={sl}&tl={tl}&dt=t&q={q_s}"
                        r_s = urllib.request.Request(u_s, headers={"User-Agent": "Mozilla/5.0"})
                        with urllib.request.urlopen(r_s, context=ctx, timeout=10) as s_resp:
                            s_data = json.loads(s_resp.read().decode("utf-8"))
                            results[f"{sl}:{tl}:{orig}"] = "".join(p[0] for p in s_data[0] if p[0]).strip()
                        time.sleep(0.04)
                success = True
                break
            except Exception:
                time.sleep(1.0 * (attempt + 1))

        if not success:
            for orig, _ in items:
                results[f"{sl}:{tl}:{orig}"] = orig

        return chunk_idx, results

    def translate_batch(self, phrases, sl, tl, max_workers=8):
        needed = [p for p in phrases if f"{sl}:{tl}:{p}" not in self.cache and p.strip()]
        if not needed:
            return

        print(f"Translating {len(needed)} unique phrases ({sl} -> {tl}) using {max_workers} threads...")
        
        chunks = []
        cur_chunk = []
        cur_chars = 0
        for p in needed:
            safe = p.replace("\n", " ")
            if cur_chars + len(safe) > 1200 or len(cur_chunk) >= 20:
                chunks.append(cur_chunk)
                cur_chunk = []
                cur_chars = 0
            cur_chunk.append((p, safe))
            cur_chars += len(safe)
        if cur_chunk:
            chunks.append(cur_chunk)

        tasks = [(i, ch, sl, tl) for i, ch in enumerate(chunks)]
        done = 0
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for _, res in pool.map(self._fetch_chunk, tasks):
                with self.cache_lock:
                    self.cache.update(res)
                done += 1
                if done % 10 == 0 or done == len(chunks):
                    print(f"Progress: {done}/{len(chunks)} chunks completed")
                    self.save_cache()

        self.save_cache()

    def get(self, text, sl, tl):
        if not text:
            return ""
        return self.cache.get(f"{sl}:{tl}:{text}", text)
