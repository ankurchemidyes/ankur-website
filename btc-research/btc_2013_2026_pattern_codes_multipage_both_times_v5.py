# BTC HISTORICAL UTC PATTERN ARCHIVE V5, 2013–2026.
# NO separate dated output PDF. One six-color code -> ONE MULTIPAGE PDF.
# Two independent studies: 23:00/00:00 and 11:00/12:00.
# Read genuine 5M/1H Bitstamp BTC/USD candles only; never invent missing bars.
# Last complete UTC day only. Original PDFs are not changed.
import sys,subprocess
subprocess.check_call([sys.executable,"-m","pip","install","-q","pandas","numpy","requests","reportlab","pypdf"])
import os,json,time,hashlib,csv
from pathlib import Path
from datetime import datetime,timezone
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
ROOT=Path("/content/drive/MyDrive/BTC_MATCHED_CODES_MULTIPAGE_V5")
CACHE=ROOT/"CACHE_5M_BITSTAMP"
PDFS=ROOT/"PDFS_GROUPED"
REPORTS=ROOT/"REPORTS"
for p in (CACHE,PDFS,REPORTS):p.mkdir(parents=True,exist_ok=True)
START=pd.Timestamp("2013-01-01",tz="UTC")
# A day is eligible only after all 24 of its 1H candles are closed.
LAST_COMPLETE_DAY=(pd.Timestamp.now(tz="UTC").floor("D")-pd.Timedelta(days=1))
# For D=Jan 1, 2013, upper panel requires previous day 20:00 onward;
# Bitstamp is queried from Dec 31, 2012 so this edge case can be checked.
DATA_START=START-pd.Timedelta(days=1)
NOW_5M=pd.Timestamp.now(tz="UTC").floor("5min")-pd.Timedelta(minutes=5)
END5=int(NOW_5M.timestamp())
EARLIEST5=int(DATA_START.timestamp())
SOURCE_URL="https://www.bitstamp.net/api/v2/ohlc/btcusd/"
HEAD=["time","open","high","low","close","volume"]
# If old clean source cache still exists, COPY it into the new project
# once to avoid repeated API downloads. Do not change the older project.
OLD_CACHED_ROOT=Path("/content/drive/MyDrive/BTC_UTC_23_5M_00_1H_2013_NOW")
if not (CACHE/"DOWNLOAD_STATE_5M.json").exists():
    old_checkpoint=OLD_CACHED_ROOT/"CACHE_5M_BITSTAMP/DOWNLOAD_STATE_5M.json"
    old_parts=OLD_CACHED_ROOT/"CACHE_5M_BITSTAMP/PARTS"
    if old_checkpoint.exists() and old_parts.is_dir():
        import shutil
        (CACHE/"PARTS").mkdir(parents=True,exist_ok=True)
        for old in sorted(old_parts.glob("5M_*.csv.gz")):
            new=CACHE/"PARTS"/old.name
            if not new.exists():
                shutil.copy2(old,new)
        shutil.copy2(old_checkpoint,CACHE/"DOWNLOAD_STATE_5M.json")
        print("Reused a COPY of earlier 5M cache in the new V5 folder")
old_native=OLD_CACHED_ROOT/"BITSTAMP_ORIGINAL_1H.csv.gz"
if old_native.exists() and not (ROOT/"BITSTAMP_ORIGINAL_1H.csv.gz").exists():
    import shutil
    shutil.copy2(old_native,ROOT/"BITSTAMP_ORIGINAL_1H.csv.gz")
    print("Reused a COPY of earlier native 1H cache in V5")
CHECKPOINT=CACHE/"DOWNLOAD_STATE_5M.json"
CHUNK_DIR=CACHE/"PARTS"
CHUNK_DIR.mkdir(exist_ok=True)
session=requests.Session()
session.mount("https://",HTTPAdapter(max_retries=Retry(
    total=8,backoff_factor=1.5,status_forcelist=[429,500,502,503,504],
    allowed_methods=["GET"])))
def announce(stage,message):
    msg=f"UTC: {datetime.now(timezone.utc).isoformat()} | {stage} | {message}"
    print(msg,flush=True)
    (ROOT/"STATUS.txt").write_text(msg+"\n",encoding="utf-8")
def save_json_atomically(path,data):
    partial=path.with_name(path.name+".partial")
    partial.write_text(json.dumps(data,indent=2),encoding="utf-8")
    os.replace(partial,path)
def fetch_5m(cursor):
    r=session.get(SOURCE_URL,params={"step":300,"limit":1000,"end":int(cursor),
        "exclude_current_candle":"true"},timeout=90)
    r.raise_for_status()
    items=r.json().get("data",{}).get("ohlc",[])
    if not items:raise RuntimeError("No Bitstamp 5M candles at cursor "+str(cursor))
    timestamps=[int(item["timestamp"]) for item in items]
    earliest=min(timestamps)
    if earliest>=cursor:raise RuntimeError("5M pagination stalled: "+str(cursor))
    rows=[]
    for item,ts in zip(items,timestamps):
        if EARLIEST5<=ts<=END5:
            rows.append([pd.to_datetime(ts,unit="s",utc=True)]
                       +[float(item[k]) for k in HEAD[1:]])
    return rows,earliest

def download_5m():
    state=json.loads(CHECKPOINT.read_text()) if CHECKPOINT.exists() else {
       "cursor":END5+300,"next_chunk":0,"completed":False,"last_end":0}
    if state.get("completed") and int(state.get("last_end",0))<END5:
       # Incremental refresh, overlaps earlier saved data for safe deduplication.
       state["cursor"]=END5+300
       state["refresh_stop"]=int(state["last_end"])-600
       state["completed"]=False
    if state.get("completed"):
       announce("DOWNLOAD","Already cached through "+str(state.get("last_end")))
       return
    cursor=int(state["cursor"])
    stop=max(EARLIEST5,int(state.get("refresh_stop",EARLIEST5)))
    buf=[];calls=0
    announce("DOWNLOAD","Bitstamp BTC/USD genuine 5-minute candles; resume enabled")
    while cursor>=stop:
       rows,earliest=fetch_5m(cursor)
       buf.extend(rows)
       cursor=earliest-1
       calls+=1
       if calls%35==0 or cursor<stop:
          idx=int(state["next_chunk"])
          target=CHUNK_DIR/f"5M_{idx:05d}.csv.gz"
          temp=CHUNK_DIR/(target.name+".partial")
          pd.DataFrame(buf,columns=HEAD).to_csv(temp,index=False,compression="gzip")
          os.replace(temp,target)
          buf.clear()
          state.update({"cursor":cursor,"next_chunk":idx+1,"last_end":END5})
          save_json_atomically(CHECKPOINT,state)
          announce("DOWNLOAD",f"chunk {idx+1}; oldest reached {pd.to_datetime(earliest,unit='s',utc=True)}")
       time.sleep(0.12)
    state.update({"completed":True,"cursor":cursor,"last_end":END5})
    save_json_atomically(CHECKPOINT,state)
    announce("DOWNLOAD","5-minute history cached successfully")

download_5m()
parts=sorted(CHUNK_DIR.glob("5M_*.csv.gz"))
if not parts:raise RuntimeError("No 5M data cache exists")
announce("VALIDATE",f"Reading {len(parts):,} cached 5M chunks")
frames=[]
for p in parts:
    temp=pd.read_csv(p)
    temp["time"]=pd.to_datetime(temp["time"],format="mixed",utc=True)
    frames.append(temp)
df5=pd.concat(frames,ignore_index=True).sort_values("time")
df5=df5.drop_duplicates("time",keep="last").reset_index(drop=True)
df5=df5[(df5.time>=DATA_START)&(df5.time<=NOW_5M)].copy()
numeric=df5[HEAD[1:]]
valid=np.isfinite(numeric).all(axis=1)&(numeric[["open","high","low","close"]]>0).all(axis=1)&(df5.volume>=0)&(df5.high>=df5[["open","close","low"]].max(axis=1))&(df5.low<=df5[["open","close","high"]].min(axis=1))&(df5.time.dt.minute%5==0)&(df5.time.dt.second==0)
df5.loc[~valid].to_csv(REPORTS/"INVALID_5M_ROWS.csv",index=False)
df5=df5.loc[valid].copy().set_index("time",drop=False)
announce("VALIDATE",f"5M valid candles: {len(df5):,}; first {df5.index.min()}")

# Reuse the prior ORIGINAL 1H exchange cache when available; otherwise obtain
# genuinely native Bitstamp 1H OHLCV using the same paginated endpoint.
OLD_1H=Path("/content/drive/MyDrive/BTC_SRK_36_CANDLE_12H_STEP_2013_NOW/_ORIGINAL_EXCHANGE_DATA/CLEAN_BITSTAMP_1H_2013_NOW.csv.gz")
ONE_H_CACHE=ROOT/"BITSTAMP_ORIGINAL_1H.csv.gz"
def load_1h():
    if OLD_1H.exists():
        announce("DATA_1H","Using earlier verified-format Bitstamp 1H OHLCV cache")
        out=pd.read_csv(OLD_1H)
    elif ONE_H_CACHE.exists():
        announce("DATA_1H","Using dedicated original 1H cached data")
        out=pd.read_csv(ONE_H_CACHE)
    else:
        announce("DATA_1H","Downloading native 1H original BTC/USD candles")
        cursor=int((LAST_COMPLETE_DAY+pd.Timedelta(days=1)).timestamp())
        oldest_need=int(DATA_START.timestamp())
        rows=[]
        while cursor>=oldest_need:
            r=session.get(SOURCE_URL,params={"step":3600,"limit":1000,"end":cursor},timeout=90)
            r.raise_for_status()
            items=r.json().get("data",{}).get("ohlc",[])
            if not items:raise RuntimeError("No 1H history returned")
            earliest=min(int(x["timestamp"]) for x in items)
            if earliest>=cursor:raise RuntimeError("1H pagination stalled")
            for x in items:
                ts=int(x["timestamp"])
                if oldest_need<=ts<=int(LAST_COMPLETE_DAY.timestamp())+23*3600:
                    rows.append([pd.to_datetime(ts,unit="s",utc=True)]
                                +[float(x[k]) for k in HEAD[1:]])
            cursor=earliest-1
            time.sleep(0.1)
        out=pd.DataFrame(rows,columns=HEAD)
        out.to_csv(ONE_H_CACHE,index=False,compression="gzip")
    out["time"]=pd.to_datetime(out["time"],format="mixed",utc=True)
    out=out.drop_duplicates("time",keep="last").sort_values("time")
    n=out[HEAD[1:]]
    good=np.isfinite(n).all(axis=1)&(n[["open","high","low","close"]]>0).all(axis=1)&(n.high>=n[["open","low","close"]].max(axis=1))&(n.low<=n[["open","high","close"]].min(axis=1))&(n.volume>=0)
    out=out.loc[good].copy().set_index("time",drop=False)
    return out
df1=load_1h()
announce("DATA_1H",f"Native 1H valid candles: {len(df1):,}")

# PDF layout: landscape single page, 5M upper and 1H lower, no extra indicators.
P_W,P_H=1320,820
COL_GREEN=HexColor("#089981")
COL_RED=HexColor("#D75159")
COL_DARK=HexColor("#222831")
COL_GRID=HexColor("#E5E7EB")
COL_MUTED=HexColor("#626C77")
def draw_panel(pdf,block,title,y0,y1,marked_times,x0=75,x1=1230):
    # The same three-reference-candle group is horizontally aligned in both charts.
    marked_indices=[j for j,t in enumerate(block.time) if t in marked_times]
    if len(marked_indices)!=3 or len(block) not in (84,32):
        raise RuntimeError("Inconsistent 5M/1H pattern candle timestamps")
    chart_width=1100.0
    target_x=430.0 if ACTIVE_MODE=="23" else 760.0
    center_frac=(marked_indices[0]+1.5)/len(block)
    x0=target_x-center_frac*chart_width
    x1=x0+chart_width
    n=len(block)
    op=block.open.to_numpy(float)
    hi=block.high.to_numpy(float)
    lo=block.low.to_numpy(float)
    cl=block.close.to_numpy(float)
    pmax=float(hi.max());pmin=float(lo.min())
    pad=max((pmax-pmin)*.08,pmax*.0002)
    pmax+=pad;pmin-=pad
    Y=lambda price:y0+(price-pmin)/(pmax-pmin)*(y1-y0)
    dx=(x1-x0)/n
    pdf.setFont("Helvetica-Bold",12)
    pdf.setFillColor(COL_DARK)
    pdf.drawString(x0,y1+22,title)
    for j in range(5):
        price=pmin+(pmax-pmin)*j/4
        y=Y(price)
        pdf.setStrokeColor(COL_GRID)
        pdf.setLineWidth(.6)
        pdf.line(x0,y,x1,y)
        pdf.setFont("Helvetica",8)
        pdf.setFillColor(COL_MUTED)
        pdf.drawString(x1+8,y-3,f"{price:,.2f}")
    for j in range(n):
        x=x0+(j+.5)*dx
        color=COL_GREEN if cl[j]>=op[j] else COL_RED
        pdf.setStrokeColor(color);pdf.setFillColor(color)
        pdf.setLineWidth(1.15)
        pdf.line(x,Y(lo[j]),x,Y(hi[j]))
        width=min(max(2,dx*.58),19)
        base=min(Y(op[j]),Y(cl[j]))
        tall=max(1.4,abs(Y(cl[j])-Y(op[j])))
        pdf.rect(x-width/2,base,width,tall,fill=1,stroke=0)
    # Identification only: highlight the THREE original candles used in the name.
    # The blue arrows do not represent a trading signal.
    selected=marked_indices
    if len(selected)!=3:
        raise RuntimeError("PDF reference candles are not visible: "+str(selected))
    pdf.setStrokeColor(HexColor("#2563EB"))
    pdf.setLineWidth(1.8)
    rect_left=x0+(min(selected)-0.35)*dx
    rect_right=x0+(max(selected)+1.35)*dx
    pdf.roundRect(rect_left,y0,rect_right-rect_left,y1-y0,3,stroke=1,fill=0)
    for k in selected:
        xx=x0+(k+.5)*dx
        yy=y1+17
        pdf.line(xx,yy,xx,yy-10)
        head=pdf.beginPath()
        head.moveTo(xx-4,yy-7)
        head.lineTo(xx,yy-13)
        head.lineTo(xx+4,yy-7)
        pdf.drawPath(head,stroke=1,fill=0)
    # Visual labels but no forecast, overlays or indicator studies.
    count_labels=8 if n>=80 else 7
    for j in sorted(set(np.linspace(0,n-1,count_labels,dtype=int).tolist())):
        pdf.setFillColor(COL_MUTED)
        pdf.setFont("Helvetica",8)
        pdf.drawCentredString(x0+(j+.5)*dx,y0-18,
                             block.time.iloc[j].strftime("%d %H:%M"))
    return

def color(c):
    return "g" if float(c.close)>float(c.open) else "r" if float(c.close)<float(c.open) else "d"
def pattern(three):
    return "".join(color(three.iloc[k]) for k in range(3))

# Every historical date adds one chart page to that day's exact pattern code.
# The PDF does NOT contain the date in its name; UTC date remains on each page.
MODES={
 "23":{
    "five_start":lambda day:day-pd.Timedelta(hours=3),
    "targets5":lambda day:pd.DatetimeIndex([day-pd.Timedelta(hours=1,minutes=10),
                                            day-pd.Timedelta(hours=1,minutes=5),
                                            day-pd.Timedelta(hours=1)]),
    "targets1":lambda day:pd.DatetimeIndex([day-pd.Timedelta(hours=2),
                                            day-pd.Timedelta(hours=1),day]),
    "title":"BTC/USD | UTC 23:00 5M & UTC DAY OPEN 00:00 1H",
    "top_title":"5M | 7 HOURS | Previous UTC day 21:00 - current day 03:55",
    "bottom_title":"1H | FULL UTC DAY 24 HOURS + 8 PRIOR CONTEXT HOURS",
    "code_tail":"00",
    "code_head":"23"
 },
 "11":{
    "five_start":lambda day:day+pd.Timedelta(hours=6,minutes=45),
    "targets5":lambda day:pd.DatetimeIndex([day+pd.Timedelta(hours=10,minutes=50),
                                            day+pd.Timedelta(hours=10,minutes=55),
                                            day+pd.Timedelta(hours=11)]),
    "targets1":lambda day:pd.DatetimeIndex([day+pd.Timedelta(hours=10),
                                            day+pd.Timedelta(hours=11),
                                            day+pd.Timedelta(hours=12)]),
    "title":"BTC/USD | UTC 11:00 5M & UTC MIDDAY 12:00 1H",
    "top_title":"5M | 7 HOURS | UTC 06:45 - 13:40",
    "bottom_title":"1H | FULL UTC DAY 24 HOURS + 8 PRIOR CONTEXT HOURS",
    "code_tail":"12",
    "code_head":"11"
 }
}
def pdf_draw(pdf,day,five,one,code,mode):
    config=MODES[mode]
    mark5=config["targets5"](day)
    mark1=config["targets1"](day)
    pdf.setFillColor(COL_DARK)
    pdf.setFont("Helvetica-Bold",17)
    pdf.drawString(75,780,config["title"])
    pdf.setFont("Helvetica-Bold",15)
    pdf.drawRightString(1240,784,code)
    pdf.setFont("Helvetica",11)
    pdf.drawString(75,761,f"UTC DATE: {day:%Y-%m-%d} | Bitstamp BTC/USD | original OHLC")
    pdf.setFont("Helvetica",11)
    pdf.drawRightString(1240,761,f"5M {code[2:5].upper()} | 1H {code[5:8].upper()}")
    draw_panel(pdf,five,config["top_title"],440,723,mark5)
    pdf.setStrokeColor(COL_GRID)
    pdf.line(75,416,1240,416)
    draw_panel(pdf,one,config["bottom_title"],95,368,mark1)
    pdf.setFont("Helvetica",9)
    pdf.setFillColor(COL_MUTED)
    pdf.drawString(75,43,
        "Blue boxes/arrows identify the THREE true candle timestamps; these are NOT trade signals.")
    pdf.drawString(75,27,
        f"5M UTC: {', '.join(t.strftime('%d %H:%M') for t in mark5)}")
    pdf.drawRightString(1240,27,
        f"1H UTC: {', '.join(t.strftime('%d %H:%M') for t in mark1)}")
    pdf.showPage()

# Scan all 2013-present dates. Keep a compact manifest; reuse V5 page data
# by loading original OHLC from cache, never copying pages from the old wrong PDFs.
from collections import defaultdict
manifest_rows=[]
skipped=[]
grouped=defaultdict(list)
days=pd.date_range(START,LAST_COMPLETE_DAY,freq="D",tz="UTC")
print("Historical UTC days to check:",len(days))
for i,day in enumerate(days,1):
    one_times=pd.date_range(day-pd.Timedelta(hours=8),periods=32,freq="h",tz="UTC")
    # 1H full day has 24 original candles; previous 8 are visual history context.
    if not one_times.isin(df1.index).all():
        for mode in MODES: skipped.append({"utc_day":str(day.date()),"mode":mode,"reason":"missing_1h"})
        continue
    for mode,config in MODES.items():
        five_times=pd.date_range(config["five_start"](day),periods=84,freq="5min",tz="UTC")
        target5=config["targets5"](day)
        target1=config["targets1"](day)
        if not five_times.isin(df5.index).all() or not target5.isin(df5.index).all():
            skipped.append({"utc_day":str(day.date()),"mode":mode,"reason":"missing_5m"})
            continue
        if not target1.isin(df1.index).all():
            skipped.append({"utc_day":str(day.date()),"mode":mode,"reason":"missing_1h_reference"})
            continue
        c5=pattern(df5.loc[target5])
        c1=pattern(df1.loc[target1])
        key=config["code_head"]+c5+c1+config["code_tail"]
        assert len(key)==10
        grouped[(mode,key)].append(day)
        manifest_rows.append({
            "study":mode,"code":key,"pdf":key+".pdf",
            "utc_date":str(day.date()),"five_m":c5,"one_h":c1,
            "five_first_utc":str(five_times[0]),
            "five_last_utc":str(five_times[-1]),
            "one_first_utc":str(one_times[0]),
            "one_last_utc":str(one_times[-1])
        })
    if i%500==0:print("Dates classified:",i,"/",len(days),flush=True)

MANIFEST=REPORTS/"HISTORICAL_DATE_AND_CODE_MANIFEST.csv"
pd.DataFrame(manifest_rows).to_csv(MANIFEST,index=False)
pd.DataFrame(skipped,columns=["utc_day","mode","reason"]).to_csv(
    REPORTS/"SKIPPED_UTC_DATES.csv",index=False)
print("Classified historical pages:",len(manifest_rows))
print("Separate grouped PDFs:",len(grouped))
print("Grouped PDFs with multiple pages:",sum(len(v)>1 for v in grouped.values()))

# Create directly ONE MULTIPAGE PDF PER PATTERN.
# ReportLab Canvas draws all corresponding dates sequentially, oldest first.
# Source cached OHLC and any earlier PDF folders remain intact.
summary=[]
for j,((mode,key),dates) in enumerate(sorted(grouped.items()),1):
    out_dir=PDFS/("UTC_23_00" if mode=="23" else "UTC_11_12")
    out_dir.mkdir(parents=True,exist_ok=True)
    outfile=out_dir/(key+".pdf")
    temp=out_dir/(key+".pdf.partial")
    ACTIVE_MODE=mode
    pdf=canvas.Canvas(str(temp),pagesize=(P_W,P_H),pageCompression=1)
    for day in dates:
        config=MODES[mode]
        five_t=pd.date_range(config["five_start"](day),periods=84,freq="5min",tz="UTC")
        one_t=pd.date_range(day-pd.Timedelta(hours=8),periods=32,freq="h",tz="UTC")
        pdf_draw(pdf,day,df5.loc[five_t],df1.loc[one_t],key,mode)
    pdf.save()
    pages=len(PdfReader(str(temp),strict=False).pages)
    if pages!=len(dates):
        raise RuntimeError(f"Incorrect page count for {key}: {pages} != {len(dates)}")
    os.replace(temp,outfile)
    summary.append({"study":mode,"pdf":outfile.name,"pages":pages,
                    "first_date":str(dates[0].date()),
                    "last_date":str(dates[-1].date())})
    if j%25==0 or j==len(grouped):
        pd.DataFrame(summary).to_csv(REPORTS/"GROUPED_PDF_PAGE_COUNTS.csv",index=False)
        print("Multipage PDFs created:",j,"/",len(grouped),
              "| Pages:",sum(x["pages"] for x in summary),flush=True)
pd.DataFrame(summary).to_csv(REPORTS/"GROUPED_PDF_PAGE_COUNTS.csv",index=False)
count_pages=sum(x["pages"] for x in summary)
if count_pages!=len(manifest_rows):
    raise RuntimeError("Audit mismatch between original dates and grouped PDF pages")
total23=sum(x["pages"] for x in summary if x["study"]=="23")
total11=sum(x["pages"] for x in summary if x["study"]=="11")
report=(
 "BTC UTC 5M/1H COLOR-CODE MULTIPAGE ARCHIVE V5\n"
 f"Historical days checked: {len(days)}\n"
 f"Total grouped PDF files: {len(summary)}\n"
 f"Total verified page count: {count_pages}\n"
 f"UTC 23:00/00:00 pages: {total23}\n"
 f"UTC 11:00/12:00 pages: {total11}\n"
 f"PDFs with more than one page: {sum(x['pages']>1 for x in summary)}\n"
 f"Skipped date/study combinations: {len(skipped)}\n"
 f"First UTC day: {days[0].date()}\n"
 f"Last UTC day: {days[-1].date()}\n"
 "Pattern name e.g. 23gggggg00.pdf or 11grrgrg12.pdf\n"
 "Same pattern code across multiple dates appears as consecutive pages.\n"
 "Every page preserves its original correct UTC date in chart heading.\n"
 "No old PDF was deleted or modified.\n"
 "100% no trading indicator/predictive signal.\n"
 f"PDF directory: {PDFS}\n"
)
(REPORTS/"COMPLETE_REPORT.txt").write_text(report,encoding="utf-8")
print("\nCOMPLETE\n"+report)
