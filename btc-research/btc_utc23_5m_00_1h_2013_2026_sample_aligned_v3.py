# BTC UTC 23:00 5M + NEXT DAY 00:00 1H — 2013 onward
# Educational historical PDF archive; no predictions, signals, or indicators.
# Upper: 7 real hours of 5-minute BTC/USD candles, previous UTC day 20:00 to current day 03:00.
# Lower: 24 real hourly BTC/USD candles, UTC day 00:00 to next day 00:00.
# Filename pattern: DD + 5M(previous two + 23:00) + 1H(previous two + 00:00) + 00
# Example: 23rrggrg00_YYYYMMDD.pdf. Date suffix prevents filename collisions.
# Incomplete or missing candles: skip day, never fabricate prices.
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
ROOT=Path("/content/drive/MyDrive/BTC_UTC_23_5M_00_1H_2013_NOW")
CACHE=ROOT/"CACHE_5M_BITSTAMP"
PDFS=ROOT/"PDFS_V3_SAMPLE_ALIGNED"
REPORTS=ROOT/"REPORTS_V3"
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
    # Make both highlighted three-candle windows share a common X-center.
    # 5M 7h: preceding day 21:00 -> next day 04:00, positions 22-24.
    # 1H full day plus previous 8h: preceding day 16:00 -> end-of-day,
    # pattern positions 6-8. Map both group centers to the same X.
    marked_indices=[j for j,t in enumerate(block.time) if t in marked_times]
    if len(marked_indices)!=3:
        raise RuntimeError("Expected exactly 3 real reference candles in each chart")
    marker_center_index=(marked_indices[0]+marked_indices[-1])/2+0.5
    common_marker_x=400.0
    if len(block)==84:
        x0=75.0
    elif len(block)==32:
        f=marker_center_index/len(block)
        x0=(common_marker_x-f*x1)/(1-f)
    else:
        raise RuntimeError("Unexpected candle count in panel: "+str(len(block)))
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
def pdf_draw(path,day,five,one,code,p5,p1):
    pdf=canvas.Canvas(str(path),pagesize=(P_W,P_H),pageCompression=1)
    pdf.setFillColor(COL_DARK)
    pdf.setFont("Helvetica-Bold",20)
    pdf.drawString(75,780,"BTC/USD | UTC 23:00 (5M) & DAY-OPEN 00:00 (1H)")
    pdf.setFont("Helvetica-Bold",12)
    pdf.drawRightString(1240,784,code)
    pdf.setFont("Helvetica",10)
    pdf.drawString(75,760,f"Study UTC day: {day:%Y-%m-%d}  |  Bitstamp BTC/USD  |  No indicators")
    pdf.drawRightString(1240,761,f"5M {p5.upper()}  |  1H {p1.upper()}")
    mark5=[day-pd.Timedelta(hours=1,minutes=10),day-pd.Timedelta(hours=1,minutes=5),day-pd.Timedelta(hours=1)]
    mark1=[day-pd.Timedelta(hours=2),day-pd.Timedelta(hours=1),day]
    draw_panel(pdf,five,"5M  |  7 HOURS  |  Previous day 21:00 - this day 04:00 UTC",440,723,mark5)
    pdf.setStrokeColor(COL_GRID);pdf.line(75,417,1240,417)
    draw_panel(pdf,one,"1H  |  FULL 24-HOUR UTC DAY  |  Plus 8 previous reference hours",95,368,mark1)
    pdf.setFont("Helvetica",9);pdf.setFillColor(COL_MUTED)
    pdf.drawString(75,44,"Blue markers: 5M 22:50 / 22:55 / 23:00 (previous day)")
    pdf.drawRightString(1240,44,"1H 22:00 / 23:00 (previous day) / 00:00 (this day)")
    pdf.drawString(75,28,"Real exchange candles only; historical descriptive chart, not a trade signal.")
    pdf.save()

manifest=REPORTS/"UTC_23_5M_00_1H_PDF_MANIFEST_V3.csv"
existing={}
if manifest.exists():
    with manifest.open(encoding="utf-8",newline="") as f:
        for x in csv.DictReader(f):existing[x["date_utc"]]=x

def valid_exact(index,expected):
    return len(index)==expected and index.is_unique
rows=[];skips=[];created=0;reused=0
days=pd.date_range(START,LAST_COMPLETE_DAY,freq="D",tz="UTC")
announce("PDF","Checking UTC dates: "+str(len(days)))
for i,day in enumerate(days,1):
    d=day.date().isoformat()
    five_times=pd.date_range(day-pd.Timedelta(hours=3),
                     periods=84,freq="5min",tz="UTC") # previous 21:00 -> current 03:55 (7h)
    one_times=pd.date_range(day-pd.Timedelta(hours=8),periods=32,freq="h",tz="UTC") # full 24h UTC day + 8 previous hours
    # Three 5m candles at 22:50,22:55,23:00 on prior day.
    target5=pd.DatetimeIndex([
      day-pd.Timedelta(hours=1,minutes=10),
      day-pd.Timedelta(hours=1,minutes=5),
      day-pd.Timedelta(hours=1)])
    # Three 1h candles prior day 22:00,23:00, then current day 00:00.
    target1=pd.DatetimeIndex([
      day-pd.Timedelta(hours=2),
      day-pd.Timedelta(hours=1),day])
    all5=five_times.append(target5).unique()
    all1=one_times.append(target1).unique()
    if not all5.isin(df5.index).all():
        skips.append({"date_utc":d,"reason":"missing_or_invalid_5M"})
        continue
    if not all1.isin(df1.index).all():
        skips.append({"date_utc":d,"reason":"missing_or_invalid_1H"})
        continue
    five=df5.loc[five_times]
    one=df1.loc[one_times]
    p5=pattern(df5.loc[target5])
    p1=pattern(df1.loc[target1])
    # DD (UTC calendar day) + three 5M colors + three 1H colors + 00 UTC.
    code=f"{day.day:02d}{p5}{p1}00"
    filename=f"{code}_{day:%Y%m%d}.pdf" # exact date+time+6 colors is unique; one PDF per key
    output=PDFS/filename
    fingerprint=hashlib.sha256(
        (five[HEAD].to_csv(index=False)+one[HEAD].to_csv(index=False)
        +df5.loc[target5,HEAD].to_csv(index=False)
        +df1.loc[target1,HEAD].to_csv(index=False)).encode()).hexdigest()
    old=existing.get(d)
    good=(old and old.get("sha256")==fingerprint
          and old.get("filename")==filename and output.is_file())
    if good:
        try:good=len(PdfReader(str(output),strict=False).pages)==1
        except Exception:good=False
    if good:reused+=1
    else:
        tmp=PDFS/(filename+".partial")
        pdf_draw(tmp,day,five,one,code,p5,p1)
        if len(PdfReader(str(tmp),strict=False).pages)!=1:
            raise RuntimeError("PDF verification failed: "+filename)
        os.replace(tmp,output)
        created+=1
    rows.append({
       "date_utc":d,"filename":filename,"study_code":code,
       "five_minute_color_pattern":p5,
       "one_hour_color_pattern":p1,
       "five_minute_candles":len(five),"one_hour_candles":len(one),
       "first_five_utc":str(five.index[0]),"last_five_utc":str(five.index[-1]),
       "first_one_utc":str(one.index[0]),"last_one_utc":str(one.index[-1]),
       "sha256":fingerprint
    })
    if i%50==0 or i==len(days):
        tmp=REPORTS/"MANIFEST.partial.csv"
        pd.DataFrame(rows).to_csv(tmp,index=False)
        os.replace(tmp,manifest)
        pd.DataFrame(skips,columns=["date_utc","reason"]).to_csv(REPORTS/"SKIPPED_UTC_DAYS.csv",index=False)
        announce("PDF",f"UTC days checked {i:,}/{len(days):,}; created {created:,}; reused {reused:,}; unavailable {len(skips):,}")
# Store final manifests even when final calendar days had missing candles.
pd.DataFrame(rows).to_csv(manifest,index=False)
pd.DataFrame(skips,columns=["date_utc","reason"]).to_csv(REPORTS/"SKIPPED_UTC_DAYS.csv",index=False)
summary=[
 "BTC UTC 23:00 5M & UTC 00:00 1H chart study",
 "Source: Bitstamp BTC/USD",
 f"Checked calendar UTC days: {len(days)}",
 f"PDFs represented by manifest: {len(rows)}",
 f"Coverage first day: {rows[0]['date_utc'] if rows else 'NONE'}",
 f"Coverage last day: {rows[-1]['date_utc'] if rows else 'NONE'}",
 f"Covered 2013: {sum(x['date_utc'].startswith('2013-') for x in rows)}",
 f"Covered 2026: {sum(x['date_utc'].startswith('2026-') for x in rows)}",
 f"PDFs newly created: {created}",
 f"PDFs reused: {reused}",
 f"Days skipped because source candles unavailable: {len(skips)}",
 "Upper 5M: previous day 21:00 to 03:55 UTC / 84 real 5m bars",
 "Lower 1H: 24 full UTC day candles plus 8 prior original hours = 32 plotted original 1H bars",
 "Filename: DD + 3 real 5M colors + 3 real 1H colors + 00 + _YYYYMMDD.pdf",
 "Colors g/r/d derived from exact Open/Close, doji d when equal",
 f"PDF directory: {PDFS}",
 "Original SRK_PDFS_180 directory untouched",
 "Blue arrows and outline identify the three reference bars on each panel; common X center for sample-like alignment; no trading signal",
 "No indicators or signals. No prediction or implied win rate."
]
(REPORTS/"FINAL_SUMMARY.txt").write_text("\n".join(summary)+"\n",encoding="utf-8")
announce("COMPLETE",f"{len(rows):,} historical PDF pages; {len(skips):,} skipped UTC days")
print("\n"+"\n".join(summary))
