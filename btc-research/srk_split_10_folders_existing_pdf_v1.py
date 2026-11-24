# Organize SRK PDFs into exactly 10 folders (safe resumable MOVE).
# Designed for existing /MyDrive/BTC_SRK_36_CANDLE_12H_STEP_2013_NOW/SRK_PDFS_180
# Keeps every PDF unchanged and preserves its name; no merging or re-rendering.
# First nine folders: 1000 files, last folder: all SRK9001+.
import re, os, csv, shutil
from pathlib import Path
from google.colab import drive
drive.mount("/content/drive")
root=Path("/content/drive/MyDrive/BTC_SRK_36_CANDLE_12H_STEP_2013_NOW/SRK_PDFS_180")
if not root.is_dir(): raise FileNotFoundError(f"SRK PDF folder missing: {root}")
pattern=re.compile(r"^SRK([1-9]\d*)\.pdf$",re.IGNORECASE)

def group(n):
    return min(10,(n-1)//1000+1)

def folder(g):
    lo=(g-1)*1000+1
    return root/(f"SRK_PART_{g:02d}_{lo:05d}_PLUS" if g==10 else f"SRK_PART_{g:02d}_{lo:05d}_{g*1000:05d}")

targets={k:folder(k) for k in range(1,11)}
for dest in targets.values():dest.mkdir(exist_ok=True)

# Re-runs are safe; PDFs already inside group folders will be recognized.
pdfs=[]
for p in root.iterdir():
    if not p.is_file():continue
    match=pattern.fullmatch(p.name)
    if not match:continue
    pdfs.append((int(match.group(1)),p))
pdfs.sort()
print("PDFs remaining in original root:",len(pdfs))
moved=0
conflicts=[]
for n,p in pdfs:
    dest=targets[group(n)]/p.name
    if dest.exists():
        # Preserve both files rather than overwrite an existing file.
        conflicts.append(f"{p.name}: {p} -> {dest}")
        continue
    shutil.move(str(p),str(dest))
    moved+=1
    if moved%500==0:print("Moved:",moved)
report=[]
for g,d in targets.items():
    count=sum(1 for f in d.iterdir() if f.is_file() and pattern.fullmatch(f.name))
    report.append((g,d.name,count))
print("\nRESULT — TEN SRK PDF FOLDERS")
for g,name,count in report:print(f"{name}: {count:,} PDF")
print("Newly moved PDFs:",moved)
print("Naming conflicts (not overwritten):",len(conflicts))
print("Total in 10 folders:",sum(x[2] for x in report))
remaining=sum(1 for p in root.iterdir() if p.is_file() and pattern.fullmatch(p.name))
print("Remaining SRK PDFs in original root:",remaining)
report_file=root.parent/"REPORTS"/"SRK_TEN_FOLDER_ORGANIZATION.csv"
report_file.parent.mkdir(exist_ok=True)
with report_file.open("w",newline="",encoding="utf-8") as f:
    writer=csv.writer(f)
    writer.writerow(["part","folder","pdf_count"])
    writer.writerows(report)
if conflicts:
    (report_file.parent/"SRK_TEN_FOLDER_CONFLICTS.txt").write_text(
        "\n".join(conflicts),encoding="utf-8"
    )
print("Report:",report_file)
print("No original PDF contents were modified.")
print("Run this cell again if interrupted; completed moves are retained.")
