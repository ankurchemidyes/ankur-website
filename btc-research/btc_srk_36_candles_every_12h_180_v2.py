# BITCOIN SRK ORIGINAL 1H CANDLE PDF ARCHIVE — COLAB
# Native Bitstamp BTC/USD hourly OHLCV; 2013 to last CLOSED hour.
# Exactly 36 REAL consecutive hourly candles per PDF, sliding by 12 hours.
# SRK1.pdf, SRK2.pdf ...; every PDF includes its unique pattern number.
# No indicators, no simulated candles, no entry/exit advice.
import sys, subprocess
subprocess.check_call([sys.executable,"-m","pip","install","-q",
                       "pandas","numpy","requests","reportlab","pypdf"])
import os, csv, json, time, hashlib
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from pypdf import PdfReader
from google.colab import drive

drive.mount("/content/drive")
ROOT=Path("/content/drive/MyDrive/BTC_SRK_36_CANDLE_12H_STEP_2013_NOW")
CACHE=ROOT/"_ORIGINAL_EXCHANGE_DATA"
PDFS=ROOT/"SRK_PDFS_180"
AUDIT=ROOT/"REPORTS"
for p in (CACHE,PDFS,AUDIT):p.mkdir(parents=True,exist_ok=True)
STATUS=ROOT/"RUN_STATUS.txt"
START=pd.Timestamp("2013-01-01",tz="UTC")
# Freeze end at start of run. This is the last COMPLETE hour's open.
END=pd.Timestamp.now(tz="UTC").floor("h")-pd.Timedelta(hours=1)
START_SEC=int(START.timestamp())
END_SEC=int(END.timestamp())
COLUMNS=["time","open","high","low","close","volume","source"]
STATE=CACHE/"DOWNLOAD_STATE.json"
BATCH_SIZE=20
SOURCE_URL="https://www.bitstamp.net/api/v2/ohlc/btcusd/"
session=requests.Session()
session.mount("https://",HTTPAdapter(max_retries=Retry(
    total=7,backoff_factor=1.5,
    status_forcelist=[429,500,502,503,504],allowed_methods=["GET"])))

def status(step,detail=""):
    message=f"SRK BTC 1H candle research\nStage: {step}\nDetails: {detail}\nUTC: {datetime.now(timezone.utc).isoformat()}\n"
    STATUS.write_text(message,encoding="utf-8")
    print(message,flush=True)

def state_save(obj):
    tmp=STATE.with_name(STATE.name+".tmp")
    tmp.write_text(json.dumps(obj,indent=2),encoding="utf-8")
    os.replace(tmp,STATE)

def request_history(cursor):
    r=session.get(SOURCE_URL,
       params={"step":3600,"limit":1000,"end":int(cursor)},timeout=90)
    r.raise_for_status()
    items=r.json().get("data",{}).get("ohlc",[])
    if not items:raise RuntimeError(f"Bitstamp returned no OHLC at {cursor}")
    values=[];timestamps=[]
    for item in items:
        ts=int(item["timestamp"])
        timestamps.append(ts)
        if ts<START_SEC or ts>END_SEC:continue
        values.append((
            pd.to_datetime(ts,unit="s",utc=True),
            *[float(item[k]) for k in ("open","high","low","close","volume")],
            "Bitstamp BTC/USD"
        ))
    oldest=min(timestamps)
    if oldest>=cursor:raise RuntimeError("Historical pagination stalled")
    return values,oldest

def download_original():
    checkpoint=json.loads(STATE.read_text()) if STATE.exists() else {
        "cursor":END_SEC+3600,"chunk":0,"completed":False,
        "oldest_observed":None
    }
    if checkpoint.get("completed"):
        # Fetch the newest period again if the last completed hour grew.
        # Do not overwrite old chunks; deduplication favors the newer cache.
        old_end=int(checkpoint.get("last_end",0))
        if END_SEC>old_end:
            checkpoint["cursor"]=END_SEC+3600
            checkpoint["completed"]=False
            checkpoint["refresh_stop"]=old_end-3600
    status("DOWNLOADING",f"Original BTC/USD hourly candles; last complete hour {END}")
    if checkpoint.get("completed"):return
    cursor=int(checkpoint["cursor"])
    earliest_required=int(checkpoint.get("refresh_stop",START_SEC))
    batch=[];requests_done=0
    while cursor>=max(START_SEC,earliest_required):
        rows,oldest=request_history(cursor)
        batch.extend(rows)
        cursor=oldest-1
        requests_done+=1
        checkpoint["oldest_observed"]=str(pd.to_datetime(oldest,unit="s",utc=True))
        if requests_done%BATCH_SIZE==0 or cursor<max(START_SEC,earliest_required):
            number=int(checkpoint["chunk"])
            out=CACHE/f"BITSTAMP_1H_CHUNK_{number:05d}.csv.gz"
            tmp=CACHE/(out.name+".partial")
            pd.DataFrame(batch,columns=COLUMNS).to_csv(
                tmp,index=False,compression="gzip")
            if not tmp.exists() or tmp.stat().st_size<75:
                raise RuntimeError("Drive cache write error")
            os.replace(tmp,out)
            checkpoint.update({
                "cursor":cursor,"chunk":number+1,"last_end":END_SEC})
            state_save(checkpoint)
            batch.clear()
            status("DOWNLOADING",
                f"Saved chunk {number+1}; reached {checkpoint['oldest_observed']}")
        time.sleep(0.15)
    checkpoint.update({"cursor":cursor,"completed":True,
                       "last_end":END_SEC,"refresh_stop":START_SEC})
    state_save(checkpoint)
download_original()

status("VALIDATING","Reading genuine exchange data and checking hourly gaps")
files=sorted(CACHE.glob("BITSTAMP_1H_CHUNK_*.csv.gz"))
if not files:raise RuntimeError("No exchange candles downloaded")
frames=[]
for f in files:
    p=pd.read_csv(f)
    p["time"]=pd.to_datetime(p["time"],format="mixed",utc=True)
    frames.append(p)
df=pd.concat(frames,ignore_index=True)
df=df.sort_values("time").drop_duplicates("time",keep="last").reset_index(drop=True)
df=df[(df.time>=START)&(df.time<=END)].reset_index(drop=True)
numeric=df[["open","high","low","close","volume"]]
valid=(
    np.isfinite(numeric).all(axis=1)
    &(numeric[["open","high","low","close"]]>0).all(axis=1)
    &(df.volume>=0)
    &(df.high>=df[["open","close","low"]].max(axis=1))
    &(df.low<=df[["open","close","high"]].min(axis=1))
    &(df.time.dt.minute==0)&(df.time.dt.second==0)
)
df.loc[~valid].to_csv(AUDIT/"INVALID_EXCHANGE_ROWS.csv",index=False)
df=df.loc[valid].reset_index(drop=True)
if len(df)<36:raise RuntimeError("Fewer than 36 real 1H candles available")
df["difference"]=df.time.diff()
df["segment"]=df.difference.ne(pd.Timedelta(hours=1)).cumsum()
gaps=[]
for i in range(1,len(df)):
    if df.segment.iat[i]!=df.segment.iat[i-1]:
        diff=df.difference.iat[i]
        gaps.append({
            "previous_utc":str(df.time.iat[i-1]),
            "next_utc":str(df.time.iat[i]),
            "missing_hours":max(0,int(diff/pd.Timedelta(hours=1))-1)
        })
pd.DataFrame(gaps,columns=["previous_utc","next_utc","missing_hours"]).to_csv(
    AUDIT/"MISSING_HOURLY_CANDLES.csv",index=False)
df.drop(columns=["difference","segment"]).to_csv(
    CACHE/"CLEAN_BITSTAMP_1H_2013_NOW.csv.gz",
    index=False,compression="gzip")
annual=df.groupby(df.time.dt.year).agg(
    candles=("close","size"),first_utc=("time","min"),
    last_utc=("time","max"))
annual.to_csv(AUDIT/"YEARLY_COVERAGE.csv")
status("DATA_READY",f"{len(df):,} real 1H candles; {len(gaps):,} gap boundaries")

# Use only 36 consecutive real candles; a missing hour invalidates that window.
# Each segment: window indices [0..35], [12..47], [24..59] etc.
WINDOW=36
STEP=12
windows=[]
for segment,part in df.groupby("segment",sort=False):
    ids=part.index.to_numpy()
    for local_start in range(0,len(ids)-WINDOW+1,STEP):
        start=int(ids[local_start])
        end=start+WINDOW
        t=df.time.iat[start]
        window=df.iloc[start:end]
        # Code representing last 3 physical candle colors
        colors="".join(
            "G" if c>=o else "R"
            for o,c in zip(window.open.tail(3),window.close.tail(3))
        )
        pattern_id=1+sum((1 if ch=="G" else 0)<<(2-j)
                         for j,ch in enumerate(colors))
        digest=hashlib.sha256(
            window[["time","open","high","low","close","volume"]]
            .to_csv(index=False).encode("utf-8")).hexdigest()
        windows.append((start,end,t,colors,pattern_id,digest))
if not windows:raise RuntimeError("No complete 36-candle windows")

PAGE_W,PAGE_H=1100,520
GREEN=HexColor("#089879")
RED=HexColor("#D45156")
INK=HexColor("#30343B")
GREY=HexColor("#757A84")
GRID=HexColor("#DCE1E6")

def draw_page(filename,n,part,colors,pattern_id):
    pdf=canvas.Canvas(str(filename),pagesize=(PAGE_W,PAGE_H),pageCompression=1)
    # Rotate the ENTIRE drawn page without adding any label or text.
    pdf.translate(PAGE_W, PAGE_H)
    pdf.rotate(180)
    first=part.time.iloc[0]
    last=part.time.iloc[-1]
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold",19)
    pdf.drawString(55,486,f"SRK{n}    |    PATTERN NUMBER: {n:06d}")
    pdf.setFont("Helvetica",11)
    pdf.drawString(
        55,465,
        f"BITCOIN BTC/USD  |  1H  |  36 REAL CANDLES  |  "
        f"12H SLIDING STEP  |  UTC  |  LAST 3: {colors} (TYPE {pattern_id})"
    )
    pdf.drawString(
        55,449,
        f"Window: {first:%Y-%m-%d %H:%M} UTC to "
        f"{last+pd.Timedelta(hours=1):%Y-%m-%d %H:%M} UTC"
        "  |  Source: Bitstamp public BTC/USD OHLCV"
    )

    x0,x1=78,1025
    y0,y1=92,420
    w=(x1-x0)/36
    op=part.open.to_numpy(float)
    hi=part.high.to_numpy(float)
    lo=part.low.to_numpy(float)
    cl=part.close.to_numpy(float)
    pmin=float(lo.min());pmax=float(hi.max())
    padding=max((pmax-pmin)*0.08,pmax*0.0003)
    pmin-=padding;pmax+=padding
    X=lambda i:x0+(i+0.5)*w
    Y=lambda v:y0+(v-pmin)/(pmax-pmin)*(y1-y0)
    for k in range(6):
        price=pmin+(pmax-pmin)*k/5
        y=Y(price)
        pdf.setStrokeColor(GRID)
        pdf.setLineWidth(0.7)
        pdf.line(x0,y,x1,y)
        pdf.setFont("Helvetica",9)
        pdf.setFillColor(GREY)
        pdf.drawString(x1+8,y-3,f"{price:,.2f}")
    for k in range(36):
        color=GREEN if cl[k]>=op[k] else RED
        pdf.setStrokeColor(color);pdf.setFillColor(color)
        pdf.setLineWidth(1.4)
        pdf.line(X(k),Y(lo[k]),X(k),Y(hi[k]))
        body=min(14,w*0.60)
        bottom=min(Y(op[k]),Y(cl[k]))
        h=max(1.8,abs(Y(cl[k])-Y(op[k])))
        pdf.rect(X(k)-body/2,bottom,body,h,fill=1,stroke=0)
    pdf.setFillColor(GREY)
    pdf.setFont("Helvetica",9)
    for k in (0,6,12,18,24,30,35):
        label=part.time.iat[k].strftime("%d/%m %H:%M")
        pdf.drawCentredString(X(k),72,label)
    pdf.setFont("Helvetica",9)
    pdf.drawString(
        55,34,
        "Raw 1H candles only — NO indicators, entry/exit signals, "
        "forecast, smoothing or fabricated OHLC values."
    )
    pdf.save()

manifest=AUDIT/"SRK_PAGE_MANIFEST_180.csv"
# Source fingerprint ensures a changed candle cannot incorrectly reuse a PDF.
old={}
if manifest.exists():
    with manifest.open(newline="",encoding="utf-8") as f:
        for item in csv.DictReader(f):old[item["filename"]]=item
rows=[];created=0;reused=0
status("CREATING_PDFS",f"1 PDF per 36-hour window; {len(windows):,} PDF files expected")
for index,(start,end,t,colors,pattern_id,digest) in enumerate(windows,1):
    name=f"SRK{index}.pdf"
    path=PDFS/name
    prev=old.get(name)
    use=(path.exists() and prev is not None
         and prev.get("data_sha256")==digest)
    if use:
        try:use=(len(PdfReader(str(path),strict=False).pages)==1)
        except Exception:use=False
    if use:reused+=1
    else:
        tmp=PDFS/(name+".partial")
        draw_page(tmp,index,df.iloc[start:end],colors,pattern_id)
        if len(PdfReader(str(tmp),strict=False).pages)!=1:
            raise RuntimeError("Failed to verify "+name)
        os.replace(tmp,path)
        created+=1
    rows.append({
        "filename":name,"pattern_number":index,
        "pattern_type_1_to_8":pattern_id,
        "last_3_candle_colors":colors,
        "window_first_utc":str(t),
        "window_last_candle_utc":str(df.time.iat[end-1]),
        "candles":36,"step_hours":STEP,"data_sha256":digest,
        "source":"Bitstamp BTC/USD"
    })
    if index%50==0 or index==len(windows):
        partial=AUDIT/"SRK_PAGE_MANIFEST.partial.csv"
        pd.DataFrame(rows).to_csv(partial,index=False)
        os.replace(partial,manifest)
        status("CREATING_PDFS",
            f"{index:,}/{len(windows):,}; new {created:,}; reused {reused:,}")

report=[
    "BTC SRK HOURLY ORIGINAL CANDLE DATASET",
    f"UTC generated: {datetime.now(timezone.utc).isoformat()}",
    "Source: Bitstamp BTC/USD 1H public OHLCV",
    f"Requested start: {START}",
    f"Last complete hour available at run: {END}",
    f"First actual 1H candle: {df.time.iloc[0]}",
    f"Last actual 1H candle: {df.time.iloc[-1]}",
    f"Actual valid 1H candles: {len(df):,}",
    f"Hourly data gap boundaries: {len(gaps):,}",
    f"36-candle PDF windows: {len(windows):,}",
    f"SRK PDFs created this run: {created:,}",
    f"SRK PDFs reused this run: {reused:,}",
    "Candles per PDF: EXACTLY 36",
    "Shift between next valid windows within a continuous segment: 12 hours",
    "Skipped any window crossing missing-data gap: YES",
    "Indicators: NONE",
    "Chart prices: Original Bitstamp BTC/USD OHLC",
    "Pattern number: sequential per PDF",
    "Pattern type: 1-8 based on color of last 3 candles",
    f"PDF folder: {PDFS}",
]
(AUDIT/"SRK_FINAL_SUMMARY_180.txt").write_text(
    "\n".join(report)+"\n",encoding="utf-8")
status("COMPLETE",f"{len(windows):,} SRK PDFs; complete summary in REPORTS")
print("\n"+"\n".join(report))
