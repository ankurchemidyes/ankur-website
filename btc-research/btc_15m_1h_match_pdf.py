# Bitcoin 15-minute / 1-hour historical SuperTrend research
# Google Colab: one cell; no pre-existing ZIP or PDF required.
# PDF name: 15RRG084523.pdf = timeframe + 3 candles + HHMM UTC + day
# ONLY ONE PDF SET; month/year never included in the grouping filename.
import sys, subprocess
subprocess.check_call([sys.executable,"-m","pip","install","-q",
                       "numpy","pandas","requests","reportlab","pypdf"])
import io, csv, zipfile, calendar, time, hashlib, shutil, bisect
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from collections import defaultdict
import numpy as np
import pandas as pd
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
ROOT=Path("/content/drive/MyDrive/BTC_15MIN_1H_MATCH_PDF_V1")
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
    target=DATA/"BS_15M.csv.gz"
    if target.exists():
        p=pd.read_csv(target);p["time"]=pd.to_datetime(p["time"],utc=True)
        return p
    first=int(datetime(2013,12,1,tzinfo=timezone.utc).timestamp())
    cursor=int(datetime(2017,8,18,tzinfo=timezone.utc).timestamp())
    rows=[]
    while cursor>=first:
        data=fetch("https://www.bitstamp.net/api/v2/ohlc/btcusd/",
                   {"step":900,"limit":1000,"end":cursor}).json()
        candles=data.get("data",{}).get("ohlc",[])
        if not candles: raise RuntimeError("Bitstamp OHLC not returned")
        stamps=[]
        for a in candles:
            ts=int(a["timestamp"]);stamps.append(ts)
            if ts>=first:
                rows.append([pd.to_datetime(ts,unit="s",utc=True),
                    *[float(a[k]) for k in ("open","high","low","close")],
                    "Bitstamp BTC/USD"])
        oldest=min(stamps)
        if oldest>=cursor: raise RuntimeError("Bitstamp pagination stalled")
        cursor=oldest-1
        print("Bitstamp reached",pd.to_datetime(oldest,unit="s",utc=True).date())
        time.sleep(.15)
    p=pd.DataFrame(rows,columns=COLUMNS).drop_duplicates("time").sort_values("time")
    p.to_csv(target,index=False,compression="gzip")
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

def rsi(values,length):
    a=np.asarray(values,float);out=np.full(len(a),np.nan)
    if len(a)<=length:return out
    diff=np.diff(a);g=np.maximum(diff,0);l=np.maximum(-diff,0)
    ag=g[:length].mean();al=l[:length].mean()
    for i in range(length,len(a)):
        if i>length:
            ag=(ag*(length-1)+g[i-1])/length
            al=(al*(length-1)+l[i-1])/length
        out[i]=50 if ag==0 and al==0 else (100 if al==0 else 100-100/(1+ag/al))
    return out
def crsi(close):
    c=np.asarray(close,float);n=len(c)
    streak=np.zeros(n)
    for i in range(1,n):
        streak[i]=max(0,streak[i-1])+1 if c[i]>c[i-1] else (
            min(0,streak[i-1])-1 if c[i]<c[i-1] else 0)
    roc=np.full(n,np.nan);roc[1:]=(c[1:]/c[:-1]-1)*100
    rank=np.full(n,np.nan)
    for i in range(100,n):
        w=roc[i-99:i+1]
        if np.isfinite(w).all():rank[i]=100*np.mean(w<=roc[i])
    return (rsi(c,3)+rsi(streak,2)+rank)/3
def supertrend(h,l,c):
    h,l,c=[np.asarray(a,float) for a in (h,l,c)]
    n=len(c)
    tr=np.empty(n);tr[0]=h[0]-l[0]
    tr[1:]=np.maximum.reduce([h[1:]-l[1:],abs(h[1:]-c[:-1]),abs(l[1:]-c[:-1])])
    bup=(h+l)/2+tr;blo=(h+l)/2-tr
    up=np.empty(n);low=np.empty(n);direction=np.empty(n,dtype=int)
    line=np.empty(n);up[0]=bup[0];low[0]=blo[0];direction[0]=-1;line[0]=up[0]
    for i in range(1,n):
        low[i]=blo[i] if blo[i]>low[i-1] or c[i-1]<low[i-1] else low[i-1]
        up[i]=bup[i] if bup[i]<up[i-1] or c[i-1]>up[i-1] else up[i-1]
        direction[i]=(1 if c[i]>up[i] else -1) if direction[i-1]==-1 else (
                       -1 if c[i]<low[i] else 1)
        line[i]=low[i] if direction[i]==1 else up[i]
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
print("One 15M PDF group count:",len(groups))
print("Matched 15M signal pages:",sum(bool(s["matches"]) for s in s15))

GREEN=HexColor("#009E72");RED=HexColor("#D74B59")
BLUE=HexColor("#1687CE");GRID=HexColor("#D5D8DE")
GRAY=HexColor("#707580");BLACK=HexColor("#20252A")
W,H=landscape(A4)
def panel(pdf,frame,bounds,center,top,bottom,crbottom,crtop,label,marker):
    segment=frame.segment.iat[center]
    a,b=bounds[segment];start=max(a,center-BEFORE);stop=min(b,center+AFTER)
    part=frame.iloc[start:stop+1]
    o=part.open.to_numpy();hi=part.high.to_numpy();lo=part.low.to_numpy()
    cl=part.close.to_numpy();st=part.st.to_numpy()
    tr=part.trend.to_numpy();cr=part.crsi.to_numpy()
    n=len(part);pos=center-start
    x0,x1=58,751;dx=(x1-x0)/n
    X=lambda k:x0+(k+.5)*dx
    minp=min(lo.min(),st.min());maxp=max(hi.max(),st.max())
    pad=max((maxp-minp)*.07,maxp*.001)
    minp-=pad;maxp+=pad
    Y=lambda v:bottom+(v-minp)/(maxp-minp)*(top-bottom)
    R=lambda v:crbottom+v/100*(crtop-crbottom)
    pdf.setFillColor(BLACK);pdf.setFont("Helvetica-Bold",9)
    pdf.drawString(45,top+10,label)
    for k in range(4):
        v=minp+(maxp-minp)*k/3
        pdf.setStrokeColor(GRID);pdf.setLineWidth(.4)
        pdf.line(x0,Y(v),x1,Y(v))
        pdf.setFillColor(GRAY);pdf.setFont("Helvetica",6)
        pdf.drawString(755,Y(v)-2,f"{v:,.0f}")
    for k in range(n):
        color=GREEN if cl[k]>=o[k] else RED
        pdf.setStrokeColor(color);pdf.setFillColor(color)
        pdf.setLineWidth(.7);pdf.line(X(k),Y(lo[k]),X(k),Y(hi[k]))
        pdf.rect(X(k)-min(9,dx*.5)/2,min(Y(o[k]),Y(cl[k])),
                 min(9,dx*.5),max(1,abs(Y(cl[k])-Y(o[k]))),stroke=0,fill=1)
    pdf.setLineWidth(1.8)
    for k in range(1,n):
        if tr[k]==tr[k-1]:
            pdf.setStrokeColor(GREEN if tr[k]==1 else RED)
            pdf.line(X(k-1),Y(st[k-1]),X(k),Y(st[k]))
    pdf.setStrokeColor(RED if marker=="RED" else GREEN)
    pdf.setDash(2,2);pdf.line(X(pos),crbottom,X(pos),top);pdf.setDash()
    pdf.setFont("Helvetica",6.3);pdf.setFillColor(GRAY)
    for k in sorted(set([0,pos,n-1]+list(range(0,n,max(1,n//5))))):
        pdf.drawCentredString(X(k),bottom-13,
            part.time.iat[k].strftime("%d/%m %H:%M"))
    for level in (30,50,70):
        pdf.setStrokeColor(GRID);pdf.line(x0,R(level),x1,R(level))
        pdf.setFillColor(GRAY);pdf.drawString(754,R(level)-2,str(level))
    pdf.setStrokeColor(BLUE);pdf.setLineWidth(1.2)
    for k in range(1,n):
        if np.isfinite(cr[k]) and np.isfinite(cr[k-1]):
            pdf.line(X(k-1),R(cr[k-1]),X(k),R(cr[k]))
    if np.isfinite(cr[pos]):
        pdf.setFillColor(BLUE);pdf.circle(X(pos),R(cr[pos]),2.8,fill=1,stroke=0)
def render(pdf,s):
    t=s["time"];color="GREEN" if s["direction"]==1 else "RED"
    pdf.setFont("Helvetica-Bold",13);pdf.setFillColor(BLACK)
    pdf.drawString(42,568,f"15M vs 1H | SuperTrend (1,1) | CRSI (3,2,100)")
    pdf.setFont("Helvetica",9)
    pdf.drawString(42,551,
        f"15M: {t:%Y-%m-%d %H:%M} UTC | {s['code']} | {color} | {s['source']}")
    matches=s["matches"]
    if matches:
        desc="; ".join(
            f"1{h['code'].lower()}{h['time']:%H}{h['time']:%d} ({h['time']:%Y-%m-%d %H:%M} UTC)"
            for h in matches[:3])
        line="MATCH with 1H: "+desc
        pdf.setFillColor(GREEN)
    else:
        line="NO MATCH: no same-direction 1H flip in the +/- matching window"
        pdf.setFillColor(RED)
    pdf.setFont("Helvetica-Bold",8.3);pdf.drawString(42,535,line[:155])
    panel(pdf,df,b15,s["i"],514,409,350,375,
          "15-MINUTE | selected signal",color)
    if matches:
        hidx=matches[0]["i"];hcolor=color
        hlabel=f"1-HOUR | matched signal {matches[0]['time']:%Y-%m-%d %H:%M} UTC"
    else:
        idx=int(hour.time.searchsorted(t,side="right"))-1
        hidx=max(0,idx)
        if hour.source.iat[hidx]!=s["source"]:
            hidx=None
        hcolor=color
        hlabel="1-HOUR | reference candles (no matching 1H signal)"
    if hidx is not None:
        panel(pdf,hour,b1h,hidx,303,196,126,152,hlabel,hcolor)
    pdf.setFillColor(GRAY);pdf.setFont("Helvetica",7)
    pdf.drawString(43,75,
        "Historical matching: 1H 08:00 signal compares with 15M 07:00-08:45, inclusive.")
    pdf.drawString(43,62,
        "All times are UTC candle OPEN times; a signal is confirmed only after candle CLOSE.")
    pdf.drawString(43,49,
        "Month/year are retained inside charts; PDF filenames group by code, HHMM and day only.")
    pdf.drawString(43,36,
        "Bitstamp BTC/USD before Binance BTC/USDT; results may differ from TradingView indicators.")
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
        pdf=canvas.Canvas(str(local),pagesize=landscape(A4),pageCompression=1)
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
print("DONE: only ONE 15M grouped PDF set.",OUTPUT)
print("Total 15M signal pages:",len(s15))
print("Total PDFs:",len(groups))
print("Historical comparison ONLY: TradingView parity has not been independently verified.")
