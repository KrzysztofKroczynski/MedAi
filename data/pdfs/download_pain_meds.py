import urllib.request
import urllib.parse
import json
import time
import os
import sys

OUTPUT_DIR = r"C:\Users\Krzysztof\Documents\MGR\TEG\MedAi\data\pdfs"

DRUGS = [
    ("oxycodone", "Oxycodone"),
    ("hydrocodone", "Hydrocodone"),
    ("codeine", "Codeine"),
    ("morphine", "Morphine"),
    ("fentanyl", "Fentanyl"),
    ("buprenorphine", "Buprenorphine"),
    ("oxymorphone", "Oxymorphone"),
    ("hydromorphone", "Hydromorphone"),
    ("tapentadol", "Tapentadol"),
    ("ketorolac", "Ketorolac"),
    ("meloxicam", "Meloxicam"),
    ("indomethacin", "Indomethacin"),
    ("piroxicam", "Piroxicam"),
    ("etodolac", "Etodolac"),
    ("flurbiprofen", "Flurbiprofen"),
    ("ketoprofen", "Ketoprofen"),
    ("mefenamic acid", "Mefenamic_acid"),
    ("diflunisal", "Diflunisal"),
    ("sulindac", "Sulindac"),
    ("tolmetin", "Tolmetin"),
    ("acetaminophen with codeine", "Acetaminophen_with_codeine"),
    ("lidocaine patch", "Lidocaine_patch"),
    ("capsaicin", "Capsaicin"),
    ("pregabalin", "Pregabalin"),
    ("duloxetine", "Duloxetine"),
    ("cyclobenzaprine", "Cyclobenzaprine"),
    ("methocarbamol", "Methocarbamol"),
    ("carisoprodol", "Carisoprodol"),
    ("baclofen", "Baclofen"),
    ("tizanidine", "Tizanidine"),
]

DELAY = 0.3
PAGESIZE = 3

downloaded = 0
skipped = 0
failed = 0

def already_have(prefix, n):
    path = os.path.join(OUTPUT_DIR, f"{prefix}_{n}_PIL.pdf")
    return os.path.exists(path)

def all_downloaded(prefix):
    return all(already_have(prefix, n) for n in range(1, PAGESIZE + 1))

def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

def download_pdf(setid, out_path):
    url = f"https://dailymed.nlm.nih.gov/dailymed/downloadpdffile.cfm?setId={setid}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    if len(data) < 1000:
        return False  # Likely not a real PDF
    with open(out_path, "wb") as f:
        f.write(data)
    return True

for drug_name, prefix in DRUGS:
    if all_downloaded(prefix):
        print(f"[SKIP] {prefix} - all 3 files already exist")
        skipped += 3
        continue

    # Check which ones we need
    needed = [n for n in range(1, PAGESIZE + 1) if not already_have(prefix, n)]
    if not needed:
        print(f"[SKIP] {prefix} - already complete")
        continue

    print(f"\n[FETCH] Searching DailyMed for: {drug_name}")
    search_url = (
        "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json"
        f"?drug_name={urllib.parse.quote(drug_name)}&pagesize={PAGESIZE}"
    )
    try:
        time.sleep(DELAY)
        data = fetch_json(search_url)
        results = data.get("data", [])
        print(f"  Found {len(results)} result(s)")
    except Exception as e:
        print(f"  [ERROR] Search failed: {e}")
        failed += len(needed)
        continue

    for idx, item in enumerate(results[:PAGESIZE], start=1):
        if idx not in needed:
            print(f"  [{prefix}_{idx}] already exists, skipping")
            skipped += 1
            continue

        setid = item.get("setid", "")
        title = item.get("title", "N/A")[:80]
        if not setid:
            print(f"  [{prefix}_{idx}] No setid, skipping")
            failed += 1
            continue

        out_path = os.path.join(OUTPUT_DIR, f"{prefix}_{idx}_PIL.pdf")
        print(f"  [{prefix}_{idx}] Downloading setid={setid} | {title}")
        try:
            time.sleep(DELAY)
            ok = download_pdf(setid, out_path)
            if ok:
                size_kb = os.path.getsize(out_path) // 1024
                print(f"    -> Saved ({size_kb} KB): {out_path}")
                downloaded += 1
            else:
                print(f"    -> Response too small, skipping")
                failed += 1
        except Exception as e:
            print(f"    -> [ERROR] Download failed: {e}")
            failed += 1

    # If fewer results than needed slots, mark those as failed
    for n in needed:
        if n > len(results):
            print(f"  [{prefix}_{n}] No result available (only {len(results)} found)")
            failed += 1

print(f"\n{'='*50}")
print(f"DONE: Downloaded={downloaded}, Skipped={skipped}, Failed/Missing={failed}")
