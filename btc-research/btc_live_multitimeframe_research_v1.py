# BTC Multitimeframe Market Research Monitor
# Google Colab | Run once for a FRESH market snapshot | READ-ONLY public OHLC.
# Educational/paper-trading only. NO ORDERS. NO 98% ACCURACY CLAIM.
# On every Run: refreshes from Binance Spot public market data for all timeframes.
import sys, subprocess
subprocess.check_call([sys.executable, "-m", "pip", "install", "-q",
                       "pandas", "numpy", "requests", "matplotlib"])
import json, time
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from google.colab import drive
from IPython.display import display

PAIR = "BTCUSDT"                      # Binance BTC/USDT Spot
INTERVALS = ["1m","3m","5m","15m","30m","1h"]
MS = {"1m":60000,"3m":180000,"5m":300000,
      "15m":900000,"30m":1800000,"1h":3600000}
MIN_CANDLES = 300
BASE_URL = "https://data-api.binance.vision"
REPORT_FOLDER = "BTC_LIVE_RESEARCH_READ_ONLY_V1"

drive.mount("/content/drive")
ROOT = Path("/content/drive/MyDrive")/REPORT_FOLDER
ROOT.mkdir(parents=True, exist_ok=True)
SESSION = requests.Session()
SESSION.mount("https://", HTTPAdapter(max_retries=Retry(
    total=3, backoff_factor=1, status_forcelist=[429,500,502,503,504],
    allowed_methods=["GET"])))
SESSION.headers.update({"Accept":"application/json"})

def api(endpoint, params=None):
    response = SESSION.get(BASE_URL+endpoint, params=params, timeout=25)
    response.raise_for_status()
    value = response.json()
    if isinstance(value,dict) and "code" in value and "msg" in value:
        raise RuntimeError(str(value))
    return value

def wilder_rsi(close, n=14):
    delta=close.diff()
    gain=delta.clip(lower=0)
    loss=-delta.clip(upper=0)
    avg_gain=gain.ewm(alpha=1/n,adjust=False,min_periods=n).mean()
    avg_loss=loss.ewm(alpha=1/n,adjust=False,min_periods=n).mean()
    rs=avg_gain/avg_loss.replace(0,np.nan)
    output=100-100/(1+rs)
    output=output.mask((avg_loss==0)&(avg_gain>0),100)
    output=output.mask((avg_loss==0)&(avg_gain==0),50)
    return output

def adx_components(frame,n=14):
    high=frame.high
    low=frame.low
    close=frame.close
    up=high.diff()
    down=-low.diff()
    plus_dm=up.where((up>down)&(up>0),0)
    minus_dm=down.where((down>up)&(down>0),0)
    true_range=pd.concat([
        high-low, (high-close.shift()).abs(),
        (low-close.shift()).abs()],axis=1).max(axis=1)
    atr=true_range.ewm(alpha=1/n,adjust=False,min_periods=n).mean()
    plus=100*plus_dm.ewm(alpha=1/n,adjust=False,min_periods=n).mean()/atr.replace(0,np.nan)
    minus=100*minus_dm.ewm(alpha=1/n,adjust=False,min_periods=n).mean()/atr.replace(0,np.nan)
    dx=100*(plus-minus).abs()/(plus+minus).replace(0,np.nan)
    adx=dx.ewm(alpha=1/n,adjust=False,min_periods=n).mean()
    return atr, adx

def parse_klines(interval,now_ms):
    rows=api("/api/v3/klines",{"symbol":PAIR,"interval":interval,"limit":1000})
    if not isinstance(rows,list) or not rows:
        raise RuntimeError("No kline data for "+interval)
    data=pd.DataFrame([{
        "open_ms":int(r[0]),"close_ms":int(r[6]),
        "open":float(r[1]),"high":float(r[2]),
        "low":float(r[3]),"close":float(r[4]),
        "volume":float(r[5])
    } for r in rows])
    # Binance's close timestamp is end-of-period minus 1 ms.
    # Exclude the currently forming candle using exchange server time.
    data=data[data.close_ms < now_ms-1500].copy()
    data=data.sort_values("open_ms").drop_duplicates("open_ms")
    data=data.reset_index(drop=True)
    data["open_utc"]=pd.to_datetime(data.open_ms,unit="ms",utc=True)
    data["closed_utc"]=pd.to_datetime(data.close_ms+1,unit="ms",utc=True)
    if len(data)<MIN_CANDLES:
        raise RuntimeError("Too few CLOSED "+interval+" candles")
    for p in ("open","high","low","close"):
        if not np.isfinite(data[p]).all() or (data[p]<=0).any():
            raise RuntimeError("Invalid "+interval+" prices")
    if (data.high<data[["open","close","low"]].max(axis=1)).any():
        raise RuntimeError("Invalid "+interval+" OHLC")
    if (data.low>data[["open","close","high"]].min(axis=1)).any():
        raise RuntimeError("Invalid "+interval+" OHLC")
    interval_ms=MS[interval]
    data["continuous"]=data.open_ms.diff().eq(interval_ms)
    data["gap_count"]=(~data.continuous).cumsum()
    return data

def indicators(frame):
    d=frame.copy()
    close=d.close
    d["ema20"]=close.ewm(span=20,adjust=False,min_periods=20).mean()
    d["ema50"]=close.ewm(span=50,adjust=False,min_periods=50).mean()
    d["ema200"]=close.ewm(span=200,adjust=False,min_periods=200).mean()
    d["rsi14"]=wilder_rsi(close,14)
    macd=close.ewm(span=12,adjust=False,min_periods=26).mean()-close.ewm(span=26,adjust=False,min_periods=26).mean()
    d["macd_hist"]=macd-macd.ewm(span=9,adjust=False,min_periods=9).mean()
    d["atr14"],d["adx14"]=adx_components(d,14)
    d["volume_ratio"]=d.volume/d.volume.rolling(20,min_periods=20).mean()
    # An indicator agreement score, NOT predictive probability or win rate.
    bull=[
        close>d.ema20, d.ema20>d.ema50, d.ema50>d.ema200,
        d.rsi14.between(50,70),d.macd_hist>0,d.adx14>=20,
        d.volume_ratio>=1
    ]
    bear=[
        close<d.ema20,d.ema20<d.ema50,d.ema50<d.ema200,
        d.rsi14.between(30,50),d.macd_hist<0,d.adx14>=20,
        d.volume_ratio>=1
    ]
    d["bull_agreement"]=sum(x.astype(int) for x in bull)
    d["bear_agreement"]=sum(x.astype(int) for x in bear)
    needed=["ema200","rsi14","macd_hist","atr14","adx14","volume_ratio"]
    d["ready"]=d[needed].notna().all(axis=1)
    return d

print("Fetching fresh exchange time and CLOSED candles...")
now_ms=int(api("/api/v3/time")["serverTime"])
now_utc=pd.to_datetime(now_ms,unit="ms",utc=True)
frames={}
for tf in INTERVALS:
    frames[tf]=indicators(parse_klines(tf,now_ms))
    x=frames[tf]
    print(f"{tf}: {len(x)} CLOSED candles, latest closes {x.closed_utc.iat[-1]}")

# Only use a one-hour trend once its candle is CLOSED, even for 1m data.
hour=frames["1h"]
hour_ref=hour[["closed_utc","ema50","ema200","bull_agreement","bear_agreement","ready"]].copy()
hour_ref=hour_ref.rename(columns={
    "bull_agreement":"hour_bull",
    "bear_agreement":"hour_bear",
    "ready":"hour_ready"
})
hour_ref["hour_bullish"]=hour_ref.hour_ready & (hour_ref.ema50>hour_ref.ema200) & (hour_ref.hour_bull>=5)
hour_ref["hour_bearish"]=hour_ref.hour_ready & (hour_ref.ema50<hour_ref.ema200) & (hour_ref.hour_bear>=5)
hour_ref=hour_ref[["closed_utc","hour_bullish","hour_bearish"]].rename(columns={"closed_utc":"confirmed_1h_utc"})

all_candles=[]
latest=[]
for tf in INTERVALS:
    df=frames[tf].copy()
    df=pd.merge_asof(
        df.sort_values("closed_utc"),
        hour_ref.sort_values("confirmed_1h_utc"),
        left_on="closed_utc",right_on="confirmed_1h_utc",
        direction="backward",allow_exact_matches=True)
    df["hour_bullish"]=df.hour_bullish.fillna(False).astype(bool)
    df["hour_bearish"]=df.hour_bearish.fillna(False).astype(bool)
    # This is a retrospective indicator screen, not a trade recommendation.
    up=df.ready & (df.bull_agreement>=5) & df.hour_bullish
    down=df.ready & (df.bear_agreement>=5) & df.hour_bearish
    df["screen_status"]=np.select(
        [up,down],["BULLISH_WATCH","BEARISH_WATCH"],default="NO_CLEAR_SETUP")
    df["timeframe"]=tf
    df["agreement_max7"]=np.maximum(df.bull_agreement,df.bear_agreement)
    # Illustrative volatility bands; not actual orders or future price forecasts.
    df["reference_low_1atr"]=df.close-df.atr14
    df["reference_high_1atr"]=df.close+df.atr14
    fields=["timeframe","open_utc","closed_utc","open","high","low","close",
            "volume","ema20","ema50","ema200","rsi14","macd_hist","adx14",
            "atr14","volume_ratio","bull_agreement","bear_agreement",
            "agreement_max7","confirmed_1h_utc","screen_status",
            "reference_low_1atr","reference_high_1atr"]
    all_candles.append(df[fields])
    row=df[fields].iloc[-1].to_dict()
    row["market"]="Binance Spot BTCUSDT"
    row["snapshot_exchange_utc"]=now_utc
    latest.append(row)

full=pd.concat(all_candles,ignore_index=True)
summary=pd.DataFrame(latest)
stamp=now_utc.strftime("%Y%m%d_%H%M%S")
full.to_csv(ROOT/f"ALL_CLOSED_CANDLES_{stamp}.csv",index=False)
summary.to_csv(ROOT/"LATEST_SNAPSHOT.csv",index=False)

# Append run snapshots while dropping duplicate same candle/timeframe rows.
logfile=ROOT/"SNAPSHOT_HISTORY.csv"
if logfile.exists():
    old=pd.read_csv(logfile)
    history=pd.concat([old,summary],ignore_index=True)
else:
    history=summary.copy()
history=history.drop_duplicates(["timeframe","closed_utc"],keep="last")
history.to_csv(logfile,index=False)

show=summary[["timeframe","closed_utc","close","rsi14","adx14",
              "bull_agreement","bear_agreement","screen_status",
              "reference_low_1atr","reference_high_1atr"]].copy()
for key in ["close","rsi14","adx14","reference_low_1atr","reference_high_1atr"]:
    show[key]=pd.to_numeric(show[key]).round(2)
print("\nBTCUSDT SPOT — FRESH CLOSED-CANDLE SCREEN, UTC")
print("Fetched at exchange UTC:",now_utc)
display(show)

# Visually display the last 60 closed one-hour candles (not a forecast).
import matplotlib.pyplot as plt
chart=frames["1h"].tail(60)
plt.figure(figsize=(12,4))
plt.plot(chart.open_utc,chart.close,label="1H historical close")
plt.plot(chart.open_utc,chart.ema20,label="EMA20")
plt.plot(chart.open_utc,chart.ema50,label="EMA50")
plt.title("BTC/USDT Spot — Last 60 CLOSED 1H candles (historical)")
plt.legend()
plt.grid(alpha=0.2)
plt.xticks(rotation=25)
plt.tight_layout()
plt.savefig(ROOT/"LATEST_1H_CHART.png",dpi=140)
plt.show()

text=(
    f"BTC MARKET RESEARCH SNAPSHOT (NO TRADING ORDERS)\n"
    f"Exchange UTC: {now_utc}\n"
    f"Market: Binance BTCUSDT SPOT\n"
    f"Timeframes: {', '.join(INTERVALS)}\n"
    "Each status is an INDICATOR AGREEMENT screen, not probability or 98% accuracy.\n"
    "NO_CLEAR_SETUP means there is no clear conditions-based watch signal.\n"
    "ATR reference bands are descriptive volatility estimates, not stop/target orders.\n"
    "NO real-money execution, personalized trade entry or exit instruction.\n"
    "The system is a manually refreshed REST snapshot, not a streaming feed.\n"
    "Data source: https://data-api.binance.vision/api/v3/klines\n"
)
(ROOT/"READ_ME_FIRST.txt").write_text(text,encoding="utf-8")
print("\nReports saved to:",ROOT)
print("Snapshot:",ROOT/"LATEST_SNAPSHOT.csv")
print("Every checked closed candle:",ROOT/f"ALL_CLOSED_CANDLES_{stamp}.csv")
print("No position opened. No broker credentials required.")
