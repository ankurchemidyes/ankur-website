# BTC V5 PDF PAGE PRIORITY — SEARCH EXACT COLOR CODE, THEN DAY OR FULL UTC DATE.
# Read an existing, immutable grouped V5 source PDF; write new reordered copy.
# Code examples: 23gggggg00, 11grrgrg12
# Date selector: 23 (all calendar days 23 across 2013–2026),
# 2019-06-23 (one exact UTC date), or 06-23 (same month/day in any year).
# Matching pages are placed FIRST, all other pages retain original order.
# Source PDFs are NOT modified, removed, or overwritten.
import sys
import subprocess
subprocess.check_call([sys.executable,"-m","pip","install","-q","pypdf>=5.0"])
from pathlib import Path
import re, csv, os, datetime
from pypdf import PdfReader, PdfWriter
from google.colab import drive, files

drive.mount("/content/drive")
ROOT=Path("/content/drive/MyDrive/BTC_MATCHED_CODES_MULTIPAGE_V5")
SRC=ROOT/"PDFS_GROUPED"
OUT=ROOT/"DATE_FIRST_SEARCH_RESULTS"
OUT.mkdir(parents=True,exist_ok=True)
REPORT=OUT/"SEARCH_HISTORY.csv"

def code_input(s):
    s=s.strip().lower().removesuffix(".pdf")
    if not re.fullmatch(r"(?:23[grd]{6}00|11[grd]{6}12)",s):
        raise ValueError(
            "पूरा सही कोड लिखिए, जैसे 23gggggg00 या 11grrgrg12 "
            "(g=green, r=red, d=doji).")
    return s

def date_input(value):
    val=value.strip()
    if re.fullmatch(r"\d{1,2}",val):
        n=int(val)
        if n<1 or n>31:raise ValueError("दिन 01 से 31 होना चाहिए।")
        return "day",n,f"DAY{n:02d}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}",val):
        x=datetime.date.fromisoformat(val)
        return "full",x.isoformat(),x.strftime("%Y%m%d")
    if re.fullmatch(r"\d{2}-\d{2}",val):
        month,day=map(int,val.split("-"))
        # Leap year permits Feb 29
        datetime.date(2024,month,day)
        return "month_day",(month,day),f"MONTH{month:02d}_DAY{day:02d}"
    raise ValueError("तारीख 23, 2019-06-23 या 06-23 के रूप में लिखें।")

def page_utc_date(page):
    # V5 prints: UTC DATE: YYYY-MM-DD
    content=page.extract_text() or ""
    m=re.search(r"\bUTC\s*DATE\s*:\s*(20\d{2}-\d{2}-\d{2})\b",content,re.I)
    if m:
        try:return datetime.date.fromisoformat(m.group(1))
        except ValueError:pass
    return None

def date_matches(date,kind,value):
    if date is None:return False
    if kind=="day":return date.day==value
    if kind=="full":return date.isoformat()==value
    return date.month==value[0] and date.day==value[1]

def organize(code,date):
    key=code_input(code)
    kind,lookfor,suffix=date_input(date)
    mode="UTC_23_00" if key.startswith("23") else "UTC_11_12"
    source=SRC/mode/(key+".pdf")
    if not source.is_file():
        raise FileNotFoundError(
            f"उस कोड की PDF नहीं मिली: {source}\n"
            "पहले BTC V5 grouped PDF वाली Colab प्रक्रिया COMPLETE होनी चाहिए।"
        )
    reader=PdfReader(str(source),strict=False)
    if len(reader.pages)<1:raise RuntimeError("Source PDF empty.")
    first=[];rest=[];unknown=[]
    dates=[]
    for i,page in enumerate(reader.pages):
        d=page_utc_date(page)
        dates.append(d.isoformat() if d else "")
        if d is None:unknown.append(i)
        if date_matches(d,kind,lookfor):
            first.append(i)
        else:
            rest.append(i)
    if not first:
        print(f"कोड {key} में तारीख '{date}' का कोई पेज नहीं मिला।")
        print(f"उस कोड में कुल {len(reader.pages):,} पेज मौजूद हैं।")
        print("मूल PDF वैसी ही रहेगी; कोई खाली नई PDF नहीं बनाई जाएगी।")
        return None
    writer=PdfWriter()
    for index in first+rest:
        writer.add_page(reader.pages[index])
    output=OUT/f"{key}__{suffix}_FIRST.pdf"
    tmp=OUT/(output.name+".partial")
    with open(tmp,"wb") as f:writer.write(f)
    # Verify content order as well as output page count, not just file existence.
    verification=PdfReader(str(tmp),strict=False)
    if len(verification.pages)!=len(reader.pages):
        raise RuntimeError("PDF page count validation failed; old source unchanged.")
    expected_dates=[dates[i] for i in first+rest]
    actual_dates=[page_utc_date(p) for p in verification.pages]
    if [x.isoformat() if x else "" for x in actual_dates]!=expected_dates:
        raise RuntimeError("Dates/order validation failed; old source unchanged.")
    os.replace(tmp,output)
    row={
        "code":key,"date_query":date,"date_mode":kind,
        "original_pages":len(reader.pages),"prioritized_pages":len(first),
        "other_pages":len(rest),"unreadable_date_pages":len(unknown),
        "result_pdf":output.name,
        "utc_generated":datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    fields=list(row)
    write_header=not REPORT.exists()
    with open(REPORT,"a",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields)
        if write_header:w.writeheader()
        w.writerow(row)
    print("\n✅ सही तारीख वाले पेज सबसे पहले रख दिए गए हैं")
    print("कोड:",key)
    print("आपने जो तारीख खोजी:",date)
    print("सबसे ऊपर मिले पेज:",len(first))
    print("उसके बाद बाकी पेज:",len(rest))
    print("कुल पेज सुरक्षित:",len(reader.pages))
    print("पहले आए UTC दिन:",", ".join(dates[i] for i in first))
    print("नई PDF:",output)
    print("पुरानी मल्टीपेज PDF: सुरक्षित, बिना बदलाव के")
    return output

print("उदाहरण कोड: 23gggggg00 अथवा 11grrgrg12")
code=input("पूरा पैटर्न कोड लिखें: ").strip()
print("तारीख के विकल्प: 23 (सभी महीनों का 23), 2019-06-23 (एक सटीक तारीख), 06-23 (हर साल 23 जून)")
date=input("तारीख लिखें: ").strip()
result=organize(code,date)
if result:
    print("\nGoogle Drive → BTC_MATCHED_CODES_MULTIPAGE_V5 → DATE_FIRST_SEARCH_RESULTS")
    print("मोबाइल पर PDF लेने के लिए Drive में यह नाम खोजें:",result.name)
    # An optional direct download is intentionally not forced:
    # large PDF may be easier to access from Drive on mobile.
