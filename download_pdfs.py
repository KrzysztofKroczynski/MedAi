import requests
import time
import os

OUTPUT_DIR = r"C:\Users\Krzysztof\Documents\MGR\TEG\MedAi\data\pdfs"
BASE_URL = "https://dailymed.nlm.nih.gov/dailymed/services/v2"
PDF_URL = "https://dailymed.nlm.nih.gov/dailymed/downloadpdffile.cfm"
DELAY = 0.3

os.makedirs(OUTPUT_DIR, exist_ok=True)

DRUGS = [
    # Pain/inflammation
    "ibuprofen", "aspirin", "acetaminophen", "naproxen", "diclofenac",
    "tramadol", "celecoxib",
    # Antibiotics
    "amoxicillin", "ciprofloxacin", "azithromycin", "doxycycline", "metronidazole",
    # Cardiovascular
    "atorvastatin", "metoprolol", "amlodipine", "lisinopril", "warfarin",
    "clopidogrel", "ramipril",
    # Diabetes
    "metformin", "insulin glargine", "sitagliptin",
    # GI
    "omeprazole", "pantoprazole", "ranitidine", "loperamide",
    # Respiratory
    "albuterol", "montelukast", "fluticasone",
    # Mental health
    "sertraline", "fluoxetine", "amitriptyline", "diazepam",
    # Other
    "levothyroxine", "prednisone", "gabapentin", "furosemide", "methotrexate",
]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (research project)"
})

downloaded = []
failed = []

def search_drug(drug_name):
    """Search for a drug and return list of (setid, title) tuples."""
    url = f"{BASE_URL}/spls.json"
    params = {"drug_name": drug_name, "pagesize": 3}
    try:
        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("data", [])
        entries = [(r.get("setid"), r.get("title", "")) for r in results if r.get("setid")]
        return entries
    except Exception as e:
        print(f"  [SEARCH ERROR] {drug_name}: {e}")
        return []

def download_pdf(setid, drug_name, index):
    """Download PDF using the downloadpdffile.cfm endpoint."""
    try:
        resp = session.get(PDF_URL, params={"setId": setid}, timeout=60, stream=True)
        if resp.status_code == 200 and "pdf" in resp.headers.get("Content-Type", "").lower():
            safe_name = drug_name.replace(" ", "_").replace("/", "_")
            filename = f"{safe_name}_{index+1}_{setid[:8]}.pdf"
            filepath = os.path.join(OUTPUT_DIR, filename)
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            size = os.path.getsize(filepath)
            if size > 5000:  # at least 5KB = real PDF
                print(f"  [OK] {filename} ({size//1024} KB)")
                return filepath
            else:
                os.remove(filepath)
                print(f"  [SKIP] File too small ({size} bytes)")
                return None
        else:
            print(f"  [FAIL] status={resp.status_code}, content-type={resp.headers.get('Content-Type','')}")
            return None
    except Exception as e:
        print(f"  [ERROR] {e}")
        return None

def process_drug(drug_name):
    print(f"\n=== {drug_name} ===")
    entries = search_drug(drug_name)
    time.sleep(DELAY)

    if not entries:
        print(f"  No results found.")
        failed.append(drug_name)
        return

    print(f"  Found {len(entries)} result(s)")
    for i, (setid, title) in enumerate(entries):
        short_title = title[:60] + "..." if len(title) > 60 else title
        print(f"  [{i+1}] {short_title}")
        filepath = download_pdf(setid, drug_name, i)
        time.sleep(DELAY)
        if filepath:
            downloaded.append(filepath)
        else:
            failed.append(f"{drug_name}[{i+1}]")

# Main
print(f"Saving PDFs to: {OUTPUT_DIR}")
print(f"Drugs to process: {len(DRUGS)}")
print("=" * 60)

for drug in DRUGS:
    try:
        process_drug(drug)
    except Exception as e:
        print(f"  [FATAL] {drug}: {e}")
        failed.append(drug)

print("\n" + "=" * 60)
print(f"COMPLETE: {len(downloaded)} PDFs downloaded, {len(failed)} failed/skipped")
print(f"\nOutput directory: {OUTPUT_DIR}")
if downloaded:
    print(f"\nAll {len(downloaded)} downloaded files:")
    for f in downloaded:
        size = os.path.getsize(f)
        print(f"  {os.path.basename(f)} ({size//1024} KB)")
