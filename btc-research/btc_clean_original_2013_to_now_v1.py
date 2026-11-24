# BITCOIN ORIGINAL HISTORICAL OHLCV CLEAN DATA EXPORT
# 2013 -> CURRENT LAST COMPLETED CANDLE (UTC).
# Single market: BITSTAMP BTC/USD. NO INDICATORS. NO TRADING SIGNALS.
# Native 15m OHLCV via official public Bitstamp API; complete 1h/1d
# are aggregated from four/96 consecutive native 15m bars, respectively.
# Never interpolate or fabricate missing price candles.
# Resume: downloads stored in small, atomic Drive CSV.gz batches.

import sys, subprocess, csv, json, os, time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict
subprocess.check_call([sys.executable,"-m","pip","install","-q","pandas","numpy","requests"])
import pandas as pd
import numpy as np
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from google.colab import drive

drive.mount("/content/drive")
BASE=Path("/content/drive/MyDrive/BTC_ORIGINAL_OHLCV_2013_NOW_V1")
PARTS=BASE/"DOWNLOAD_PARTS"
CLEAN=BASE/"CLEAN_CSV"
REPORTS=BASE/"AUDIT_REPORTS"
for folder in (PARTS,CLEAN,REPORTS): folder.mkdir(parents=True,exist_ok=True)
START=pd.Timestamp("2013-01-01",tz="UTC")
NOW=pd.Timestamp.now(tz="UTC")
# Only candles whose 15-minute close already occurred, avoiding current partial bar.
END_OPEN=(NOW.floor("15min")-pd.Timedelta(minutes=15))
START_SECONDS=int(START.timestamp())
END_SECONDS=int(END_OPEN.timestamp())
BASE_URL="https://www.bitstamp.net/api/v2/ohlc/btcusd/"
COLS=["open_time_utc","open","high","low","close","volume","market"]
FINAL_COLS=["open_time_utc","close_time_utc","open","high","low","close","volume","market","timeframe"]
session=requests.Session()
session.mount("https://",HTTPAdapter(max_retries=Retry(
    total=7,backoff_factor=1.5,status_forcelist=[429,500,502,503,504],
    allowed_methods=["GET"])))
session.headers["User-Agent"]="BTC Historical Original OHLCV Academic Research"
STATE=PARTS/"DOWNLOAD_STATE.json"
STATUS=BASE/"RUN_STATUS.txt"
CHUNK=20  # persist after every 20 exchange requests, resume after interruption.

def progress(text):
    STATUS.write_text(
        "BTC ORIGINAL OHLCV DATASET\n"+
        "UTC "+datetime.now(timezone.utc).isoformat()+"\n"+
        text+"\n"+
        "Source: Bitstamp BTC/USD public OHLC API; no indicators.\n",
        encoding="utf-8")
    print(text,flush=True)

def atomic_json(path, obj):
    tmp=path.with_name(path.name+".tmp")
    tmp.write_text(json.dumps(obj,indent=2),encoding="utf-8")
    os.replace(tmp,path)

def api(end_cursor):
    r=session.get(BASE_URL,params={
        "step":900,"limit":1000,"end":int(end_cursor),
        "exclude_current_candle":"true"
    },timeout=90)
    r.raise_for_status()
    data=r.json()
    items=data.get("data",{}).get("ohlc",[])
    if not items:
        raise RuntimeError("No Bitstamp OHLC returned for cursor "+str(end_cursor))
    rows=[]
    stamps=[]
    for x in items:
        raw=int(x["timestamp"])
        stamps.append(raw)
        rows.append({
            "open_time_utc":pd.to_datetime(raw,unit="s",utc=True),
            "open":float(x["open"]),"high":float(x["high"]),
            "low":float(x["low"]),"close":float(x["close"]),
            "volume":float(x.get("volume",np.nan)),
            "market":"Bitstamp BTC/USD"
        })
    oldest=min(stamps)
    if oldest >= end_cursor:
        raise RuntimeError("Historical pagination failed to advance. Details at "+BASE_URL)
    return rows,oldest

# Download backwards. Persist completed chunks FIRST, then checkpoint cursor.
state=json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {
    "next_cursor": END_SECONDS+900,
    "completed": False,
    "chunk_index": 0,
    "request_count": 0
}
batch=[]
attempts=0
progress("DRIVE CONNECTED. Downloading original OHLCV 2013-to-now; resuming saved chunks.")
if not state["completed"]:
    cursor=int(state["next_cursor"])
    while cursor>=START_SECONDS:
        rows,oldest=api(cursor)
        batch.extend(rows)
        cursor=oldest-1
        attempts+=1
        state["request_count"]+=1
        if attempts % CHUNK==0 or cursor<START_SECONDS:
            chunk_no=int(state["chunk_index"])
            filename=f"CHUNK_{chunk_no:05d}.csv.gz"
            dest=PARTS/filename
            temp=PARTS/(filename+".partial")
            pd.DataFrame(batch,columns=COLS).to_csv(
                temp,index=False,compression="gzip")
            if not temp.exists() or temp.stat().st_size<100:
                raise RuntimeError("Drive chunk write failed")
            os.replace(temp,dest)
            state["chunk_index"]=chunk_no+1
            state["next_cursor"]=cursor
            atomic_json(STATE,state)
            progress(
                f"Saved chunk {chunk_no+1}, newest historical UTC "
                f"{pd.to_datetime(oldest,unit='s',utc=True)}. "
                f"Requests: {state['request_count']}.")
            batch.clear()
        if cursor<START_SECONDS: break
        time.sleep(0.18)
    state["completed"]=True
    state["next_cursor"]=cursor
    atomic_json(STATE,state)
progress("DOWNLOAD PHASE COMPLETE. Validating all historical records.")

parts=sorted(PARTS.glob("CHUNK_*.csv.gz"))
if not parts: raise RuntimeError("No original exchange data downloaded.")
frames=[]
for f in parts:
    p=pd.read_csv(f)
    p["open_time_utc"]=pd.to_datetime(
        p["open_time_utc"],format="mixed",utc=True)
    frames.append(p)
raw=pd.concat(frames,ignore_index=True)
raw=raw.sort_values("open_time_utc").drop_duplicates(
    "open_time_utc",keep="last").reset_index(drop=True)
raw=raw[
    (raw.open_time_utc>=START)
    &(raw.open_time_utc<=END_OPEN)
].reset_index(drop=True)
if raw.empty: raise RuntimeError("No candles in the requested period.")
raw.to_csv(REPORTS/"RAW_EXCHANGE_OBSERVATIONS.csv.gz",
           index=False,compression="gzip")
valid=(
    np.isfinite(raw[["open","high","low","close","volume"]]).all(axis=1)
    &(raw[["open","high","low","close"]]>0).all(axis=1)
    &(raw["volume"]>=0)
    &(raw.high>=raw[["open","close","low"]].max(axis=1))
    &(raw.low<=raw[["open","close","high"]].min(axis=1))
    &(raw.open_time_utc.dt.minute%15==0)
    &(raw.open_time_utc.dt.second==0)
)
bad=raw.loc[~valid].copy()
bad.to_csv(REPORTS/"INVALID_OR_OFF_GRID_ROWS.csv",index=False)
clean=raw.loc[valid].copy()
# Genuine missing intervals are documented, not forward filled.
delta=clean.open_time_utc.diff()
gapmask=delta>pd.Timedelta(minutes=15)
gap=clean.loc[gapmask,["open_time_utc"]].copy()
gap["prev_open_utc"]=clean.open_time_utc.shift()[gapmask].values
gap["gap_minutes"]=delta[gapmask].dt.total_seconds()/60
gap["missing_15m_candles"]=(gap["gap_minutes"]/15-1).astype("int64")
gap.to_csv(REPORTS/"MISSING_INTERVALS.csv",index=False)
clean["close_time_utc"]=clean.open_time_utc+pd.Timedelta(minutes=15)
clean["timeframe"]="15m"
clean=clean[FINAL_COLS]
clean.to_csv(CLEAN/"BITSTAMP_BTCUSD_15M_2013_NOW.csv.gz",
             index=False,compression="gzip")
# One original market, separate annual files for easier analysis.
clean["year"]=clean.open_time_utc.dt.year
for year,p in clean.groupby("year",sort=True):
    p.drop(columns=["year"]).to_csv(
        CLEAN/f"BITSTAMP_BTCUSD_15M_{year}.csv.gz",
        index=False,compression="gzip")
clean=clean.drop(columns=["year"])

# Resample to hours/days ONLY IF full, exact, continuous constituent bars exist.
indexed=clean.set_index("open_time_utc").sort_index()
def full_aggregate(rule,expected,label):
    bars=indexed.resample(rule,label="left",closed="left").agg({
        "open":"first","high":"max","low":"min",
        "close":"last","volume":"sum","market":"first"})
    sizes=indexed["close"].resample(rule,label="left",closed="left").size()
    bars=bars.loc[sizes==expected].reset_index()
    duration=pd.Timedelta(hours=1) if rule=="1h" else pd.Timedelta(days=1)
    bars["close_time_utc"]=bars.open_time_utc+duration
    bars["timeframe"]=label
    return bars[FINAL_COLS]
h1=full_aggregate("1h",4,"1h")
d1=full_aggregate("1D",96,"1d")
h1.to_csv(CLEAN/"BITSTAMP_BTCUSD_1H_COMPLETE.csv.gz",index=False,compression="gzip")
d1.to_csv(CLEAN/"BITSTAMP_BTCUSD_1D_COMPLETE.csv.gz",index=False,compression="gzip")

annual=clean.assign(year=clean.open_time_utc.dt.year).groupby("year").agg(
    candles=("close","size"),
    first_open_utc=("open_time_utc","min"),
    last_open_utc=("open_time_utc","max")).reset_index()
annual.to_csv(REPORTS/"YEAR_BY_YEAR_COVERAGE.csv",index=False)

expected_global=int((END_OPEN-START)/pd.Timedelta(minutes=15))+1
report=[
    "BITCOIN OHLCV ORIGINAL DATA QUALITY REPORT",
    "Historical source: BITSTAMP BTC/USD public OHLCV API (single market)",
    "Requested start (UTC): "+str(START),
    "Requested last complete 15m candle open (UTC): "+str(END_OPEN),
    "First REAL candle (UTC): "+str(clean.open_time_utc.iloc[0]),
    "Last REAL candle (UTC): "+str(clean.open_time_utc.iloc[-1]),
    "Expected 15m timestamps in requested range: "+str(expected_global),
    "Valid original 15m candles: "+str(len(clean)),
    "Invalid / off-grid observations excluded: "+str(len(bad)),
    "Missing-interval events: "+str(len(gap)),
    "Total missing 15m slots between observed candles: "+str(
        int(gap.missing_15m_candles.sum()) if len(gap) else 0),
    "Complete reconstructed 1h candles: "+str(len(h1)),
    "Complete reconstructed 1d candles: "+str(len(d1)),
    "Interpolated / fabricated candles: ZERO",
    "Indicators / entry / exit / signals: NONE",
    "Original source market is BTC/USD, not Binance BTC/USDT.",
    "Download provenance: public Bitstamp OHLC endpoint; data may contain exchange-side gaps.",
    "Public OHLCV is exchange-published aggregation, not raw trade tick data.",
    "Source docs: https://www.bitstamp.net/api/"
]
(REPORTS/"DATA_QUALITY_SUMMARY.txt").write_text(
    "\n".join(report)+"\n",encoding="utf-8")
progress("COMPLETE. Original data exported; gaps/invalid data audited.")
print("\n"+"\n".join(report))
print("\nGoogle Drive clean files:",CLEAN)
print("Quality audits:",REPORTS)
