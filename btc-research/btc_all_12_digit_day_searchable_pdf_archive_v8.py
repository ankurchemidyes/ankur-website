# BTC 12-CHARACTER SEARCHABLE, DATE-FIRST PDF ARCHIVE V8
# From ORIGINAL grouped V5 source PDFs, create a searchable PDF for every
# *ACTUALLY PRESENT* day-of-month per pattern. NO manual input, NO invented hits.
# 23ggrrgg0020.pdf: actual day-20 page(s) first; same-pattern other pages follow.
# All PDF contents preserve the original date labels, prices and annotations.
# This generates multiple full-length PDF copies PER pattern. Plan sufficient Drive storage.
# DO NOT DELETE V5 PDFS_GROUPED until the final verification report is COMPLETE.

import sys, subprocess
subprocess.check_call([sys.executable,"-m","pip","install","-q","pypdf>=5.0"])

from pathlib import Path
from collections import Counter
from datetime import datetime, timezone, date
import csv, json, os, re, shutil
from pypdf import PdfReader, PdfWriter
from google.colab import drive

drive.mount("/content/drive")

SOURCE_ROOT = Path("/content/drive/MyDrive/BTC_MATCHED_CODES_MULTIPAGE_V5/PDFS_GROUPED")
OUTPUT_ROOT = Path("/content/drive/MyDrive/BTC_12_DIGIT_SEARCH_READY_V8")
PDF_ROOT = OUTPUT_ROOT / "SEARCHABLE_12_CHAR_PDFS"
REPORT_ROOT = OUTPUT_ROOT / "REPORTS"
PDF_ROOT.mkdir(parents=True, exist_ok=True)
REPORT_ROOT.mkdir(parents=True, exist_ok=True)

STUDIES = {
    "UTC_23_00": re.compile(r"23[grd]{6}00[.]pdf$", re.I),
    "UTC_11_12": re.compile(r"11[grd]{6}12[.]pdf$", re.I),
}
UTC_DATE_PATTERN = re.compile(r"\bUTC\s*DATE\s*:\s*(20\d{2}-\d{2}-\d{2})\b", re.I)
CSV_PATH = REPORT_ROOT / "ALL_VALID_12_CHAR_CODES.csv"
PROGRESS_PATH = REPORT_ROOT / "PROGRESS_STATUS.txt"
ERRORS_PATH = REPORT_ROOT / "ERRORS.csv"
SUMMARY_PATH = REPORT_ROOT / "FINAL_SUMMARY.txt"

def utc_date(page, original_name, number):
    match = UTC_DATE_PATTERN.search(page.extract_text() or "")
    if match is None:
        raise ValueError(f"UTC DATE not found: {original_name}, page {number}")
    try:
        return date.fromisoformat(match.group(1))
    except ValueError as ex:
        raise ValueError(f"Invalid UTC DATE: {original_name}, page {number}") from ex

def status(message):
    line = f"{datetime.now(timezone.utc).isoformat()} | {message}"
    print(line, flush=True)
    PROGRESS_PATH.write_text(line+"\n", encoding="utf-8")

def save_csv_atomic(path, rows, columns):
    temp = path.with_name(path.name+".partial")
    with temp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temp, path)

def make_page_order(dates, day):
    priority = [i for i,d in enumerate(dates) if d.day == day]
    rest = [i for i,d in enumerate(dates) if d.day != day]
    return priority, rest

def validate_existing(path, expected_count, expected_day, count_matching):
    if not path.exists(): return False
    try:
        r = PdfReader(str(path), strict=False)
        if len(r.pages) != expected_count: return False
        if any(utc_date(r.pages[i],path.name,i+1).day!=expected_day
               for i in range(count_matching)): return False
        if count_matching < len(r.pages):
            # Check that first non-matching page is NOT selected day.
            if utc_date(r.pages[count_matching],path.name,count_matching+1).day == expected_day:
                return False
        return True
    except Exception:
        return False

FILES=[]
missing=[]
for study, name_pattern in STUDIES.items():
    folder=SOURCE_ROOT/study
    if not folder.is_dir():
        missing.append(str(folder))
        continue
    for path in sorted(folder.glob("*.pdf")):
        if name_pattern.fullmatch(path.name):
            FILES.append((study,path))
        else:
            status(f"IGNORED NONSTANDARD SOURCE FILE: {path.name}")

if not FILES:
    raise FileNotFoundError(
        "स्रोत V5 की मल्टीपेज PDF नहीं मिली। V5 PDFS_GROUPED फोल्डर को "
        "डिलीट न करें। अपेक्षित फ़ोल्डर: "+str(SOURCE_ROOT))
if missing:
    status("WARNING: Some source study folders are missing: "+"; ".join(missing))

status(f"BEGIN | source pattern PDFs = {len(FILES)} | 12-char PDF for each available day")
rows=[]; errors=[]
created=0; reused=0; original_pages=0
output_pages=0; expected_pairs=0
for file_index,(study,path) in enumerate(FILES,1):
    try:
        source=PdfReader(str(path), strict=False)
        count=len(source.pages)
        if count==0:
            raise ValueError("Source PDF has no pages")
        dates=[utc_date(page,path.name,i+1) for i,page in enumerate(source.pages)]
        days=sorted(set(d.day for d in dates))
        original_pages+=count
        expected_pairs+=len(days)
        # Build one code+day search PDF for each actual UTC calendar day in the source.
        for day in days:
            first, rest=make_page_order(dates,day)
            code12=f"{path.stem}{day:02d}"
            assert len(code12)==12 and len(first)>0
            destination=PDF_ROOT/study/(code12+".pdf")
            destination.parent.mkdir(parents=True,exist_ok=True)
            if validate_existing(destination,count,day,len(first)):
                reused+=1
            else:
                writer=PdfWriter()
                for index in first+rest:
                    writer.add_page(source.pages[index])
                temporary=destination.with_suffix(".pdf.partial")
                with temporary.open("wb") as handle:
                    writer.write(handle)
                # Check all pages by DATE, not just filename or first page.
                verify=PdfReader(str(temporary),strict=False)
                if len(verify.pages)!=count:
                    temporary.unlink(missing_ok=True)
                    raise RuntimeError(f"Page count mismatch {code12}")
                actual_dates=[
                    utc_date(p,temporary.name,i+1) for i,p in enumerate(verify.pages)]
                expected_dates=[dates[i] for i in first+rest]
                if actual_dates!=expected_dates:
                    temporary.unlink(missing_ok=True)
                    raise RuntimeError(f"Date order mismatch {code12}")
                os.replace(temporary,destination)
                created+=1
            output_pages+=count
            rows.append({
                "study":study,
                "search_code_12":code12,
                "base_pattern":path.stem,
                "day_only":f"{day:02d}",
                "matching_day_pages_first":len(first),
                "remaining_same_pattern_pages":len(rest),
                "total_pdf_pages":count,
                "file_name":destination.name,
                "drive_path":str(destination)
            })
        if file_index%10==0 or file_index==len(FILES):
            save_csv_atomic(CSV_PATH,rows,
                ["study","search_code_12","base_pattern","day_only",
                 "matching_day_pages_first","remaining_same_pattern_pages",
                 "total_pdf_pages","file_name","drive_path"])
            status(f"{file_index}/{len(FILES)} source pattern PDFs | "
                   f"{created} new, {reused} reused, {len(rows)} searchable files | "
                   f"all output pages summed {output_pages}")
    except Exception as exc:
        errors.append({
            "study":study,
            "source_pdf":path.name,
            "reason":str(exc)
        })
        status(f"ERROR | {study}/{path.name}: {type(exc).__name__}: {exc}")
        # Continue processing other source pattern PDFs without touching originals.

save_csv_atomic(CSV_PATH,rows,[
    "study","search_code_12","base_pattern","day_only",
    "matching_day_pages_first","remaining_same_pattern_pages",
    "total_pdf_pages","file_name","drive_path"])
save_csv_atomic(ERRORS_PATH,errors,["study","source_pdf","reason"])
summary=(
    f"BTC 12-CHARACTER SEARCHABLE PDF V8\n"
    f"Source pattern PDFs found: {len(FILES)}\n"
    f"12-character PDFs created this run: {created}\n"
    f"12-character PDFs previously verified/reused: {reused}\n"
    f"Searchable 12-character PDF total verified in this run: {len(rows)}\n"
    f"Unique 10-character source patterns with results: "
    f"{len(set((x['study'],x['base_pattern']) for x in rows))}\n"
    f"Original source pages seen: {original_pages}\n"
    f"Total pages across all searchable PDFs (includes duplicated pages per day): {output_pages}\n"
    f"Source patterns with processing errors: {len(errors)}\n"
    f"V5 source PDFs unchanged: YES\n"
    f"Output root: {PDF_ROOT}\n"
    f"Index with every available code+day: {CSV_PATH}\n"
    f"Errors: {ERRORS_PATH}\n"
)
if errors or missing:
    summary += ("STATUS: PARTIAL. Do NOT delete your old V5 source folder yet.\n")
else:
    summary += ("STATUS: COMPLETE. Verify the output in Google Drive before deleting anything.\n")
SUMMARY_PATH.write_text(summary,encoding="utf-8")
print("\n"+summary)
print("खोज उदाहरण: 23ggrrgg0020 (अगर दिन 20 का वास्तविक मैच मौजूद है)")
print("एक कोड में उसी दिन के सारे पेज पहले, बाकी उसी कोड के पेज बाद में हैं।")
print("किस-किस दिन का सच में मैच है: REPORTS/ALL_VALID_12_CHAR_CODES.csv देखें।")
