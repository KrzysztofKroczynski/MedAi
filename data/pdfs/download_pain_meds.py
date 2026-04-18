import urllib.request
import urllib.parse
import json
import time
import os

OUTPUT_DIR = r"C:\Users\Krzysztof\Documents\MGR\TEG\MedAi\data\pdfs"

# One PIL per drug. Output: {prefix}_PIL.pdf
# Skips drugs already present as {prefix}_PIL.pdf or {prefix}_1_PIL.pdf.
# Source: DailyMed (US FDA labeling database).

DRUGS = [
    # --- Benzodiazepines / anxiolytics / sleep ---
    # (diazepam already in corpus)
    ("alprazolam", "Alprazolam"),           # Xanax — most prescribed benzo
    ("clonazepam", "Clonazepam"),           # Klonopin — anxiety / panic / seizures
    ("lorazepam", "Lorazepam"),             # Ativan — anxiety / pre-op sedation
    ("zolpidem", "Zolpidem"),              # Ambien — most prescribed sleep drug

    # --- Antipsychotics ---
    ("quetiapine", "Quetiapine"),           # Seroquel — antipsychotic + off-label sleep
    ("aripiprazole", "Aripiprazole"),       # Abilify — very widely prescribed
    ("olanzapine", "Olanzapine"),           # Zyprexa
    ("risperidone", "Risperidone"),         # Risperdal
    ("haloperidol", "Haloperidol"),         # classic antipsychotic

    # --- Mood stabilisers / epilepsy ---
    ("lithium carbonate", "Lithium"),       # classic, well-known
    ("valproic acid", "Valproate"),         # Depakote — epilepsy / bipolar
    ("lamotrigine", "Lamotrigine"),         # Lamictal — epilepsy / bipolar
    ("carbamazepine", "Carbamazepine"),     # Tegretol — epilepsy / nerve pain
    ("topiramate", "Topiramate"),           # Topamax — epilepsy / migraine prevention
    ("phenytoin", "Phenytoin"),             # Dilantin — classic epilepsy drug

    # --- Anticoagulants ---
    ("apixaban", "Apixaban"),              # Eliquis — now most prescribed anticoagulant
    ("dabigatran", "Dabigatran"),          # Pradaxa
    ("enoxaparin", "Enoxaparin"),          # Lovenox — LMWH heparin

    # --- Antihypertensives / cardiac ---
    ("spironolactone", "Spironolactone"),  # heart failure / hypertension / acne
    ("diltiazem", "Diltiazem"),            # CCB — rate control / hypertension
    ("verapamil", "Verapamil"),            # CCB — arrhythmia / hypertension
    ("digoxin", "Digoxin"),               # classic cardiac — heart failure / AFib
    ("amiodarone", "Amiodarone"),          # arrhythmia — well-known
    ("amlodipine besylate", "Amlodipine_besylate"),

    # --- Antibiotics ---
    ("amoxicillin clavulanate", "Amoxicillin_clavulanate"),  # Augmentin — very common
    ("trimethoprim sulfamethoxazole", "Trimethoprim_sulfamethoxazole"),  # Bactrim — UTI
    ("levofloxacin", "Levofloxacin"),      # common broad-spectrum
    ("clindamycin", "Clindamycin"),        # skin / dental / anaerobic infections
    ("nitrofurantoin", "Nitrofurantoin"),  # UTI
    ("cephalexin", "Cephalexin"),          # Keflex — very common oral cephalosporin
    ("clarithromycin", "Clarithromycin"),  # H. pylori / respiratory

    # --- Antivirals ---
    ("acyclovir", "Acyclovir"),            # herpes
    ("valacyclovir", "Valacyclovir"),      # Valtrex — herpes, very common
    ("oseltamivir", "Oseltamivir"),        # Tamiflu — well-known

    # --- Antifungals ---
    ("fluconazole", "Fluconazole"),        # Diflucan — most prescribed antifungal

    # --- Respiratory ---
    ("tiotropium", "Tiotropium"),          # Spiriva — COPD maintenance
    ("budesonide", "Budesonide"),          # inhaled corticosteroid / IBD
    ("ipratropium", "Ipratropium"),        # COPD / Atrovent

    # --- Neurological / Alzheimer's / Parkinson's ---
    ("levodopa carbidopa", "Levodopa_carbidopa"),  # Parkinson's — very important
    ("donepezil", "Donepezil"),            # Aricept — most prescribed Alzheimer's drug
    ("memantine", "Memantine"),            # Alzheimer's

    # --- Opioid treatment / reversal ---
    ("naloxone", "Naloxone"),              # Narcan — opioid reversal, very well-known
    ("naltrexone", "Naltrexone"),          # opioid / alcohol dependence
    ("methadone", "Methadone"),            # opioid treatment / chronic pain

    # --- GI ---
    ("ondansetron", "Ondansetron"),        # Zofran — most prescribed antiemetic

    # --- Osteoporosis ---
    ("alendronate", "Alendronate"),        # Fosamax — most prescribed osteoporosis drug

    # --- Diabetes ---
    ("liraglutide", "Liraglutide"),        # Victoza — GLP-1 agonist
    ("dapagliflozin", "Dapagliflozin"),   # Farxiga — SGLT-2

    # --- Antihistamines ---
    ("loratadine", "Loratadine"),          # Claritin — most prescribed non-drowsy antihistamine
    ("fexofenadine", "Fexofenadine"),      # Allegra
    ("diphenhydramine", "Diphenhydramine"),  # Benadryl — well-known OTC

    # --- Gout ---
    ("allopurinol", "Allopurinol"),        # most prescribed gout drug
    ("colchicine", "Colchicine"),          # acute gout

    # --- Corticosteroids ---
    ("dexamethasone", "Dexamethasone"),    # well-known — COVID / inflammation / chemo
    ("prednisolone", "Prednisolone"),      # oral steroid — inflammation

    # --- Autoimmune ---
    ("hydroxychloroquine", "Hydroxychloroquine"),  # Plaquenil — well-known from COVID

    # --- Urological / hormonal ---
    ("sildenafil", "Sildenafil"),          # Viagra — very well-known
    ("tadalafil", "Tadalafil"),            # Cialis
    ("finasteride", "Finasteride"),        # BPH / hair loss

    # --- Dermatology ---
    ("isotretinoin", "Isotretinoin"),      # Accutane — well-known acne treatment

    # --- Immunosuppressants ---
    ("azathioprine", "Azathioprine"),      # transplant / autoimmune
    ("tacrolimus", "Tacrolimus"),          # transplant

    # --- Insulin ---
    ("insulin aspart", "Insulin_aspart"),  # rapid-acting insulin
]

DELAY = 0.3


def already_have(prefix: str) -> bool:
    base = os.path.join(OUTPUT_DIR, f"{prefix}_PIL.pdf")
    numbered = os.path.join(OUTPUT_DIR, f"{prefix}_1_PIL.pdf")
    return os.path.exists(base) or os.path.exists(numbered)


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def download_pdf(setid: str, out_path: str) -> bool:
    url = f"https://dailymed.nlm.nih.gov/dailymed/downloadpdffile.cfm?setId={setid}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    if len(data) < 1000:
        return False
    with open(out_path, "wb") as f:
        f.write(data)
    return True


downloaded = 0
skipped = 0
failed = 0

for drug_name, prefix in DRUGS:
    if already_have(prefix):
        print(f"[SKIP] {prefix} — already exists")
        skipped += 1
        continue

    print(f"\n[FETCH] {drug_name}")
    search_url = (
        "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json"
        f"?drug_name={urllib.parse.quote(drug_name)}&pagesize=1"
    )
    try:
        time.sleep(DELAY)
        data = fetch_json(search_url)
        results = data.get("data", [])
    except Exception as e:
        print(f"  [ERROR] Search failed: {e}")
        failed += 1
        continue

    if not results:
        print(f"  [MISS] No results found")
        failed += 1
        continue

    item = results[0]
    setid = item.get("setid", "")
    title = item.get("title", "N/A")[:80]

    if not setid:
        print(f"  [MISS] No setid")
        failed += 1
        continue

    out_path = os.path.join(OUTPUT_DIR, f"{prefix}_PIL.pdf")
    print(f"  setid={setid} | {title}")
    try:
        time.sleep(DELAY)
        ok = download_pdf(setid, out_path)
        if ok:
            size_kb = os.path.getsize(out_path) // 1024
            print(f"  -> Saved ({size_kb} KB)")
            downloaded += 1
        else:
            print(f"  -> Response too small, skipping")
            failed += 1
    except Exception as e:
        print(f"  -> [ERROR] {e}")
        failed += 1

print(f"\n{'='*50}")
print(f"DONE: downloaded={downloaded} skipped={skipped} failed={failed}")
