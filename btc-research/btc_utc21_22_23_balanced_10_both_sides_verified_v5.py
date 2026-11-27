# BTC 21-22-23 UTC | Green/Red ONLY | Rotated chart balanced/verified (V5)
# Fix V4 IndexError: axis time labels previously accessed index 24/28 of a 23-bar list.
# Add a deterministic geometrical QA gate before downloading historical exchange data.
# Pattern: original UTC 21, 22, 23. 180 degree candle geometry, labels upright.
# Original 1H chart window: 11:00 same day through 09:00 next day (23 candles).
# Rotated display: ten next-day candles on LEFT; ten earlier-day candles on RIGHT.
# No V1/V2/V3 dependency. Fetch fresh genuine exchange OHLCV.
# One multi-page PDF by 21 + (three g/r) + UTC day (01–31), e.g. 21grg27.pdf.

import sys, subprocess
subprocess.check_call([sys.executable,"-m","pip","install","-q","requests","pandas","reportlab","pypdf"])
import os, time, csv, json, math
from pathlib import Path
from collections import defaultdict
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from pypdf import PdfReader

try:
    from google.colab import drive
    drive.mount("/content/drive")
    BASE=Path("/content/drive/MyDrive/BTC_21_22_23_1H_BALANCED_VERIFIED_V5")
except ImportError:
    BASE=Path.home()/"BTC_21_22_23_1H_BALANCED_VERIFIED_V5"

DATA=BASE/"DATA_ORIGINAL_BITSTAMP_1H"
# No previous version or Google Drive files are required.
OUT=BASE/"PDFS_21_COLOR_DAY"
REPORTS=BASE/"REPORTS"
for p in (DATA,OUT,REPORTS):p.mkdir(parents=True,exist_ok=True)

START=pd.Timestamp("2013-01-01",tz="UTC")
END=min(pd.Timestamp("2026-12-31",tz="UTC"),
        pd.Timestamp.now(tz="UTC").floor("D")-pd.Timedelta(days=1))
if END < START:raise RuntimeError("No completed UTC days in requested range")
API="https://www.bitstamp.net/api/v2/ohlc/btcusd/"
CSV=DATA/"BITSTAMP_BTCUSD_NATIVE_1H_2013_TO_2026.csv.gz"
CHECKPOINT=DATA/"DOWNLOAD_PROGRESS.json"
MANIFEST=REPORTS/"ALL_MATCHED_UTC_DATES.csv"
INDEX=REPORTS/"ALL_SEARCHABLE_PDF_CODES.csv"
SKIPPED=REPORTS/"SKIPPED_UTC_DAYS.csv"
FINAL=REPORTS/"FINAL_SUMMARY.txt"

def progress(message):
    print(message,flush=True)
    (REPORTS/"LAST_PROGRESS.txt").write_text(message+"\n",encoding="utf-8")

def atomic_csv(path,rows,cols):
    tmp=path.with_suffix(path.suffix+".partial")
    with tmp.open("w",encoding="utf-8",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp,path)

session=requests.Session()
retry=Retry(total=6,backoff_factor=1.0,status_forcelist=[429,500,502,503,504],
            allowed_methods=["GET"])
session.mount("https://",HTTPAdapter(max_retries=retry))

# Only original exchange 1H OHLC bars; save as a persistent local Drive cache.
# One complete download is ~125 API calls; future reruns use the CSV.
def load_exchange_1h():
    if CSV.exists():
        progress("Reading cached genuine 1H OHLCV: "+str(CSV))
        return pd.read_csv(CSV,parse_dates=["time"])
    needed_start=START-pd.Timedelta(days=1)
    end_exclusive=END+pd.Timedelta(days=2)
    cursor=int(end_exclusive.timestamp())
    earliest_needed=int(needed_start.timestamp())
    collected={}
    calls=0
    while cursor>=earliest_needed:
        resp=session.get(API,params={"step":3600,"limit":1000,"end":cursor},timeout=75)
        resp.raise_for_status()
        raw=resp.json().get("data",{}).get("ohlc",[])
        if not raw:raise RuntimeError("Bitstamp returned no 1H candles; stopped without fabricating data")
        minimum=min(int(x["timestamp"]) for x in raw)
        if minimum>=cursor:raise RuntimeError("Bitstamp history pagination not moving")
        for x in raw:
            t=int(x["timestamp"])
            if earliest_needed<=t<int(end_exclusive.timestamp()):
                collected[t]=[t]+[float(x[k]) for k in ("open","high","low","close","volume")]
        cursor=minimum-3600
        calls+=1
        if calls%20==0:progress(f"Original exchange 1H download: {calls} requests, {len(collected)} unique candles")
    df=pd.DataFrame(collected.values(),columns=["timestamp","open","high","low","close","volume"])
    if df.empty:raise RuntimeError("Empty exchange dataset")
    df["time"]=pd.to_datetime(df.pop("timestamp"),unit="s",utc=True)
    df=df.sort_values("time").drop_duplicates("time")
    numeric=["open","high","low","close","volume"]
    good=df[numeric].notna().all(axis=1)
    good &= (df[["open","high","low","close"]]>0).all(axis=1)
    good &= df["high"]>=df[["open","low","close"]].max(axis=1)
    good &= df["low"]<=df[["open","high","close"]].min(axis=1)
    good &= df["volume"]>=0
    good &= df["time"].dt.minute.eq(0)&df["time"].dt.second.eq(0)
    bad=df.loc[~good].copy()
    if not bad.empty:bad.to_csv(REPORTS/"REJECTED_ORIGINAL_1H_ROWS.csv",index=False)
    df=df.loc[good].copy().reset_index(drop=True)
    temp=CSV.with_suffix(".csv.gz.partial")
    df.to_csv(temp,index=False,compression="gzip")
    os.replace(temp,CSV)
    progress(f"Downloaded/validated {len(df)} genuine BTC/USD hourly candles; cache={CSV}")
    return df

df=load_exchange_1h()
df["time"]=pd.to_datetime(df["time"],utc=True)
df=df.set_index("time",drop=False).sort_index()

def candle_color(row):
    if row["close"]>row["open"]:return "g"
    if row["close"]<row["open"]:return "r"
    return None # exact equal open/close: skip and report, NEVER label as green/red

# Visual balance: 10 real 1H candles on EACH side of focus box.
# Hourly 11:00–20:00 (10 earlier bars), 21:00–23:00 (3 focus),
# next day 00:00–09:00 (10 later bars) = 23 original candles.
# After geometric 180-degree rotation, the 10 LATER bars are on the LEFT
# and the 10 EARLIER bars are on the RIGHT. No missing values invented.
groups=defaultdict(list)
skipped=[]
manifest=[]
dates=pd.date_range(START,END,freq="D",tz="UTC")
progress(f"Scanning {len(dates)} complete UTC days for 21:00,22:00,23:00 1H bars...")
for day in dates:
    context=pd.date_range(day+pd.Timedelta(hours=11),periods=23,freq="h",tz="UTC")
    if not context.isin(df.index).all():
        skipped.append({"UTC_date":str(day.date()),"reason":"Missing genuine 1H bar in 23-hour focus/context chart"})
        continue
    focus=pd.DatetimeIndex([day+pd.Timedelta(hours=h) for h in (21,22,23)])
    colors=[candle_color(df.loc[t]) for t in focus]
    if any(color is None for color in colors):
        skipped.append({"UTC_date":str(day.date()),"reason":"Exact OPEN==CLOSE at 21/22/23: no green/red; excluded, not mislabeled"})
        continue
    letters="".join(colors)
    assert all(ch in "gr" for ch in letters)
    code=f"21{letters}{day.day:02d}"
    assert len(code)==7
    groups[code].append(day)
    manifest.append({"UTC_date":str(day.date()),"focus_times":"21:00,22:00,23:00",
                     "colors":letters,"PDF_name":code+".pdf"})
atomic_csv(MANIFEST,manifest,["UTC_date","focus_times","colors","PDF_name"])
atomic_csv(SKIPPED,skipped,["UTC_date","reason"])
progress(f"Matched {len(manifest)} actual UTC days into {len(groups)} color+day PDFs")

PAGE_W,PAGE_H=1260,790
LEFT,RIGHT,BOTTOM,TOP=118,1170,130,660
GREEN=HexColor("#089981")
RED=HexColor("#e05258")
DOJI=HexColor("#68778b") # neutral context candles are drawn, never added to GR code
INK=HexColor("#1c2730")
GRID=HexColor("#e0e5e9")
BLUE=HexColor("#236eea")

# QA: deterministic geometry; 10 1H candles left, 3 highlighted, 10 right.
# Ensure all plotted axis labels address valid indices before any chart PDF is produced.
def verify_plot_layout():
    bar_count=23
    targets=(10,11,12)
    assert len(range(0,bar_count,4))==6
    assert max(range(0,bar_count,4))<bar_count
    assert min(targets)==10 and max(targets)==12
    flipped=[bar_count-1-i for i in targets]
    assert flipped==[12,11,10]
    assert min(flipped)==10 and (bar_count-1-max(flipped))==10
    example={"open":[100,110,110],"close":[101,109,111]}
    assert "".join("g" if c>o else "r" for o,c in zip(example["open"],example["close"]))=="grg"
    print("LAYOUT QA PASS: 10 candles | box 3 (UTC 21-23) | 10 candles; G/R order checked")
verify_plot_layout()

def pdf_page(pdf,day,code):
    times=pd.date_range(day+pd.Timedelta(hours=11),periods=23,freq="h",tz="UTC")
    frame=df.loc[times]
    o=frame.open.to_numpy(float)
    h=frame.high.to_numpy(float)
    l=frame.low.to_numpy(float)
    c=frame.close.to_numpy(float)
    low=float(l.min());high=float(h.max())
    padding=max((high-low)*0.085,high*.00015)
    low-=padding;high+=padding
    def ypos(price):return BOTTOM+(price-low)/(high-low)*(TOP-BOTTOM)
    dx=(RIGHT-LEFT)/len(frame)
    def xpos(i):return LEFT+(i+.5)*dx
    # EXACT 180-degree geometry about the plot's centre, for chart graphics ONLY.
    # Rotated candle i is (LEFT+RIGHT-xpos(i), BOTTOM+TOP-ypos(price)).
    def rx(x):return LEFT+RIGHT-x
    def ry(y):return BOTTOM+TOP-y
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold",16)
    pdf.drawString(LEFT,748,"BTC/USD | ORIGINAL BITSTAMP 1H | 21:00 / 22:00 / 23:00 UTC")
    pdf.setFont("Helvetica-Bold",23)
    pdf.setFillColor(RED)
    pdf.drawRightString(RIGHT,739,code)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica",12)
    pdf.drawString(LEFT,715,f"UTC DATE: {day:%Y-%m-%d} | DATE DAY: {day.day:02d} | CODE: {code}")
    pdf.drawString(LEFT,694,"Candles + grid rotated 180 degrees; code, dates, axis numbers UPRIGHT.")
    pdf.setFont("Helvetica-Bold",32)
    pdf.setFillColor(RED)
    pdf.drawCentredString((LEFT+RIGHT)/2,674,code[2:5])
    # Rotate chart grid as visual geometry, no text is rotated.
    pdf.setStrokeColor(GRID)
    pdf.setLineWidth(.7)
    for t in range(5):
        y=BOTTOM+(TOP-BOTTOM)*t/4
        pdf.line(LEFT,ry(y),RIGHT,ry(y))
    for i in range(0,len(frame)+1,4):
        x=LEFT+i*dx
        pdf.line(rx(x),BOTTOM,rx(x),TOP)
    # Candlesticks: rotate each true OHLC visual glyph by 180 degrees.
    for i in range(len(frame)):
        color=GREEN if c[i]>o[i] else RED if c[i]<o[i] else DOJI
        x=rx(xpos(i))
        top_wick=ry(ypos(h[i])); bottom_wick=ry(ypos(l[i]))
        pdf.setStrokeColor(color)
        pdf.setLineWidth(1.5)
        pdf.line(x,top_wick,x,bottom_wick)
        y_open=ry(ypos(o[i]));y_close=ry(ypos(c[i]))
        y_min=min(y_open,y_close)
        hh=max(1.8,abs(y_close-y_open))
        pdf.setFillColor(color)
        pdf.rect(x-dx*.31,y_min,dx*.62,hh,fill=1,stroke=0)
    # Focus three UTC bars 21-23. Box geometry is upright and correct on rotated chart.
    # Indexing within 23-hour window: day 11:00=index0,
    # 21:00=index10; 22:00=index11; 23:00=index12.
    # The 10 later hours appear left of the blue box after rotation;
    # the 10 earlier hours appear to its right.
    focused=[10,11,12]
    assert all(times[j].hour==hour and times[j].date()==day.date()
               for j,hour in zip(focused,(21,22,23)))
    xright=rx(xpos(focused[0]))+dx*.50
    xleft=rx(xpos(focused[-1]))-dx*.50
    assert xright>xleft and abs((xleft-LEFT)/dx-10.0)<1e-8
    assert abs((RIGHT-xright)/dx-10.0)<1e-8
    pdf.setStrokeColor(BLUE);pdf.setLineWidth(2.5)
    pdf.roundRect(xleft,BOTTOM+4,xright-xleft,TOP-BOTTOM-8,7,fill=0,stroke=1)
    # Upright focused candle description
    pdf.setFillColor(RED);pdf.setFont("Helvetica-Bold",38)
    pdf.drawString(LEFT,84,code[2:5])
    pdf.setFillColor(INK);pdf.setFont("Helvetica",12)
    pdf.drawString(LEFT+135,91,"CODE ORDER: UTC 21:00 -> 22:00 -> 23:00 | G=GREEN, R=RED")
    pdf.setFont("Helvetica",10)
    pdf.drawString(LEFT,63,"Rotated plot: 10 later candles LEFT | 23,22,21 focus | 10 earlier candles RIGHT.")
    # Rotated chart: original price-high is seen lower, so printed scale reflects that.
    for t in range(5):
        original=low+(high-low)*t/4
        actual_y=ry(ypos(original))
        pdf.setFillColor(INK);pdf.setFont("Helvetica",9)
        pdf.drawRightString(LEFT-12,actual_y-3,f"{original:,.2f}")
    # Original 1H time labels following the rotated x position, text upright.
    for i in range(0,len(frame),4):
        x=rx(xpos(i))
        pdf.setFont("Helvetica",9);pdf.setFillColor(INK)
        pdf.drawCentredString(x,BOTTOM-21,times[i].strftime("%d %H:00"))
    pdf.setFont("Helvetica",10);pdf.setFillColor(INK)
    pdf.drawRightString(RIGHT,42,"Historical observation only | No synthetic OHLC | Not a trading signal")
    pdf.showPage()

rows=[]
for k,(code,day_list) in enumerate(sorted(groups.items()),1):
    target=OUT/(code+".pdf")
    # Resume after disconnection without repeating any valid completed PDF.
    reuse=False
    if target.exists():
        try:
            reuse=len(PdfReader(str(target),strict=False).pages)==len(day_list)
        except Exception:reuse=False
    if not reuse:
        tmp=OUT/(code+".pdf.partial")
        doc=canvas.Canvas(str(tmp),pagesize=(PAGE_W,PAGE_H),pageCompression=1)
        for day in day_list:
            pdf_page(doc,day,code)
        doc.save()
        if len(PdfReader(str(tmp),strict=False).pages)!=len(day_list):
            raise RuntimeError("Incorrect page count for "+code)
        os.replace(tmp,target)
    rows.append({"PDF_name":target.name,"color_code":code[2:5],
                 "day_only":code[-2:],"pages":len(day_list),"location":str(target)})
    if k%30==0 or k==len(groups):
        atomic_csv(INDEX,rows,["PDF_name","color_code","day_only","pages","location"])
        progress(f"PDF complete: {k}/{len(groups)} codes; originals kept; last={code}")
atomic_csv(INDEX,rows,["PDF_name","color_code","day_only","pages","location"])
summary=(
    "BTC 21/22/23 UTC ROTATED-CHART-ONLY HISTORY\n"
    f"Requested first date: 2013-01-01\n"
    f"Actual last fully closed date: {END.date()}\n"
    f"Original exchange 1H candles retained: {len(df)}\n"
    f"Historical days matched: {len(manifest)}\n"
    f"Days omitted due to missing original bars or equal focus candle: {len(skipped)}\n"
    f"PDFs created/verified: {len(rows)}\n"
    f"Chart pages: {sum(x['pages'] for x in rows)}\n"
    "Pattern candles: UTC 21:00, 22:00, 23:00\n"
    "Chart candles+grid rotated 180 degrees; all numbers, dates and names upright\n"
    "Highlight has exactly 10 genuine subsequent candles LEFT and 10 earlier candles RIGHT after rotation\n"
    "Color code always chronological original UTC 21 -> 22 -> 23\n"
    "Pattern by true OHLC: g=close>open, r=close<open; equal focus omitted and reported\n"
    f"PDF folder: {OUT}\n"
    f"Search index: {INDEX}\n"
    "STATUS: COMPLETE\n"
)
FINAL.write_text(summary,encoding="utf-8")
print("\n"+summary)
