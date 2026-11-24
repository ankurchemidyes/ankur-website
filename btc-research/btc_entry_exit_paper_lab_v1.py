# BTC Research Lab — PAPER BACKTEST ONLY
# 1H completed trend + 15M entry, close-confirmed, next bar open.
# No brokerage login, API keys, real orders or position sizing.
# Assumptions are editable; results never guarantee future returns.
import sys, subprocess, io, csv, zipfile, calendar, hashlib, time
from pathlib import Path
from datetime import date, datetime, timezone
import numpy as np
import pandas as pd
import requests
from google.colab import drive

subprocess.check_call([sys.executable,"-m","pip","install","-q","pandas","numpy","requests"])
drive.mount("/content/drive")
BASE=Path("/content/drive/MyDrive/BTC_ENTRY_EXIT_PAPER_RESEARCH_V1")
CACHE=BASE/"CACHE"
OUT=BASE/"REPORTS"
for folder in (CACHE,OUT): folder.mkdir(parents=True,exist_ok=True)

# Spot BTC/USDT, one exchange only. The dataset is historical, not live.
START=date(2021,1,1)
END=date(2026,10,31)
TEST_SPLIT=pd.Timestamp("2025-01-01",tz="UTC")
FEE_PER_SIDE=0.001       # illustrative 0.10% per side
SLIPPAGE_PER_SIDE=0.0005 # illustrative 0.05% per side
STOP_ATR_MULT=1.2
TARGET_ATR_MULT=1.8
MAX_HOLD_BARS=32         # 8 hours on 15M
MIN_TEST_TRADES=50
URL_BASE="https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/15m/"
session=requests.Session()
session.headers["User-Agent"]="Bitcoin historical educational research"

def month_iter(start,end):
    d=date(start.year,start.month,1)
    while d<=end:
        yield d
        d=date(d.year+(d.month==12),(d.month%12)+1,1)

def read_archive(blob):
    rows=[]
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        if z.testzip() is not None: raise ValueError("ZIP checksum/internal error")
        names=[x for x in z.namelist() if x.lower().endswith(".csv")]
        if len(names)!=1: raise ValueError("Unexpected archive structure")
        with z.open(names[0]) as file:
            for x in csv.reader(io.TextIOWrapper(file)):
                if len(x)<5: continue
                try: stamp=int(x[0])
                except ValueError: continue
                unit="us" if stamp>=10**14 else "ms"
                rows.append((pd.to_datetime(stamp,unit=unit,utc=True),
                            *[float(v) for v in x[1:5]]))
    return pd.DataFrame(rows,columns=["time","open","high","low","close"])

frames=[]
for d in month_iter(START,END):
    filename=f"BTCUSDT-15m-{d.year}-{d.month:02d}.zip"
    file=CACHE/filename
    if not file.exists():
        url=URL_BASE+filename
        response=session.get(url,timeout=90)
        response.raise_for_status()
        blob=response.content
        if not zipfile.is_zipfile(io.BytesIO(blob)):
            raise ValueError("Bad exchange ZIP: "+filename)
        file.write_bytes(blob)
    part=read_archive(file.read_bytes())
    if part.empty: raise ValueError("Empty historical month "+str(d))
    frames.append(part)
    print("History:",d.strftime("%Y-%m"),len(part),"candles")
df=pd.concat(frames,ignore_index=True)
df=df.sort_values("time").drop_duplicates("time").reset_index(drop=True)
df=df[(df.time>=pd.Timestamp(START,tz="UTC"))
      &(df.time<pd.Timestamp(END, tz="UTC")+pd.Timedelta(days=1))].copy()
df=df.reset_index(drop=True)
assert not df.empty
valid=((df[["open","high","low","close"]]>0).all(axis=1)
       &(df.high>=df[["open","close","low"]].max(axis=1))
       &(df.low<=df[["open","close","high"]].min(axis=1)))
if not valid.all(): raise ValueError("Bad OHLC found")
df["gap"]=df.time.diff().ne(pd.Timedelta(minutes=15))
df["segment"]=df.gap.cumsum()
df.loc[df.gap,["time","open","high","low","close"]].to_csv(
    OUT/"TIME_GAPS_AND_STARTS.csv",index=False)
print("15M candles:",len(df),"segments:",df.segment.nunique())

# 1H trend uses only the last FULLY CLOSED hour.
hourly=df.set_index("time").resample("1h").agg({
    "open":"first","high":"max","low":"min","close":"last"})
hourcount=df.set_index("time").close.resample("1h").count()
hourly=hourly[hourcount==4].copy()
hourly["ema200"]=hourly.close.ewm(span=200,adjust=False,min_periods=200).mean()
hourly["trend_long"]=(hourly.close>hourly.ema200)&(
    hourly.ema200>hourly.ema200.shift(4))
# Candle H is only known at H+1h. Mark as eligible starting next hour.
hourly["eligible_hour"]=hourly.index+pd.Timedelta(hours=1)
filter_series=hourly.set_index("eligible_hour")["trend_long"]
# During 15M hour, use last available confirmed 1H candle.
df["hour_bucket"]=df.time.dt.floor("h")
df["trend_long"]=df.hour_bucket.map(filter_series).fillna(False).astype(bool)
# If a 1H hour was missing, the filter is False (no backward/forward fill).

# Fifteen-minute indicators, computed separately in uninterrupted segments.
df["ema20"]=np.nan
df["rsi14"]=np.nan
df["atr14"]=np.nan
for _,p in df.groupby("segment",sort=False):
    ix=p.index
    close=p.close
    changes=close.diff()
    gain=changes.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    loss=(-changes.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    rsi=100-100/(1+(gain/loss.replace(0,np.nan)))
    rsi=np.where((loss==0)&(gain>0),100,np.where((gain==0)&(loss==0),50,rsi))
    tr=pd.concat([
        (p.high-p.low),
        (p.high-p.close.shift()).abs(),
        (p.low-p.close.shift()).abs()
    ],axis=1).max(axis=1)
    df.loc[ix,"ema20"]=close.ewm(span=20,adjust=False,min_periods=20).mean().values
    df.loc[ix,"rsi14"]=rsi
    df.loc[ix,"atr14"]=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean().values

# Entry signal at the CLOSED 15M candle:
# price crosses above EMA20; prior candle was at/below EMA20;
# RSI14 between 50 and 68; full 1H trend filter.
# No future information is used for signal creation.
same=df.segment.eq(df.segment.shift())
cross=(df.close>df.ema20)&(df.close.shift(1)<=df.ema20.shift(1))
signal=(same & df.trend_long & cross
        & df.rsi14.between(50,68,inclusive="both")
        & df.atr14.notna())
df["candidate"]=signal.fillna(False)
df["candidate"].to_csv(OUT/"SIGNAL_FLAGS.csv",index=False)

# Non-overlapping educational paper trades (spot long only).
# Entry at next 15M OPEN after signal, with adverse slippage.
# Stops/targets assumed hit using following bar H/L;
# if both touched in one bar, stop wins (conservative).
# Costs applied on both entry and exit, not omitted.
trades=[]
i=0
n=len(df)
while i<n-1:
    if not bool(df.candidate.iat[i]):
        i+=1
        continue
    entry_idx=i+1
    if df.segment.iat[entry_idx]!=df.segment.iat[i]:
        i+=1
        continue
    entry_raw=float(df.open.iat[entry_idx])
    entry=entry_raw*(1+SLIPPAGE_PER_SIDE)
    risk=float(df.atr14.iat[i])*STOP_ATR_MULT
    stop=entry-risk
    take=entry+float(df.atr14.iat[i])*TARGET_ATR_MULT
    if stop<=0 or risk<=0 or not np.isfinite([entry,stop,take]).all():
        i+=1
        continue
    exit_idx=None
    exit_raw=None
    reason=None
    max_idx=min(n-1,entry_idx+MAX_HOLD_BARS-1)
    for j in range(entry_idx,max_idx+1):
        if df.segment.iat[j]!=df.segment.iat[entry_idx]:
            break
        op,hi,lo,cl=[float(df[x].iat[j])
                      for x in ("open","high","low","close")]
        if op<=stop:
            exit_idx=j; exit_raw=op; reason="gap_stop"; break
        if op>=take:
            exit_idx=j; exit_raw=op; reason="gap_target"; break
        if lo<=stop:
            exit_idx=j; exit_raw=stop; reason="stop"; break
        if hi>=take:
            exit_idx=j; exit_raw=take; reason="target"; break
        exit_idx=j; exit_raw=cl; reason="time_exit"
    if exit_idx is None:
        i=entry_idx
        continue
    exit_price=exit_raw*(1-SLIPPAGE_PER_SIDE)
    gross=exit_price/entry-1
    net=(exit_price*(1-FEE_PER_SIDE))/(entry*(1+FEE_PER_SIDE))-1
    trades.append({
        "signal_utc":df.time.iat[i],
        "entry_utc":df.time.iat[entry_idx],
        "exit_utc":df.time.iat[exit_idx]+pd.Timedelta(minutes=15),
        "entry_price":entry,
        "stop_price":stop,
        "target_price":take,
        "exit_price":exit_price,
        "exit_reason":reason,
        "gross_return_pct":gross*100,
        "net_return_pct":net*100,
        "market":"Binance BTCUSDT spot",
        "period":"OUT_OF_SAMPLE" if df.time.iat[entry_idx]>=TEST_SPLIT else "DEVELOPMENT"
    })
    i=exit_idx+1
trade_columns=["signal_utc","entry_utc","exit_utc","entry_price",
               "stop_price","target_price","exit_price","exit_reason",
               "gross_return_pct","net_return_pct","market","period"]
trade_df=pd.DataFrame(trades,columns=trade_columns)
trade_df.to_csv(OUT/"ALL_PAPER_TRADES.csv",index=False)

def report(g):
    if len(g)==0:
        return {"trades":0,"wins":0,"win_rate_pct":np.nan,
                "mean_net_return_pct":np.nan,"compound_net_pct":np.nan,
                "max_drawdown_pct":np.nan,"profit_factor":np.nan}
    r=g.net_return_pct.to_numpy()/100
    wealth=np.cumprod(1+r)
    dd=wealth/np.maximum.accumulate(np.r_[1.0,wealth])[1:]-1
    wins=r[r>0].sum()
    losses=-r[r<0].sum()
    return {
        "trades":len(r),
        "wins":int((r>0).sum()),
        "win_rate_pct":round(100*np.mean(r>0),2),
        "mean_net_return_pct":round(100*r.mean(),4),
        "compound_net_pct":round(100*(wealth[-1]-1),2),
        "max_drawdown_pct":round(100*dd.min(),2),
        "profit_factor":round(float(wins/losses),3) if losses>0 else np.nan
    }

stats=[]
for name,g in [("DEVELOPMENT",trade_df[trade_df.period=="DEVELOPMENT"]),
               ("OUT_OF_SAMPLE",trade_df[trade_df.period=="OUT_OF_SAMPLE"]),
               ("ALL_HISTORY",trade_df)]:
    stats.append({"period":name,**report(g)})
summary=pd.DataFrame(stats)
summary.to_csv(OUT/"BACKTEST_SUMMARY.csv",index=False)
print("\n==== HISTORICAL PAPER BACKTEST RESULTS ====")
print(summary.to_string(index=False))
hold=summary[summary.period=="OUT_OF_SAMPLE"].iloc[0]
if (hold.trades>=MIN_TEST_TRADES and
    np.isfinite(hold.win_rate_pct) and
    hold.win_rate_pct>=70 and
    np.isfinite(hold.compound_net_pct) and
    hold.compound_net_pct>0 and
    np.isfinite(hold.profit_factor) and
    hold.profit_factor>1):
    verdict="RESEARCH CRITERIA MET IN HISTORICAL HOLDOUT; NO FUTURE GUARANTEE"
else:
    verdict="NOT VALIDATED FOR 70% TARGET; DO NOT ASSUME IT WORKS"
(OUT/"RESEARCH_VERDICT.txt").write_text(
    verdict+"\nReal-money orders: DISABLED\n"
    "Same-candle high/low cannot establish tick-by-tick execution.\n"
    "Costs and slippage are illustrative, not actual account prices.\n"
    "Data sources: Binance public monthly spot BTCUSDT 15m archives.\n",
    encoding="utf-8")
print("\n",verdict,"\nReports saved to:",OUT)
