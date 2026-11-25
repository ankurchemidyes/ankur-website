# Save a permanent Hindi PDF handbook from the pinned GitHub Markdown source.
# Does not read or alter any BTC price data/PDF datasets.
import sys,subprocess,urllib.request,re,html
from pathlib import Path
subprocess.check_call([sys.executable,"-m","pip","install","-q","weasyprint>=62","markdown>=3.5"])
subprocess.run(["apt-get","update","-qq"],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
subprocess.run(["apt-get","install","-y","-qq","fonts-noto-core","fonts-noto-extra"],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
from google.colab import drive,files
from weasyprint import HTML
import markdown

drive.mount("/content/drive")
url="https://raw.githubusercontent.com/ankurchemidyes/ankur-website/6924c94add661dc4b5531a1a4fcac4d88ee9f7ea/btc-research/BTC_RESEARCH_PERMANENT_RECOVERY_HANDBOOK_HINDI.md"
md=urllib.request.urlopen(url,timeout=90).read().decode("utf-8")
# Make naked URLs clickable in exported PDF.
md=re.sub(r"(?m)^(https://[^\s<]+)$",lambda m:f"[{m.group(1)}]({m.group(1)})",md)
body=markdown.markdown(md,extensions=["tables","fenced_code","toc"])
css=r"""
@page {
 size: A4; margin: 16mm 16mm 19mm 16mm;
 @bottom-right {
 content: "पेज " counter(page) " / " counter(pages);
 font: 9pt "Noto Sans Devanagari", sans-serif;
 color: #64748b;
 }
}
* { box-sizing: border-box; }
body { font-family: "Noto Sans Devanagari","Noto Sans",sans-serif;
 font-size: 9.4pt; line-height: 1.65; color: #18243a; }
h1 { font-size: 20pt; line-height: 1.28; color:#122a52; border-bottom:3px solid #0f766e; padding-bottom:10px; }
h2 { font-size: 13.3pt; color:#0f766e; margin-top:17pt; page-break-after:avoid; }
h3 { font-size: 10.7pt; color:#123b62; page-break-after:avoid; }
p,li { orphans:3; widows:3; }
table { width:100%; border-collapse:collapse; margin:10px 0; font-size:8.3pt;
 table-layout:fixed; }
thead { display:table-header-group; }
tr { page-break-inside:avoid; }
td,th { border:1px solid #cbd5e1; padding:6px; vertical-align:top;
 overflow-wrap:anywhere; }
th { background:#e8f5f2; color:#164e48; }
code,pre { font-family:"DejaVu Sans Mono",monospace; font-size:8pt;
 overflow-wrap:anywhere; white-space:pre-wrap; }
pre { background:#f1f5f9; padding:10px; border-radius:5px; }
blockquote { border-left:3px solid #0f766e; margin-left:0; padding-left:13px;
 background:#f8fafc; }
a { color:#1d4ed8; text-decoration:none; overflow-wrap:anywhere; }
strong { font-weight:700; }
hr { border:0;border-top:1px solid #cbd5e1; margin:18px 0; }
"""
doc="<!DOCTYPE html><html lang='hi'><head><meta charset='utf-8'><style>"+css+"</style></head><body>"+body+"</body></html>"
root=Path("/content/drive/MyDrive/BTC_PERMANENT_BACKUP_HANDBOOK")
root.mkdir(parents=True,exist_ok=True)
pdf=root/"BTC_SRK_2013_2026_COMPLETE_RECOVERY_RULES_HINDI.pdf"
source=root/"BTC_RESEARCH_PERMANENT_RECOVERY_HANDBOOK_HINDI.md"
source.write_text(md,encoding="utf-8")
HTML(string=doc,base_url="https://github.com/").write_pdf(str(pdf))
print("PDF सफलतापूर्वक बनी:",pdf)
print("PDF MB:",round(pdf.stat().st_size/1024/1024,2))
print("पाठ का दूसरा बैकअप:",source)
files.download(str(pdf))
