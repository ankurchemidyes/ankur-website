# BTC 1M + native 15M | 23:00/00:00 | REAL Bitstamp data | ONE COLAB BOOTSTRAP.
# Preserved research rules: 420 genuine 1M chart bars; 32 genuine native 15M bars;
# 1M 22:58,22:59,23:00 previous UTC day; 15M 23:30,23:45 previous and 00:00 current;
# 1m23 + 3g/r + 3g/r + 00 + UTC day (DD), e.g. 1m23ggrggr0027.pdf.
# Group all dates of same exact code into one multipage PDF. No synthetic fill, no D codes.
# Original OHLC is not rotated. Focus boxes/arrows identify 3 actual timestamps each.
# Source: Bitstamp exchange API native 1M/15M; per-month compressed permanent checkpoints.
# FULL 2013–2026 MINUTE HISTORY IS MILLIONS OF ROWS; can take hours and multiple Colab sessions.

import sys,subprocess
subprocess.check_call([sys.executable,"-m","pip","install","-q","numpy","pandas","requests","reportlab","pypdf"])
import os,csv,time,calendar,json,gzip,shutil
from pathlib import Path
from datetime import datetime,timezone
from collections import defaultdict
import numpy as np
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
    ROOT=Path("/content/drive/MyDrive/BTC_1M23_15M00_ORIGINAL_2013_NOW")
except ImportError:
    ROOT=Path.cwd()/"BTC_1M23_15M00_ORIGINAL_2013_NOW"
DATA=ROOT/"CACHE"/"EXCHANGE_NATIVE_OHLC"
PDFS=ROOT/"PDFS_GROUPED_BY_CODE_DAY"
REPORTS=ROOT/"REPORTS"
for path in (DATA,PDFS,REPORTS):path.mkdir(parents=True,exist_ok=True)

START=pd.Timestamp("2013-01-01",tz="UTC")
END=(pd.Timestamp.now(tz="UTC").floor("D")-pd.Timedelta(days=1)).normalize()
END=min(END,pd.Timestamp("2026-12-31",tz="UTC"))
if END<START:raise RuntimeError("No completed UTC day")
# For first day of study, both panels use bars from the previous day.
FIRST_MONTH=pd.Timestamp("2012-12-01",tz="UTC")
LAST_REQUIRED=END+pd.Timedelta(hours=5)
API="https://www.bitstamp.net/api/v2/ohlc/btcusd/"
SESSION=requests.Session()
SESSION.mount("https://",HTTPAdapter(max_retries=Retry(
    total=5,backoff_factor=2,status_forcelist=[429,500,502,503,504],
    allowed_methods=["GET"])))
FIELDS=["time","open","high","low","close","volume"]

def notice(msg):
    print(msg,flush=True)
    (REPORTS/"LAST_PROGRESS.txt").write_text(msg+"\n",encoding="utf-8")

def csv_report(name,rows,columns):
    dest=REPORTS/name
    temp=dest.with_name(dest.name+".partial")
    with temp.open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader();writer.writerows(rows)
    os.replace(temp,dest)

def validate(frame,step):
    frame=frame.copy()
    if frame.empty:return frame
    frame["time"]=pd.to_datetime(frame["time"],utc=True,errors="coerce")
    for col in FIELDS[1:]:frame[col]=pd.to_numeric(frame[col],errors="coerce")
    frame=frame.dropna(subset=FIELDS)
    frame=frame[(frame[FIELDS[1:]].apply(np.isfinite)).all(axis=1)]
    frame=frame[(frame[["open","high","low","close"]]>0).all(axis=1)]
    frame=frame[(frame["volume"]>=0)]
    frame=frame[(frame["high"]>=frame[["open","low","close"]].max(axis=1))&
                (frame["low"]<=frame[["open","high","close"]].min(axis=1))]
    frame=frame[(frame["time"].astype("int64")//10**9)%step==0]
    return frame.sort_values("time").drop_duplicates("time",keep="last").reset_index(drop=True)

def get_months():
    return pd.date_range(FIRST_MONTH,LAST_REQUIRED.floor("D").replace(day=1),freq="MS",tz="UTC")

def month_source(step,month):
    month_str=month.strftime("%Y-%m")
    output=DATA/("1M" if step==60 else "15M")/(month_str+".csv.gz")
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.is_file() and output.stat().st_size>0:
        try:
            test=pd.read_csv(output,nrows=2)
            if set(FIELDS).issubset(set(test.columns)):
                return output
        except Exception:pass
    upper=month+pd.offsets.MonthBegin(1)
    # We ask exchange for < upper UTC timestamp; stop once oldest covered.
    cursor=min(int(upper.timestamp())-step,int(pd.Timestamp.now(tz="UTC").timestamp())-step)
    lower=int(month.timestamp())
    rows={}
    requests_made=0
    while cursor>=lower:
        result=SESSION.get(API,params={"step":step,"limit":1000,"end":cursor},timeout=100)
        result.raise_for_status()
        candles=result.json().get("data",{}).get("ohlc",[])
        if not candles:
            raise RuntimeError(f"No exchange data for {month_str}, step={step}, end={cursor}")
        earliest=min(int(item["timestamp"]) for item in candles)
        latest=max(int(item["timestamp"]) for item in candles)
        if earliest>cursor or latest>cursor+step:
            raise RuntimeError(f"Unexpected Bitstamp API pagination range {month_str}: {earliest}..{latest} vs {cursor}")
        for item in candles:
            ts=int(item["timestamp"])
            if lower<=ts<int(upper.timestamp()) and ts<=int(pd.Timestamp.now(tz="UTC").timestamp())-step:
                rows[ts]=[pd.Timestamp(ts,unit="s",tz="UTC")]+[
                    float(item[k]) for k in ("open","high","low","close","volume")]
        # Advance backward by one interval to ensure distinct prior timestamps.
        new_cursor=earliest-step
        if new_cursor>=cursor:raise RuntimeError("Bitstamp cursor did not decrease")
        cursor=new_cursor
        requests_made+=1
        if requests_made%25==0:
            notice(f"DOWNLOAD {step//60}m {month_str}: {requests_made} requests, {len(rows)} bars")
        time.sleep(0.06)
    df=validate(pd.DataFrame(rows.values(),columns=FIELDS),step)
    # A genuinely empty or incomplete exchange period is not filled with invented prices.
    if df.empty: raise RuntimeError(f"No real exchange bars for {month_str}, {step//60}m")
    temp=output.with_suffix(".csv.gz.partial")
    df.to_csv(temp,index=False,compression="gzip")
    os.replace(temp,output)
    notice(f"DOWNLOADED native {step//60}m {month_str}: {len(df)} real exchange candles")
    return output

def download_all(step):
    paths=[]
    for i,month in enumerate(get_months(),1):
        paths.append(month_source(step,month))
        if i%6==0:
            notice(f"CHECKPOINT native {step//60}m {i}/{len(get_months())} calendar months")
    return paths

notice("Downloading original Bitstamp 1M and native 15M OHLCV. Missing candles will NOT be interpolated.")
paths1=download_all(60)
paths15=download_all(900)
notice("Loading downloaded monthly source caches into history index...")
def read_all(paths,step):
    all_frames=[]
    for p in paths:
        x=pd.read_csv(p)
        if not x.empty:all_frames.append(x)
    if not all_frames:raise RuntimeError(f"No downloaded {step//60}m candles")
    out=validate(pd.concat(all_frames,ignore_index=True),step)
    out=out.set_index("time",drop=False)
    notice(f"Native {step//60}m original candles validated: {len(out):,}")
    return out

one=read_all(paths1,60)
quarter=read_all(paths15,900)

def real_window(df,start,count,frequency):
    expected=pd.date_range(start,periods=count,freq=frequency,tz="UTC")
    if not expected.isin(df.index).all():return None
    return df.loc[expected]
def letters(focus):
    result=[]
    for row in focus.itertuples():
        if row.close>row.open:result.append("g")
        elif row.close<row.open:result.append("r")
        else:return None
    return "".join(result)

groups=defaultdict(list)
manifest=[];skipped=[]
all_dates=pd.date_range(START,END,freq="D",tz="UTC")
for d in all_dates:
    previous=d-pd.Timedelta(days=1)
    upper_start=previous+pd.Timedelta(hours=20)
    lower_start=previous+pd.Timedelta(hours=21)
    upper=real_window(one,upper_start,420,"min")
    lower=real_window(quarter,lower_start,32,"15min")
    if upper is None or lower is None:
        skipped.append({"utc_date":str(d.date()),"reason":"Missing at least one genuine 1M or native 15M OHLC bar"})
        continue
    t1=pd.DatetimeIndex([previous+pd.Timedelta(hours=22,minutes=58),
        previous+pd.Timedelta(hours=22,minutes=59),previous+pd.Timedelta(hours=23)])
    t15=pd.DatetimeIndex([previous+pd.Timedelta(hours=23,minutes=30),
        previous+pd.Timedelta(hours=23,minutes=45),d])
    if not t1.isin(upper.index).all() or not t15.isin(lower.index).all():
        skipped.append({"utc_date":str(d.date()),"reason":"Missing exact focus timestamp"})
        continue
    upper_colors=letters(upper.loc[t1])
    lower_colors=letters(lower.loc[t15])
    if upper_colors is None or lower_colors is None:
        skipped.append({"utc_date":str(d.date()),"reason":"Exact equal Open/Close on highlighted candle; G/R not fabricated"})
        continue
    code=f"1m23{upper_colors}{lower_colors}00{d.day:02d}"
    assert len(code)==14 and set(upper_colors+lower_colors)<=set("gr")
    item=(d,upper_start,lower_start,upper_colors,lower_colors)
    groups[code].append(item)
    manifest.append({"utc_date":str(d.date()),"code":code,"upper_1m":upper_colors,"lower_15m":lower_colors})

csv_report("SEARCH_INDEX_ALL_PAGES.csv",manifest,["utc_date","code","upper_1m","lower_15m"])
csv_report("SKIPPED_UTC_DAYS.csv",skipped,["utc_date","reason"])
notice(f"SCAN: {len(all_dates)} days | {len(manifest)} original matched pages | {len(groups)} PDF names | {len(skipped)} skipped")

# Two chart panels, prices and timestamps never rotated; original chart style.
WIDTH,HEIGHT=1320,840
GREEN=HexColor("#089981");RED=HexColor("#d75159")
BLUE=HexColor("#3477e3");INK=HexColor("#26313c");GRID=HexColor("#e1e7ef")
def draw_panel(pdf,frame,focus_times,ymin,ymax,label,chart_left=92,chart_right=1250):
    n=len(frame)
    low=float(frame.low.min());high=float(frame.high.max())
    gap=max((high-low)*.09,high*.0001); low-=gap;high+=gap
    scale=lambda val:ymin+(val-low)/(high-low)*(ymax-ymin)
    delta=(chart_right-chart_left)/n
    def xcenter(i):return chart_left+(i+.5)*delta
    pdf.setFont("Helvetica-Bold",12);pdf.setFillColor(INK)
    pdf.drawString(chart_left,ymax+18,label)
    for i in range(5):
        y=ymin+(ymax-ymin)*i/4
        pdf.setStrokeColor(GRID);pdf.setLineWidth(.7)
        pdf.line(chart_left,y,chart_right,y)
        pdf.setFont("Helvetica",8);pdf.setFillColor(INK)
        pdf.drawRightString(chart_left-8,y-3,f"{(low+(high-low)*i/4):,.2f}")
    for i,(stamp,row) in enumerate(frame.iterrows()):
        o=float(row.open);c=float(row.close);h=float(row.high);l=float(row.low)
        color=GREEN if c>o else RED if c<o else INK
        x=xcenter(i)
        pdf.setStrokeColor(color);pdf.setLineWidth(max(.35,min(1.2,delta*.23)))
        pdf.line(x,scale(l),x,scale(h))
        width=max(.5,delta*.62)
        body=max(1.0,abs(scale(c)-scale(o)))
        pdf.setFillColor(color)
        pdf.rect(x-width/2,min(scale(o),scale(c)),width,body,stroke=0,fill=1)
    positions=[int(frame.index.get_loc(t)) for t in focus_times]
    assert positions==list(range(positions[0],positions[0]+3))
    left=xcenter(positions[0])-delta*.5
    right=xcenter(positions[-1])+delta*.5
    pdf.setStrokeColor(BLUE);pdf.setLineWidth(2.4)
    pdf.roundRect(left,ymin+4,right-left,ymax-ymin-8,4,fill=0,stroke=1)
    for i in positions:
        x=xcenter(i)
        pdf.setStrokeColor(BLUE);pdf.setLineWidth(1.6)
        pdf.line(x,ymax+7,x,ymax+19)
        path=pdf.beginPath();path.moveTo(x-3,ymax+12);path.lineTo(x,ymax+7)
        path.lineTo(x+3,ymax+12);pdf.drawPath(path,stroke=1)
    every=60 if n==420 else 4
    for i in range(0,n,every):
        pdf.setFont("Helvetica",8);pdf.setFillColor(INK)
        pdf.drawCentredString(xcenter(i),ymin-16,frame.index[i].strftime("%d %H:%M"))

def draw_page(pdf,item,code):
    d,upper_start,lower_start,upper_letters,lower_letters=item
    upper=real_window(one,upper_start,420,"min")
    lower=real_window(quarter,lower_start,32,"15min")
    if upper is None or lower is None:raise RuntimeError(f"Original data missing while drawing {d}")
    previous=d-pd.Timedelta(days=1)
    top_focus=pd.DatetimeIndex([previous+pd.Timedelta(hours=22,minutes=58),
        previous+pd.Timedelta(hours=22,minutes=59),previous+pd.Timedelta(hours=23)])
    low_focus=pd.DatetimeIndex([previous+pd.Timedelta(hours=23,minutes=30),
        previous+pd.Timedelta(hours=23,minutes=45),d])
    pdf.setFillColor(INK);pdf.setFont("Helvetica-Bold",16)
    pdf.drawString(92,800,"BTC/USD | Bitstamp ORIGINAL 1M + ORIGINAL 15M")
    pdf.setFont("Helvetica",11)
    pdf.drawString(92,779,f"UTC DATE: {d:%Y-%m-%d} | real OHLC | 1M {upper_letters.upper()} | 15M {lower_letters.upper()}")
    pdf.setFont("Helvetica-Bold",16);pdf.drawRightString(1250,801,code)
    draw_panel(pdf,upper,top_focus,448,735,"1M | 7 HOURS | prev UTC 20:00 - current UTC 02:59")
    draw_panel(pdf,lower,low_focus,95,371,"15M | 32 ORIGINAL CANDLES | prev UTC 21:00 - current UTC 04:45")
    pdf.setFont("Helvetica",9);pdf.setFillColor(INK)
    pdf.drawString(92,35,"Blue boxes and arrows mark original candle timestamps; no artificial data, no trading signal.")
    pdf.showPage()

counts=[];total=sum(len(x) for x in groups.values())
for idx,(code,items) in enumerate(sorted(groups.items()),1):
    dest=PDFS/(code+".pdf")
    expected=len(items)
    already=False
    if dest.exists():
        try:already=len(PdfReader(str(dest),strict=False).pages)==expected
        except Exception:already=False
    if not already:
        temp=PDFS/(code+".pdf.partial")
        pdf=canvas.Canvas(str(temp),pagesize=(WIDTH,HEIGHT),pageCompression=1)
        for item in sorted(items,key=lambda z:z[0]):
            draw_page(pdf,item,code)
        pdf.save()
        check=PdfReader(str(temp),strict=False)
        if len(check.pages)!=expected:
            temp.unlink(missing_ok=True)
            raise RuntimeError(f"PDF pages mismatch for {code}: expected {expected}")
        os.replace(temp,dest)
    counts.append({"code":code,"page_count":expected,"pdf_path":str(dest)})
    if idx%30==0 or idx==len(groups):
        csv_report("PDF_GROUP_SUMMARY.csv",counts,["code","page_count","pdf_path"])
        notice(f"PDF: {idx}/{len(groups)} names verified; {sum(x['page_count'] for x in counts)} pages")
csv_report("PDF_GROUP_SUMMARY.csv",counts,["code","page_count","pdf_path"])
final=(f"BTC 1M23 + 15M00 ORIGINAL HISTORICAL PDF\n"
       f"START: 2013-01-01 UTC\nLAST: {END.date()}\n"
       f"Source: Bitstamp BTC/USD native 1M / native 15M exchange OHLCV\n"
       f"Valid historical chart pages: {len(manifest)}\n"
       f"Skipped original UTC days: {len(skipped)}\n"
       f"Searchable PDF files: {len(counts)}\n"
       f"PDF pages: {sum(x['page_count'] for x in counts)}\n"
       f"Upper 1M: prev UTC 20:00 to current UTC 02:59, 420 bars\n"
       f"Upper focus: prev UTC 22:58,22:59,23:00\n"
       f"Lower native 15M: prev UTC 21:00 to current UTC 04:45, 32 bars\n"
       f"Lower focus: prev UTC 23:30,23:45; current UTC 00:00\n"
       f"Filename: 1m23 + upper3(g/r) + lower3(g/r) + 00 + DD\n"
       f"OUT: {PDFS}\nSTATUS: COMPLETE\n")
(REPORTS/"FINAL_SUMMARY.txt").write_text(final,encoding="utf-8")
print(final)
