# BTC V5: select ONE full six-color code + ONE day-of-month only (01–31).
# E.g. code=23gggggg00 and day=23. No year/month input.
# All pages whose UTC day equals 23 are first; all other pages follow.
# ONE resulting multipage PDF; original grouped source untouched.
import sys, subprocess
subprocess.check_call([sys.executable,"-m","pip","install","-q","pypdf>=5.0"])
from pathlib import Path
import re, os, csv
from datetime import date, datetime, timezone
from pypdf import PdfReader, PdfWriter
from google.colab import drive

drive.mount("/content/drive")
ROOT=Path("/content/drive/MyDrive/BTC_MATCHED_CODES_MULTIPAGE_V5")
SOURCE=ROOT/"PDFS_GROUPED"
DEST=ROOT/"DAY_FIRST_ONE_MULTIPAGE_PDF"
DEST.mkdir(parents=True,exist_ok=True)
CODE=input("पूरा पैटर्न कोड डालें (जैसे 23gggggg00 या 11grrgrg12): ").strip().lower()
if CODE.endswith(".pdf"):CODE=CODE[:-4]
if not re.fullmatch(r"(?:23[grd]{6}00|11[grd]{6}12)",CODE):
    raise ValueError("पूरा 10-अक्षर का कोड डालें: 23gggggg00 या 11grrgrg12. d = Doji.")
DAY_TEXT=input("केवल तारीख का दिन (01–31) डालें, साल/महीना नहीं: ").strip()
if not re.fullmatch(r"(?:0?[1-9]|[12][0-9]|3[01])",DAY_TEXT):
    raise ValueError("तारीख के दिन के लिए केवल 1 से 31 तक संख्या डालें।")
DAY=int(DAY_TEXT)
STUDY="UTC_23_00" if CODE.startswith("23") else "UTC_11_12"
source=SOURCE/STUDY/(CODE+".pdf")
if not source.is_file():
    raise FileNotFoundError(
        "इस कोड की मल्टीपेज PDF नहीं मिली: "+str(source)+
        "\nपहले 2013–2026 V5 SAME CODE MULTIPAGE वाला Colab पूरा चलाएँ।")
reader=PdfReader(str(source),strict=False)
if not reader.pages:raise RuntimeError("मूल PDF में कोई पेज नहीं है।")
def read_date(page):
    txt=page.extract_text() or ""
    # V5 page header prints UTC DATE: YYYY-MM-DD.
    m=re.search(r"UTC\s*DATE\s*:\s*(20\d{2}-\d{2}-\d{2})",txt,re.I)
    if not m:
        return None
    try:return date.fromisoformat(m.group(1))
    except ValueError:return None

selected=[];remaining=[];dates=[];unknown=0
for index,page in enumerate(reader.pages):
    d=read_date(page)
    dates.append(d)
    if d is None:
        unknown+=1
    if d is not None and d.day==DAY:
        selected.append(index)
    else:
        remaining.append(index)
print("कुल मूल पेज:",len(reader.pages))
print(f"{DAY:02d} तारीख वाले मैचिंग पेज:",len(selected))
print("इसी कोड के बाकी पेज:",len(remaining))
if unknown:
    print("चेतावनी: जिन पेजों की तारीख पढ़ी नहीं गई:",unknown,
          "— वे सुरक्षित रूप से बाकी पेजों में रखे जाएँगे।")
if not selected:
    print("इस कोड में इस तारीख का मैच नहीं मिला, इसलिए मूल क्रम को बदलने वाली PDF नहीं बनाई गई।")
else:
    filename=f"{CODE}__DAY{DAY:02d}_FIRST.pdf"
    output=DEST/filename
    partial=DEST/(filename+".partial")
    writer=PdfWriter()
    for index in selected+remaining:
        writer.add_page(reader.pages[index])
    with partial.open("wb") as fh:
        writer.write(fh)
    check=PdfReader(str(partial),strict=False)
    if len(check.pages)!=len(reader.pages):
        raise RuntimeError("पेज संख्या नहीं मिली; मूल PDF सुरक्षित है।")
    # Validate that every selected page comes before all others.
    actual=[read_date(p) for p in check.pages]
    if any(p is None or p.day!=DAY for p in actual[:len(selected)]):
        raise RuntimeError("चुने हुए दिन के पेज पहले नहीं आए; नया PDF सेव नहीं किया।")
    if [d.isoformat() if d else "" for d in actual] != [
        dates[i].isoformat() if dates[i] else "" for i in selected+remaining
    ]:
        raise RuntimeError("पेजों की तारीख का क्रम जाँच में असफल रहा।")
    os.replace(partial,output)
    print("\nसफल! एक ही मल्टीपेज PDF बनाई गई:")
    print(output)
    print(f"सबसे पहले {DAY:02d} तारीख वाले {len(selected)} पेज।")
    print(f"उसके बाद {len(remaining)} अन्य पेज (एक ही कोड, एक ही टाइम)।")
    print("कुल पेज सुरक्षित:",len(check.pages))
    print("मूल SOURCE PDF में कोई बदलाव नहीं हुआ।")
    if selected:
        print("ऊपर आने वाली तारीखें (सिर्फ जानकारी के लिए):",
              ", ".join(str(dates[i]) for i in selected[:30]))
    report=DEST/"DAY_FIRST_RESULTS.csv"
    header=not report.exists()
    with report.open("a",encoding="utf-8",newline="") as fh:
        w=csv.writer(fh)
        if header:
            w.writerow(["code","day_only","matched_pages","other_pages",
                        "total_pages","output_file","utc_generated"])
        w.writerow([CODE,f"{DAY:02d}",len(selected),len(remaining),
                    len(check.pages),filename,datetime.now(timezone.utc).isoformat()])
