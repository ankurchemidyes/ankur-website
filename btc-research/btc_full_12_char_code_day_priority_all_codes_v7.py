# BTC V7 — exact 12-character search: TIME + 5M colors + 1H colors + TIME + DAY
# Example: 23ggrgrg0031 => all UTC-day-31 pages of 23ggrgrg00.pdf FIRST,
#                          followed by EVERY OTHER page of the SAME CODE.
# No input() popups. Batch multiple full 12-character codes in QUERY_CODES.
# Optional AUTO_SORT_ALL_CODES organizes every base-code PDF by day 01..31.
# Originals are READ ONLY; all new PDFs are verified in a separate Drive directory.

import sys, subprocess
subprocess.check_call([sys.executable,"-m","pip","install","-q","pypdf>=5.0"])
import re, csv, os, hashlib
from pathlib import Path
from datetime import datetime, timezone, date
from pypdf import PdfReader, PdfWriter
from google.colab import drive

# ===== SETTINGS: EDIT THIS LIST ONLY IF YOU WANT ANOTHER CODE =====
QUERY_CODES = [
    "23ggrgrg0031",
    # "23gggggg0023",
    # "11grrgrg1215",
]
AUTO_SORT_ALL_CODES = True
# True: also generate ONE day-01-to-31-sorted PDF for EVERY existing V5 code.
# False: only make PDFs for the 12-character QUERY_CODES above.
# ================================================================

drive.mount("/content/drive")
BASE = Path("/content/drive/MyDrive/BTC_MATCHED_CODES_MULTIPAGE_V5")
SOURCE = BASE / "PDFS_GROUPED"
OUTPUT = BASE / "CORRECT_12_CHARACTER_CODE_DATE_V7"
EXACT = OUTPUT / "EXACT_CODE_PLUS_DAY"
ALL = OUTPUT / "ALL_CODES_DAY_01_TO_31"
REPORTS = OUTPUT / "REPORTS"
for d in (EXACT, ALL, REPORTS):
    d.mkdir(parents=True,exist_ok=True)

PATTERN_12 = re.compile(r"^(23|11)([grd]{3})([grd]{3})(00|12)(0[1-9]|[12]\d|3[01])$",re.I)
PATTERN_SOURCE = {
    "UTC_23_00":re.compile(r"^23[grd]{6}00[.]pdf$",re.I),
    "UTC_11_12":re.compile(r"^11[grd]{6}12[.]pdf$",re.I),
}
PAGE_DATE = re.compile(r"UTC\s*DATE\s*:\s*(20\d{2}-\d{2}-\d{2})",re.I)

def validate_requested(raw):
    token=raw.strip().lower().removesuffix(".pdf")
    match=PATTERN_12.fullmatch(token)
    if match is None:
        raise ValueError("12-अक्षर सही कोड चाहिए, जैसे 23ggrgrg0031; कुल 2+3+3+2+2 अक्षर।")
    left,up,down,right,day=match.groups()
    if (left,right) not in (("23","00"),("11","12")):
        raise ValueError("टाइम का मेल सही नहीं: 23 के अंत में 00 और 11 के अंत में 12 होना चाहिए।")
    return token, left+up+down+right, int(day), "UTC_23_00" if left=="23" else "UTC_11_12"

def get_page_date(page,source_path,index):
    m=PAGE_DATE.search(page.extract_text() or "")
    if not m:
        raise ValueError(f"UTC DATE not found in {source_path.name}, page {index+1}")
    try:
        return date.fromisoformat(m.group(1))
    except ValueError as exc:
        raise ValueError(f"Invalid UTC DATE in {source_path.name}, page {index+1}") from exc

def reorder_pdf(source, destination, requested_day=None):
    reader=PdfReader(str(source),strict=False)
    n=len(reader.pages)
    if not n:raise ValueError("Source PDF has zero pages: "+source.name)
    dates=[get_page_date(page,source,i) for i,page in enumerate(reader.pages)]
    if requested_day is None:
        # Automatic grouping of all pages by day 01..31; stable within each day.
        indices=sorted(range(n),key=lambda i:(dates[i].day,i))
        matched=n
    else:
        first=[i for i,d in enumerate(dates) if d.day==requested_day]
        rest=[i for i,d in enumerate(dates) if d.day!=requested_day]
        indices=first+rest
        matched=len(first)
    if requested_day is not None and matched==0:
        # Do not generate a misleading file with no matching date at its start.
        return {"status":"NO_MATCH","count":n,"matched":0,
                "output":"","source":source.name}
    writer=PdfWriter()
    for i in indices:
        writer.add_page(reader.pages[i])
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_suffix(destination.suffix+".partial")
    with temporary.open("wb") as f:writer.write(f)
    # Ensure count and exact order of full UTC dates—not just file existence.
    check=PdfReader(str(temporary),strict=False)
    if len(check.pages)!=n:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Page count mismatch: {source.name}")
    expected_dates=[dates[i] for i in indices]
    received_dates=[get_page_date(p,temporary,i) for i,p in enumerate(check.pages)]
    if received_dates!=expected_dates:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Page date/order mismatch: {source.name}")
    os.replace(temporary,destination)
    return {"status":"OK","count":n,"matched":matched,
            "output":str(destination),"source":source.name}

def write_csv(path,rows):
    if not rows:return
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)

print("12-अक्षर वाले कोड का सही प्रारूप: 23 + ggr + grg + 00 + 31")
print("यह सिस्टम साल या महीना नहीं माँगता।")
print("V5 मूल PDF सुरक्षित रहेंगी।")

requested_results=[]
seen=set()
for item in QUERY_CODES:
    token,base,day,study=validate_requested(item)
    if token in seen:continue
    seen.add(token)
    src=SOURCE/study/(base+".pdf")
    if not src.is_file():
        requested_results.append({"query":token,"base_code":base,"day":day,
            "status":"SOURCE_MISSING","total_pages":0,"day_pages":0,"output":""})
        print(f"स्रोत नहीं मिला: {token} -> {src}")
        continue
    dst=EXACT/study/(token+".pdf")
    try:
        r=reorder_pdf(src,dst,day)
        requested_results.append({"query":token,"base_code":base,"day":day,
            "status":r["status"],"total_pages":r["count"],
            "day_pages":r["matched"],"output":r["output"]})
        print(f"{token}: {r['status']}; पहले दिन {day:02d} के {r['matched']} पेज; कुल {r['count']} पेज")
    except Exception as error:
        requested_results.append({"query":token,"base_code":base,"day":day,
            "status":"ERROR: "+str(error),"total_pages":0,"day_pages":0,"output":""})
        print("जाँच में समस्या:",token,error)
write_csv(REPORTS/"QUERIED_12_CHARACTER_CODES.csv",requested_results)

automatic_results=[]
if AUTO_SORT_ALL_CODES:
    print("\nसभी मूल कोड की PDF अब दिन 01 से 31 के क्रम में बनाई जा रही हैं...")
    for study,regex in PATTERN_SOURCE.items():
        folder=SOURCE/study
        if not folder.is_dir():
            print("स्रोत फ़ोल्डर नहीं मिला:",folder)
            continue
        for src in sorted(folder.glob("*.pdf")):
            if not regex.fullmatch(src.name):
                print("अमान्य स्रोत PDF नाम छोड़ दिया:",src.name)
                continue
            dst=ALL/study/src.name
            try:
                r=reorder_pdf(src,dst,None)
                automatic_results.append({"study":study,"code":src.stem,
                    "status":r["status"],"pages":r["count"],"output":r["output"]})
            except Exception as error:
                automatic_results.append({"study":study,"code":src.stem,
                    "status":"ERROR: "+str(error),"pages":0,"output":""})
                print("स्रोत सुरक्षित; त्रुटि:",src.name,error)
            if len(automatic_results)%25==0:
                write_csv(REPORTS/"ALL_CODES_PAGES.csv",automatic_results)
                print(f"सभी कोड प्रगति: {len(automatic_results)} PDF",flush=True)
write_csv(REPORTS/"ALL_CODES_PAGES.csv",automatic_results)

ok_exact=[x for x in requested_results if x["status"]=="OK"]
ok_all=[x for x in automatic_results if x["status"]=="OK"]
report=(
    "BTC 12-CHARACTER TIME + COLOR + DAY PDF SYSTEM V7\n"
    f"UTC: {datetime.now(timezone.utc).isoformat()}\n"
    f"Queries entered in configuration: {len(seen)}\n"
    f"Exact date-day-prioritized PDFs created: {len(ok_exact)}\n"
    f"Total pages across exact PDF results: {sum(x['total_pages'] for x in ok_exact)}\n"
    f"All-code date-sorted PDFs created: {len(ok_all)}\n"
    f"Total historical pages across all-code PDFs: {sum(x['pages'] for x in ok_all)}\n"
    "PDF example: 23ggrgrg0031.pdf (31-day matches first, remaining matching-code pages after)\n"
    "Pattern 23ggrgrg00 never mixed with any other pattern.\n"
    "Only day (01–31) is used for page sorting; year/month remain on original pages.\n"
    "No originals were changed or deleted.\n"
    f"RESULT FOLDER: {OUTPUT}\n"
)
(REPORTS/"FINAL_SUMMARY.txt").write_text(report,encoding="utf-8")
print("\n"+report)
if not ok_exact and not ok_all:
    print("कोई नई PDF नहीं बनी। पहले V5 के PDFS_GROUPED फ़ोल्डर का निर्माण पूरा करें।")
