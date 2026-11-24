# SRK historical 23:00 pattern archive — correct names and multipage grouping.
# Reads completed V3 PDFs and groups identical SIX-CANDLE color codes.
# No source PDFs are changed or deleted; every original page is preserved.
# Output: 23gggggg00.pdf (all dates as pages in this one file).
import sys,subprocess
subprocess.check_call([sys.executable,"-m","pip","install","-q","pypdf"])
from pathlib import Path
import csv, re, os, collections
from pypdf import PdfReader, PdfWriter
from google.colab import drive
drive.mount("/content/drive")
BASE=Path("/content/drive/MyDrive/BTC_UTC_23_5M_00_1H_2013_NOW")
SOURCE=BASE/"PDFS_V3_SAMPLE_ALIGNED"
OUTPUT=Path("/content/drive/MyDrive/BTC_23_FIXED_CODES_MULTIPAGE_CORRECT")
PAGES=OUTPUT/"PDFS"
REPORTS=OUTPUT/"REPORTS"
for d in (PAGES,REPORTS):d.mkdir(parents=True,exist_ok=True)
if not SOURCE.is_dir():
    raise FileNotFoundError(f"Original V3 PDFs not found: {SOURCE}")
regex=re.compile(r"^(?:0[1-9]|[12][0-9]|3[01])([grd]{6})00_(20[0-9]{6})[.]pdf$",re.IGNORECASE)
groups=collections.defaultdict(list)
ignored=[]
for f in SOURCE.glob("*.pdf"):
    m=regex.fullmatch(f.name)
    if m:
        key="23"+m.group(1).lower()+"00"
        groups[key].append((m.group(2),f))
    else:ignored.append(f.name)
print(f"Source PDF count accepted: {sum(map(len,groups.values())):,}")
print(f"Distinct six-candle codes: {len(groups):,}")
print(f"Unrecognized names, not changed: {len(ignored):,}")
if not groups:raise ValueError("No V3 source PDFs match the expected day+6-colors+00_YYYYMMDD pattern")
manifest_rows=[]
for idx,(key,fileset) in enumerate(sorted(groups.items()),1):
    fileset.sort(key=lambda pair:(pair[0],pair[1].name))
    filename=key+".pdf"
    dest=PAGES/filename
    partial=PAGES/(filename+".partial")
    writer=PdfWriter()
    for date,file in fileset:
        try:
            reader=PdfReader(str(file),strict=False)
            if len(reader.pages)<1:
                raise RuntimeError("No PDF pages")
            for page in reader.pages:
                writer.add_page(page)
            manifest_rows.append({
              "code":key,"output_pdf":filename,"source_pdf":file.name,
              "utc_date":date,"original_pages":len(reader.pages)})
        except Exception as e:
            raise RuntimeError(f"Stopped safely. Could not read {file.name}: {e}") from e
    with open(partial,"wb") as h:writer.write(h)
    expected=sum(r["original_pages"] for r in manifest_rows if r["code"]==key)
    actual=len(PdfReader(str(partial),strict=False).pages)
    if actual!=expected:
        raise RuntimeError(f"Page count mismatch for {filename}: {actual} vs {expected}")
    os.replace(partial,dest)
    print(f"[{idx}/{len(groups)}] {filename}: {actual} pages")
manifest=REPORTS/"SOURCE_PAGES_BY_CODE.csv"
with open(manifest,"w",encoding="utf-8",newline="") as h:
    w=csv.DictWriter(h,fieldnames=["code","output_pdf","source_pdf","utc_date","original_pages"])
    w.writeheader();w.writerows(manifest_rows)
if ignored:
    (REPORTS/"UNRECOGNIZED_SOURCE_NAMES.txt").write_text("\n".join(ignored),encoding="utf-8")
source_pages=sum(x["original_pages"] for x in manifest_rows)
out_pdf_count=len(groups)
multi_count=sum(len(rows)>1 for rows in groups.values())
report=(f"Input original PDF files: {sum(len(x) for x in groups.values()):,}\n"
        f"Output grouped PDF files: {out_pdf_count:,}\n"
        f"Total preserved pages: {source_pages:,}\n"
        f"Codes with multiple source records: {multi_count:,}\n"
        f"PDF names: 23 + 6 real color letters + 00.pdf\n"
        f"Output: {PAGES}\n"
        f"Original source PDF files: UNCHANGED\n")
(REPORTS/"GROUPING_SUMMARY.txt").write_text(report,encoding="utf-8")
print("\nCOMPLETE\n"+report)
