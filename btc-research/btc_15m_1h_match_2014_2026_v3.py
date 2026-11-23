# Bitcoin 15-minute / 1-hour historical SuperTrend research
# Google Colab: one cell; no pre-existing ZIP or PDF required.
# PDF name: 15RRG084523.pdf = timeframe + 3 candles + HHMM UTC + day
# ONLY ONE PDF SET; month/year never included in the grouping filename.
import sys, subprocess
subprocess.check_call([sys.executable,"-m","pip","install","-q",
                       "numpy","pandas","numba","requests","reportlab","pypdf"])
import io, csv, zipfile, calendar, time, hashlib, shutil, bisect
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from collections import defaultdict
import numpy as np
import pandas as pd
from numba import njit
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from google.colab import drive
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.colors import HexColor
from pypdf import PdfReader

START, END = date(2014,1,1), date(2026,11,21)
BEFORE, AFTER = 10, 16
drive.mount("/content/drive")
ROOT=Path("/content/drive/MyDrive/BTC_15MIN_1H_2014_2026_V3_RESEARCH")
DATA,OUTPUT,REPORT,TEMP=(ROOT/"_CACHE",ROOT/"ONE_15MIN_PDF_SET",
                         ROOT/"REPORTS",Path("/content/btc_pdf_local"))
for p in [DATA,OUTPUT,REPORT,TEMP]: p.mkdir(parents=True,exist_ok=True)
http=requests.Session()
http.mount("https://",HTTPAdapter(max_retries=Retry(
    total=6,backoff_factor=1.5,status_forcelist=[429,500,502,503,504],
    allowed_methods=["GET"])))
COLUMNS=["time","open","high","low","close","source"]
def fetch(url,params=None,optional=False):
    r=http.get(url,params=params,timeout=90)
    if optional and r.status_code==404: return None
    r.raise_for_status()
    return r
def read_zip(data):
    out=[]
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if z.testzip() is not None: raise RuntimeError("Archive corrupted")
        names=[n for n in z.namelist() if n.lower().endswith(".csv")]
        if len(names)!=1: raise RuntimeError("Unexpected ZIP format")
        with z.open(names[0]) as f:
            for row in csv.reader(io.TextIOWrapper(f,encoding="utf-8")):
                if len(row)<5: continue
                try: ts=int(row[0])
                except ValueError: continue
                unit="us" if ts>=10**14 else "ms"
                out.append([pd.to_datetime(ts,unit=unit,utc=True),
                    *map(float,row[1:5]),"Binance BTC/USDT"])
    return out
def binance():
    parts=[]
    month=date(2017,8,1)
    base="https://data.binance.vision/data/spot/"
    while month<=END:
        y,m=month.year,month.month
        last=date(y,m,calendar.monthrange(y,m)[1])
        target=DATA/f"BN_15M_{y}_{m:02d}.csv.gz"
        if target.exists():
            p=pd.read_csv(target)
            p["time"]=pd.to_datetime(p["time"],utc=True)
        else:
            r=None
            if last<=END:
                url=base+f"monthly/klines/BTCUSDT/15m/BTCUSDT-15m-{y}-{m:02d}.zip"
                r=fetch(url,optional=True)
            if r is not None:
                rows=read_zip(r.content)
            else:
                rows=[]
                d=max(month,date(2017,8,17))
                while d<=min(last,END):
                    url=base+f"daily/klines/BTCUSDT/15m/BTCUSDT-15m-{d}.zip"
                    r=fetch(url,optional=True)
                    if r is None: raise RuntimeError(f"Missing Binance day {d}")
                    rows.extend(read_zip(r.content))
                    d+=timedelta(days=1)
            if not rows: raise RuntimeError(f"Missing Binance month {month}")
            p=pd.DataFrame(rows,columns=COLUMNS)
            p.to_csv(target,index=False,compression="gzip")
        parts.append(p)
        print("Binance:",y,m,len(p))
        month=date(y+1,1,1) if m==12 else date(y,m+1,1)
    return pd.concat(parts,ignore_index=True)
def bitstamp():
    final=DATA/"BS_15M.csv.gz"
    partial=DATA/"BS_15M_PARTIAL.csv.gz"
    if final.exists():
        p=pd.read_csv(final)
        p["time"]=pd.to_datetime(p["time"],utc=True)
        return p
    first=int(datetime(2013,12,1,tzinfo=timezone.utc).timestamp())
    cursor=int(datetime(2017,8,18,tzinfo=timezone.utc).timestamp())
    rows=[]
    if partial.exists():
        saved=pd.read_csv(partial)
        saved["time"]=pd.to_datetime(saved["time"],utc=True)
        if len(saved):
            rows=saved[COLUMNS].values.tolist()
            cursor=int(saved.time.min().timestamp())-1
            print("Resuming Bitstamp from",saved.time.min())
    call=0
    while cursor>=first:
        data=fetch("https://www.bitstamp.net/api/v2/ohlc/btcusd/",
                   {"step":900,"limit":1000,"end":cursor}).json()
        candles=data.get("data",{}).get("ohlc",[])
        if not candles:
            raise RuntimeError("Bitstamp historical OHLC unavailable; check service/data source")
        stamps=[]
        for a in candles:
            ts=int(a["timestamp"]);stamps.append(ts)
            if ts>=first:
                rows.append([pd.to_datetime(ts,unit="s",utc=True),
                    *[float(a[k]) for k in ("open","high","low","close")],
                    "Bitstamp BTC/USD"])
        oldest=min(stamps)
        if oldest>=cursor:
            raise RuntimeError("Bitstamp OHLC pagination stalled")
        cursor=oldest-1
        call+=1
        if call%25==0:
            pd.DataFrame(rows,columns=COLUMNS).drop_duplicates("time").to_csv(
                partial,index=False,compression="gzip")
            print("Bitstamp checkpoint:",pd.to_datetime(oldest,unit="s",utc=True))
        time.sleep(.15)
    p=pd.DataFrame(rows,columns=COLUMNS).drop_duplicates("time").sort_values("time")
    p.to_csv(final,index=False,compression="gzip")
    partial.unlink(missing_ok=True)
    return p

raw=DATA/"COMPLETE_15M_OHLC.csv.gz"
if raw.exists():
    df=pd.read_csv(raw);df["time"]=pd.to_datetime(df["time"],utc=True)
else:
    bn=binance();bs=bitstamp()
    bn["time"]=pd.to_datetime(bn["time"],utc=True)
    bs["time"]=pd.to_datetime(bs["time"],utc=True)
    df=pd.concat([bs[bs.time<bn.time.min()],bn],ignore_index=True)
    df=df.sort_values("time").drop_duplicates("time").reset_index(drop=True)
    df=df[df.time<pd.Timestamp(END+timedelta(days=1),tz="UTC")].copy()
    df.to_csv(raw,index=False,compression="gzip")
df=df.sort_values("time").reset_index(drop=True)
if df.empty or df.time.min()>pd.Timestamp("2014-01-01",tz="UTC"):
    raise RuntimeError("2014 Bitstamp history is missing; no simulated candles will be used.")
for k in ("open","high","low","close"): df[k]=pd.to_numeric(df[k])
good=(df[["open","high","low","close"]]>0).all(axis=1)&(df.high>=df[["open","close","low"]].max(axis=1))&(df.low<=df[["open","close","high"]].min(axis=1))
if not good.all(): raise RuntimeError("Invalid OHLC rows")
df["segment"]=(df.time.diff().ne(pd.Timedelta(minutes=15))|
               df.source.ne(df.source.shift())).cumsum()
gaps=[]
for i in range(1,len(df)):
    if df.segment.iat[i]!=df.segment.iat[i-1]:
        gaps.append({"previous_utc":df.time.iat[i-1],"next_utc":df.time.iat[i],
                     "previous_source":df.source.iat[i-1],"next_source":df.source.iat[i]})
pd.DataFrame(gaps).to_csv(REPORT/"DATA_GAPS.csv",index=False)
# Data-source/annual coverage audit: never silently invent missing bars.
coverage=df.assign(year=df.time.dt.year).groupby(["year","source"],as_index=False).agg(
    candles=("time","size"),first_UTC=("time","min"),last_UTC=("time","max"))
coverage.to_csv(REPORT/"YEARLY_SOURCE_COVERAGE.csv",index=False)
offgrid=((df.time.dt.minute%15)!=0)|(df.time.dt.second!=0)
df.loc[offgrid,COLUMNS].to_csv(REPORT/"OFF_GRID_CANDLES.csv",index=False)
if offgrid.any():
    print("Warning: excluding",int(offgrid.sum()),"non-quarter-hour candles; logged in REPORTS")
    df=df.loc[~offgrid].reset_index(drop=True)
    df["segment"]=(df.time.diff().ne(pd.Timedelta(minutes=15))|
                   df.source.ne(df.source.shift())).cumsum()
print("15M historical candles",len(df))

# Build exchange-aligned, complete 1-hour candles from the SAME 15M candles.
hourparts=[]
for seg,part in df.groupby("segment",sort=False):
    x=part.set_index("time").resample("1h",label="left",closed="left").agg(
        {"open":"first","high":"max","low":"min","close":"last",
         "source":"first","segment":"first"})
    counts=part.set_index("time").close.resample("1h").count()
    x=x[counts==4].reset_index()
    if len(x): hourparts.append(x)
hour=pd.concat(hourparts,ignore_index=True).sort_values("time").reset_index(drop=True)
hour["segment"]=(hour.time.diff().ne(pd.Timedelta(hours=1))|
                 hour.source.ne(hour.source.shift())).cumsum()
print("Complete reconstructed 1H candles",len(hour))

# Accelerated exact-history calculations for ~12 years of 15-minute bars.
@njit
def rsi(values,length):
    a=np.asarray(values,dtype=np.float64)
    n=len(a)
    out=np.full(n,np.nan)
    if n<=length:
        return out
    ag=0.0;al=0.0
    for j in range(1,length+1):
        change=a[j]-a[j-1]
        ag+=max(change,0.0)
        al+=max(-change,0.0)
    ag/=length;al/=length
    for i in range(length,n):
        if i>length:
            change=a[i]-a[i-1]
            ag=(ag*(length-1)+max(change,0.0))/length
            al=(al*(length-1)+max(-change,0.0))/length
        if ag==0.0 and al==0.0:
            out[i]=50.0
        elif al==0.0:
            out[i]=100.0
        else:
            out[i]=100.0-100.0/(1.0+ag/al)
    return out

@njit
def crsi(close):
    c=np.asarray(close,dtype=np.float64)
    n=len(c)
    streak=np.zeros(n,dtype=np.float64)
    roc=np.full(n,np.nan)
    rank=np.full(n,np.nan)
    for i in range(1,n):
        if c[i]>c[i-1]:
            streak[i]=max(0.0,streak[i-1])+1.0
        elif c[i]<c[i-1]:
            streak[i]=min(0.0,streak[i-1])-1.0
        roc[i]=(c[i]/c[i-1]-1.0)*100.0
    for i in range(100,n):
        count=0
        for j in range(i-99,i+1):
            if roc[j]<=roc[i]:
                count+=1
        rank[i]=float(count)
    return (rsi(c,3)+rsi(streak,2)+rank)/3.0

@njit
def supertrend(h,l,c):
    h=np.asarray(h,dtype=np.float64)
    l=np.asarray(l,dtype=np.float64)
    c=np.asarray(c,dtype=np.float64)
    n=len(c)
    tr=np.empty(n,dtype=np.float64)
    tr[0]=h[0]-l[0]
    for i in range(1,n):
        tr[i]=max(h[i]-l[i],abs(h[i]-c[i-1]),abs(l[i]-c[i-1]))
    upper=np.empty(n,dtype=np.float64)
    lower=np.empty(n,dtype=np.float64)
    direction=np.empty(n,dtype=np.int8)
    line=np.empty(n,dtype=np.float64)
    mid=(h[0]+l[0])/2.0
    upper[0]=mid+tr[0]
    lower[0]=mid-tr[0]
    direction[0]=-1
    line[0]=upper[0]
    for i in range(1,n):
        mid=(h[i]+l[i])/2.0
        bu=mid+tr[i]
        bl=mid-tr[i]
        lower[i]=bl if bl>lower[i-1] or c[i-1]<lower[i-1] else lower[i-1]
        upper[i]=bu if bu<upper[i-1] or c[i-1]>upper[i-1] else upper[i-1]
        if direction[i-1]==-1:
            direction[i]=1 if c[i]>upper[i] else -1
        else:
            direction[i]=-1 if c[i]<lower[i] else 1
        line[i]=lower[i] if direction[i]==1 else upper[i]
    return direction,line

def indicators(frame):
    frame["trend"]=0;frame["st"]=np.nan;frame["crsi"]=np.nan
    bounds={}
    for seg,part in frame.groupby("segment",sort=False):
        idx=part.index.to_numpy();bounds[seg]=(int(idx[0]),int(idx[-1]))
        tr,st=supertrend(part.high,part.low,part.close)
        frame.loc[idx,"trend"]=tr;frame.loc[idx,"st"]=st
        frame.loc[idx,"crsi"]=crsi(part.close)
    return bounds
b15=indicators(df);b1h=indicators(hour)
def extract_signals(frame,bounds):
    signals=[]
    op=frame.open.to_numpy();cl=frame.close.to_numpy()
    trend=frame.trend.to_numpy();segs=frame.segment.to_numpy()
    for i in range(1,len(frame)):
        t=frame.time.iat[i]
        if not START<=t.date()<=END:continue
        if segs[i]!=segs[i-1] or trend[i]==trend[i-1]:continue
        code=("".join("G" if cl[j]>=op[j] else "R" for j in range(i-2,i+1))
              if i>=2 and segs[i-2]==segs[i] else "REVIEW")
        a,b=bounds[segs[i]]
        signals.append({"i":i,"time":t,"code":code,
            "direction":int(trend[i]),"source":frame.source.iat[i],
            "before":min(i-a,BEFORE),"after":min(b-i,AFTER)})
    return signals
s15=extract_signals(df,b15)
s1=extract_signals(hour,b1h)
print("15M signals:",len(s15),"1H signals:",len(s1))
if not s15:raise RuntimeError("No 15M signals were detected")

# For 1H signal H, match same-direction 15M signals at [H-60min, H+45min].
# Example: H=08:00 -> 07:00,07:15,...,08:45.
lookups=defaultdict(list)
for s in s1:lookups[(s["source"],s["direction"])].append((s["time"],s))
for key in lookups:lookups[key].sort(key=lambda item:item[0])
lookup_times={key:[t for t,_ in seq] for key,seq in lookups.items()}
groups=defaultdict(list);records=[]
for s in s15:
    t=s["time"]
    key=(s["source"],s["direction"])
    seq=lookups.get(key,[])
    times=lookup_times.get(key,[])
    lo=bisect.bisect_left(times,t-pd.Timedelta(minutes=45))
    hi=bisect.bisect_right(times,t+pd.Timedelta(hours=1))
    s["matches"]=[x for _,x in seq[lo:hi]]
    name=f"15{s['code']}{t:%H%M}{t:%d}.pdf"
    s["filename"]=name
    if s["matches"]:
        groups[name].append(s)
    hour_strings=[]
    for h in s["matches"]:
        htime=h["time"]
        hour_strings.append(
            f"1{h['code'].lower()}{htime:%H}{htime:%d} "
            f"({htime:%Y-%m-%d %H:%M} UTC)"
        )
    records.append({
        "15M_UTC":t,"15M_PDF":name,"15M_candle_code":s["code"],
        "15M_signal":"GREEN" if s["direction"]==1 else "RED",
        "match_status":"MATCH" if s["matches"] else "NO MATCH",
        "matched_1H_signals":"; ".join(hour_strings),
        "15M_source":s["source"],"15M_CRSI":float(df.crsi.iat[s["i"]])
    })
pd.DataFrame(records).to_csv(REPORT/"ALL_SIGNALS_AND_1H_MATCHES.csv",index=False)
# Every exact historical pair, including full dates and UTC timing.
pair_rows=[]
for sample in s15:
    for counterpart in sample.get("matches",[]):
        pair_rows.append({
            "15M_UTC":sample["time"],
            "1H_UTC":counterpart["time"],
            "15M_code":sample["code"],
            "1H_code":counterpart["code"],
            "15M_CRSI":float(df.crsi.iat[sample["i"]]),
            "1H_CRSI":float(hour.crsi.iat[counterpart["i"]]),
            "direction":"GREEN" if sample["direction"]==1 else "RED",
            "15M_PDF":sample["filename"],
            "market":sample["source"],
            "offset_minutes":int((sample["time"]-counterpart["time"]).total_seconds()/60)
        })
pd.DataFrame(pair_rows).to_csv(REPORT/"EXACT_MATCHED_PAIRS.csv",index=False)

print("One 15M matched-signal PDF group count:",len(groups))
print("No-match cases are recorded in CSV, not generated as PDFs.")
print("Matched 15M signal pages:",sum(bool(s["matches"]) for s in s15))

# TradingView-like research layout: two full candlestick charts,
# red/green SuperTrend flip arrows, and separate CRSI panels.
# All plotted price points come from retrieved historical candles.
from reportlab.lib.pagesizes import A3
GREEN=HexColor("#078E63")
RED=HexColor("#D44D58")
BLUE=HexColor("#258FBE")
GRID=HexColor("#D6DEE4")
GRAY=HexColor("#697480")
BLACK=HexColor("#222831")
W,H=landscape(A3)

def signal_arrow(pdf,x,y,direction,size=6):
    pdf.setFillColor(GREEN if direction==1 else RED)
    path=pdf.beginPath()
    if direction==1:
        path.moveTo(x,y+size)
        path.lineTo(x-size,y-size/2)
        path.lineTo(x+size,y-size/2)
    else:
        path.moveTo(x,y-size)
        path.lineTo(x-size,y+size/2)
        path.lineTo(x+size,y+size/2)
    path.close()
    pdf.drawPath(path,fill=1,stroke=0)

def panel(pdf,frame,bounds,center,top,bottom,crbottom,crtop,label):
    seg=int(frame.segment.iat[center])
    a,b=bounds[seg]
    start=max(a,center-BEFORE)
    stop=min(b,center+AFTER)
    p=frame.iloc[start:stop+1]
    o=p.open.to_numpy()
    hi=p.high.to_numpy()
    lo=p.low.to_numpy()
    cl=p.close.to_numpy()
    st=p.st.to_numpy()
    tr=p.trend.to_numpy()
    cr=p.crsi.to_numpy()
    n=len(p)
    pos=center-start
    x0,x1=78,1065
    dx=(x1-x0)/n
    X=lambda k:x0+(k+.5)*dx
    minp=min(lo.min(),st.min())
    maxp=max(hi.max(),st.max())
    pad=max((maxp-minp)*.15,maxp*.001)
    minp-=pad
    maxp+=pad
    Y=lambda v:bottom+(v-minp)/(maxp-minp)*(top-bottom)
    R=lambda v:crbottom+v/100*(crtop-crbottom)

    pdf.setFillColor(BLACK)
    pdf.setFont("Helvetica-Bold",11)
    pdf.drawString(72,top+19,label)

    for j in range(5):
        price=minp+(maxp-minp)*j/4
        pdf.setLineWidth(.5)
        pdf.setStrokeColor(GRID)
        pdf.line(x0,Y(price),x1,Y(price))
        pdf.setFillColor(GRAY)
        pdf.setFont("Helvetica",8)
        pdf.drawString(1074,Y(price)-2,f"{price:,.2f}")

    for k in range(n):
        color=GREEN if cl[k]>=o[k] else RED
        pdf.setStrokeColor(color)
        pdf.setFillColor(color)
        pdf.setLineWidth(1)
        pdf.line(X(k),Y(lo[k]),X(k),Y(hi[k]))
        candle_width=min(15,dx*.52)
        pdf.rect(X(k)-candle_width/2,
                 min(Y(o[k]),Y(cl[k])),candle_width,
                 max(1.7,abs(Y(cl[k])-Y(o[k]))),
                 stroke=0,fill=1)

    pdf.setLineWidth(3.0)
    for k in range(1,n):
        if tr[k]==tr[k-1]:
            pdf.setStrokeColor(GREEN if tr[k]==1 else RED)
            pdf.line(X(k-1),Y(st[k-1]),X(k),Y(st[k]))

    # Visible actual SuperTrend flips, not synthetic arrows.
    for k in range(1,n):
        if tr[k]!=tr[k-1]:
            direction=int(tr[k])
            if direction==1:
                arrow_y=max(bottom+10,Y(lo[k])-13)
            else:
                arrow_y=min(top-10,Y(hi[k])+13)
            signal_arrow(pdf,X(k),arrow_y,direction)

    # Mark precisely the candle whose historical signal is being compared.
    pdf.setStrokeColor(RED)
    pdf.setLineWidth(1.2)
    pdf.setDash(3,3)
    pdf.line(X(pos),crbottom,X(pos),top)
    pdf.setDash()

    ticks=sorted(set([0,pos,n-1]+list(range(0,n,max(1,n//7)))))
    pdf.setFont("Helvetica",8)
    pdf.setFillColor(GRAY)
    for k in ticks:
        pdf.drawCentredString(
            X(k),bottom-15,
            p.time.iat[k].strftime("%d/%m %H:%M")
        )

    pdf.setFont("Helvetica",9)
    pdf.setFillColor(GRAY)
    pdf.drawString(x0,crtop+7,"CRSI (3,2,100)")

    for level in (30,50,70):
        pdf.setStrokeColor(GRID)
        pdf.setLineWidth(.7)
        pdf.setDash(4,3)
        pdf.line(x0,R(level),x1,R(level))
        pdf.setDash()
        pdf.setFont("Helvetica",8)
        pdf.setFillColor(GRAY)
        pdf.drawString(1075,R(level)-3,str(level))

    pdf.setStrokeColor(BLUE)
    pdf.setLineWidth(2)
    for k in range(1,n):
        if np.isfinite(cr[k]) and np.isfinite(cr[k-1]):
            pdf.line(X(k-1),R(cr[k-1]),X(k),R(cr[k]))

    if np.isfinite(cr[pos]):
        pdf.setFillColor(BLUE)
        pdf.circle(X(pos),R(cr[pos]),4,fill=1,stroke=0)

def render(pdf,s):
    # ONE PAGE = one real 15-minute signal paired with one
    # real same-direction 1-hour SuperTrend flip.
    assert s["matches"]
    h=s["matches"][0]
    t=s["time"]
    ht=h["time"]
    code15=f"15{s['code'].lower()}{t:%H%M}{t:%d}"
    code1=f"1{h['code'].lower()}{ht:%H}{ht:%d}"
    direction="GREEN" if s["direction"]==1 else "RED"
    delta=int((t-ht).total_seconds()/60)

    pdf.setFillColor(BLACK)
    pdf.setFont("Helvetica-Bold",22)
    pdf.drawString(72,790,f"{code15}/{code1}")

    pdf.setFont("Helvetica",11)
    pdf.drawString(
        72,764,
        f"15M {t:%Y-%m-%d %H:%M} UTC   |   "
        f"1H {ht:%Y-%m-%d %H:%M} UTC   |   "
        f"{direction} SuperTrend flip   |   15M-1H offset {delta:+d} min"
    )
    pdf.setFont("Helvetica",9)
    pdf.drawString(
        72,747,
        f"Market: {s['source']}   |   "
        f"15M CRSI {df.crsi.iat[s['i']]:.2f}   |   "
        f"1H CRSI {hour.crsi.iat[h['i']]:.2f}"
    )

    panel(
        pdf,df,b15,s["i"],
        703,556,488,517,
        "15-MINUTE  |  ORIGINAL HISTORICAL OHLC  |  SuperTrend (1,1)"
    )
    panel(
        pdf,hour,b1h,h["i"],
        418,271,203,232,
        "1-HOUR  |  AGGREGATED FROM THE SAME 15M SOURCE  |  SuperTrend (1,1)"
    )

    pdf.setFillColor(BLACK)
    pdf.setFont("Helvetica-Bold",11)
    pdf.drawString(
        72,153,
        f"MATCH: same SuperTrend direction ({direction}); "
        f"15M candle at {t:%H:%M} UTC, 1H candle at {ht:%H:%M} UTC"
    )

    if len(s["matches"])>1:
        more=", ".join(
            v["time"].strftime("%Y-%m-%d %H:%M")
            for v in s["matches"][1:]
        )
        pdf.setFont("Helvetica",9)
        pdf.drawString(72,135,"Other same-direction 1H matches: "+more[:160])

    pdf.setFillColor(GRAY)
    pdf.setFont("Helvetica",9)
    pdf.drawString(
        72,103,
        "Research-only historical match: 1H 08:00 aligns with 15M 07:00-08:45 UTC."
    )
    pdf.drawString(
        72,87,
        "Times denote candle OPEN; 1H signal is confirmed after the 1H candle CLOSE."
    )
    pdf.drawString(
        72,71,
        "All original dates retained on each page; grouping ignores month and year."
    )
    pdf.drawString(
        72,55,
        "Bitstamp BTC/USD and Binance BTC/USDT are DIFFERENT markets; "
        "check exact TradingView ticker and indicator settings."
    )
    pdf.showPage()
def pages(path):
    try:return len(PdfReader(str(path),strict=False).pages)
    except Exception:return -1
def sha(path):
    dig=hashlib.sha256()
    with open(path,"rb") as f:
        for part in iter(lambda:f.read(1024*1024),b""):dig.update(part)
    return dig.hexdigest()
summary=[]
for count,(name,items) in enumerate(sorted(groups.items()),1):
    target=OUTPUT/name
    if pages(target)!=len(items):
        local=TEMP/name
        pdf=canvas.Canvas(str(local),pagesize=landscape(A3),pageCompression=1)
        for s in items:render(pdf,s)
        pdf.save()
        if pages(local)!=len(items):
            raise RuntimeError("Local PDF failed: "+name)
        shutil.copy2(local,target)
        if sha(local)!=sha(target):
            raise RuntimeError("Drive PDF checksum failed: "+name)
        local.unlink(missing_ok=True)
    summary.append({"filename":name,"pages":len(items),
                    "matched_pages":sum(bool(s["matches"]) for s in items)})
    if count%50==0 or count==len(groups):
        print(f"PDFs complete: {count}/{len(groups)}")
pd.DataFrame(summary).to_csv(REPORT/"PDF_GROUP_COUNTS.csv",index=False)
print("DONE: one matched-signal PDF set only.",OUTPUT)
print("Total 15M detected signals:",len(s15))
print("Matched 15M chart pages:",sum(len(items) for items in groups.values()))
print("Total PDFs:",len(groups))
print("Historical comparison ONLY: TradingView parity has not been independently verified.")
