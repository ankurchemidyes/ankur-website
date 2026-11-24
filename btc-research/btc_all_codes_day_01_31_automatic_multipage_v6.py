# AUTOMATIC BTC V5 SAME-CODE MULTIPAGE PDF DATE-DAY SORTER
# NO input() prompts. ALL codes in BOTH V5 study folders are processed.
# Each CODE stays exactly ONE PDF; all its pages remain; sort by UTC day 01..31.
# Original PDFs are READ ONLY; sorted outputs are written to a separate new folder.
import sys, subprocess
subprocess.check_call([sys.executable,"-m","pip","install","-q","pypdf>=5.0"])
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone, date
import csv, os, re, hashlib
from pypdf import PdfReader, PdfWriter
from google.colab import drive

drive.mount("/content/drive")

BASE=Path("/content/drive/MyDrive/BTC_MATCHED_CODES_MULTIPAGE_V5")
SOURCE=BASE/"PDFS_GROUPED"
OUTPUT=BASE/"ALL_CODES_DAY_01_TO_31_SORTED_V6"
REPORTS=OUTPUT/"REPORTS"
REPORTS.mkdir(parents=True,exist_ok=True)
STUDIES={
    "UTC_23_00":re.compile(r"23[grd]{6}00[.]pdf",re.I),
    "UTC_11_12":re.compile(r"11[grd]{6}12[.]pdf",re.I),
}
RECORDS=[]
PROBLEMS=[]
FILES=[]

for study,regex in STUDIES.items():
    folder=SOURCE/study
    if not folder.is_dir():
        PROBLEMS.append((study,"SOURCE_FOLDER_MISSING",str(folder)))
        continue
    for f in sorted(folder.glob("*.pdf")):
        if not regex.fullmatch(f.name):
            PROBLEMS.append((study,"UNEXPECTED_PDF_FILENAME",str(f)))
            continue
        FILES.append((study,f))

if not FILES:
    raise FileNotFoundError(
        "कोई मूल V5 मल्टीपेज PDF नहीं मिली।\n"
        f"यहाँ स्रोत चाहिए: {SOURCE}/UTC_23_00 तथा UTC_11_12\n"
        "पहले V5 SAME CODE MULTIPAGE Colab पूरा चलाएँ। "
        "यह कोड नयी BTC कीमतें डाउनलोड नहीं करता और पुराने एक-पेज PDF नहीं पढ़ता।"
    )

def page_day(page):
    text=page.extract_text() or ""
    # The generator puts "UTC DATE: YYYY-MM-DD" on EVERY page.
    match=re.search(r"\bUTC\s*DATE\s*:\s*(20\d{2}-\d{2}-\d{2})\b",text,re.I)
    if not match:
        return None
    try:return date.fromisoformat(match.group(1))
    except ValueError:return None

def file_checksum(path):
    sha=hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024*1024),b""):
            sha.update(block)
    return sha.hexdigest()

print("कुल सही पैटर्न PDF मिलीं:",len(FILES))
print("साल/महीना नहीं पूछा जाएगा; प्रत्येक PDF के पेज दिन 01-31 के अनुसार सजेंगे।")
print("केवल NEW output folder में लिखेगा:",OUTPUT)
sorted_files=0;total_original_pages=0;total_new_pages=0;unknown_pages=0
for number,(study,src) in enumerate(FILES,1):
    try:
        original=PdfReader(str(src),strict=False)
        count=len(original.pages)
        if count==0:raise ValueError("EMPTY_PDF")
        entries=[]
        for idx,page in enumerate(original.pages):
            d=page_day(page)
            entries.append((idx,d))
        undecoded=sum(d is None for _,d in entries)
        # Do NOT silently place date-less pages in wrong day groups.
        # Leave entire source unchanged, report it so nothing gets lost.
        if undecoded:
            PROBLEMS.append((study,"UNREADABLE_PAGE_DATE",f"{src.name}: {undecoded}/{count} pages"))
            continue
        # Day only! Stable sort preserves the chronology within each day-of-month.
        order=sorted(range(count),key=lambda i:(entries[i][1].day,i))
        target_dir=OUTPUT/study
        target_dir.mkdir(parents=True,exist_ok=True)
        dest=target_dir/src.name  # EXACT code name stays unchanged.
        partial=target_dir/(src.name+".partial")
        writer=PdfWriter()
        for index in order:
            writer.add_page(original.pages[index])
        with partial.open("wb") as handle:
            writer.write(handle)
        verified=PdfReader(str(partial),strict=False)
        if len(verified.pages)!=count:
            raise RuntimeError(f"Page count changed: {len(verified.pages)}/{count}")
        expected=[entries[i][1].isoformat() for i in order]
        actual=[page_day(p) for p in verified.pages]
        if any(x is None for x in actual) or [x.isoformat() for x in actual]!=expected:
            raise RuntimeError("Page dates/order failed verification")
        os.replace(partial,dest)
        total_original_pages+=count
        total_new_pages+=len(verified.pages)
        sorted_files+=1
        RECORDS.append({
           "study":study,"code_pdf":src.name,
           "original_pages":count,"sorted_pages":len(verified.pages),
           "date_day_first":f"{entries[order[0]][1].day:02d}",
           "date_day_last":f"{entries[order[-1]][1].day:02d}",
           "distinct_day_numbers":len(set(d.day for _,d in entries)),
           "multiple_pages":str(count>1),
           "source_path":str(src),"new_path":str(dest),
        })
        if number%25==0 or number==len(FILES):
            print(f"जाँच व सेव: {number}/{len(FILES)} | बन चुकी PDF: {sorted_files} | सुरक्षित पेज: {total_new_pages}",flush=True)
    except Exception as err:
        PROBLEMS.append((study,"PROCESSING_ERROR",f"{src.name}: {type(err).__name__}: {err}"))
        print("स्किप (मूल सुरक्षित):",src.name,str(err)[:150],flush=True)

report=REPORTS/"ALL_CODES_PAGE_COUNTS.csv"
if RECORDS:
    with report.open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=list(RECORDS[0]))
        writer.writeheader();writer.writerows(RECORDS)
errors=REPORTS/"ISSUES_REQUIRING_ATTENTION.csv"
with errors.open("w",newline="",encoding="utf-8") as handle:
    writer=csv.writer(handle)
    writer.writerow(["study","issue","details"])
    writer.writerows(PROBLEMS)
report_text=(
    "BTC SAME-CODE MULTIPAGE PDF AUTOMATIC SORT BY DAY (01–31)\n"
    f"UTC completed: {datetime.now(timezone.utc).isoformat()}\n"
    f"Input PDFs found: {len(FILES):,}\n"
    f"Output PDFs verified: {sorted_files:,}\n"
    f"Original pages in successful PDFs: {total_original_pages:,}\n"
    f"Verified output pages: {total_new_pages:,}\n"
    f"PDFs with multiple pages: {sum(r['multiple_pages']=='True' for r in RECORDS):,}\n"
    f"Files/issues skipped (no deletions): {len(PROBLEMS):,}\n"
    "Day order: 01 to 31; no year/month input; year/month retained IN page header.\n"
    "Names: EXACT original pattern code, one PDF per code in its study folder.\n"
    "Original PDF inputs untouched, no market data modified.\n"
    f"OUTPUT={OUTPUT}\nREPORT={report}\nERRORS={errors}\n"
)
(REPORTS/"FINAL_SUMMARY.txt").write_text(report_text,encoding="utf-8")
print("\n"+report_text)
if PROBLEMS:
    print("ध्यान दें: कुछ स्रोत फाइलों की तारीख पढ़ने में समस्या थी; उनकी सूची ISSUES_REQUIRING_ATTENTION.csv में है।")
else:
    print("सभी पहचानी गई कोड-PDF सफलतापूर्वक व्यवस्थित हो गईं।")
