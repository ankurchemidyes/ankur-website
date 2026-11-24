# SRK ORIGINAL PDF SIX-CANDLE VISUAL PATTERN SEARCH — V1
# Existing 180-degree SRK PDFs remain untouched. Uses exact same original OHLC.
# Sample must be a tightly-cropped image showing exactly SIX unobstructed candlesticks.
# Measures 24 body corners (4 per candle) plus 12 upper/lower wick extremes.
# Searches ONLY the central 60% region of each original 36-candle SRK page.
# Exports TOP TEN annotated PNG previews + CSV percentages (visual similarity only).
# No financial signal, no accuracy guarantee, no altered source PDFs.

import sys, subprocess
subprocess.check_call([
    sys.executable,"-m","pip","install","-q",
    "numpy","pandas","opencv-python-headless","pymupdf","pillow"])
import os, zipfile, math, re
from pathlib import Path
import numpy as np
import pandas as pd
import cv2
import fitz
from IPython.display import display, Image
from google.colab import drive, files

drive.mount("/content/drive")
BASE=Path("/content/drive/MyDrive/BTC_SRK_36_CANDLE_12H_STEP_2013_NOW")
ORIGINALS=BASE/"SRK_PDFS_180"
MANIFEST=BASE/"REPORTS/SRK_PAGE_MANIFEST_180.csv"
OHLC=BASE/"_ORIGINAL_EXCHANGE_DATA/CLEAN_BITSTAMP_1H_2013_NOW.csv.gz"
DEST=BASE/"TOP10_SIX_CANDLE_PATTERN_MATCH_V1"
DEST.mkdir(parents=True,exist_ok=True)

for path in (ORIGINALS,MANIFEST,OHLC):
    if not path.exists():
        raise FileNotFoundError(
            "Missing original SRK resource: "+str(path)+
            ". Complete the existing SRK generator before searching."
        )

print("ORIGINAL SRK FILES: READ-ONLY. No modifications will be made.")
print("Upload a CLOSE-CROPPED picture of SIX consecutive candles.")
print("Crop OUT axes, price labels, tools, arrows, indicators and extra candles.")
print("This first version requires six visible red/green candle bodies and wicks.")
uploaded=files.upload()
if len(uploaded)!=1:
    raise ValueError("Upload exactly ONE PNG/JPG sample showing SIX candles.")
sample_name=next(iter(uploaded))
buffer=np.frombuffer(uploaded[sample_name],dtype=np.uint8)
sample=cv2.imdecode(buffer,cv2.IMREAD_COLOR)
if sample is None:
    raise ValueError("The image could not be decoded. Use PNG or JPG.")

# Use strong colored candlestick ink; white backgrounds/grid are ignored.
def colored_masks(bgr):
    b=bgr[:,:,0].astype(np.int16)
    g=bgr[:,:,1].astype(np.int16)
    r=bgr[:,:,2].astype(np.int16)
    red=(r>=g+38)&(r>=b+20)&(r>85)
    green=(g>=r+26)&(g>=b+5)&(g>70)
    return red,green

red,green=colored_masks(sample)
ink=red|green
if ink.sum()<100:
    raise ValueError(
        "Too few red/green candlestick pixels. Crop the six-candle area more closely."
    )
height,width=ink.shape
hist=ink.sum(axis=0).astype(float)
# Six candles are assumed equally spaced across a tightly cropped image.
# Use the outer colored x pixels to define 6 equal cells.
positive=np.flatnonzero(hist>=2)
if len(positive)<12:
    raise ValueError("Cannot find six candlestick regions.")
left,right=int(positive[0]),int(positive[-1])+1
span=right-left
if span<36:
    raise ValueError("Uploaded sample is too narrow.")
edges=np.linspace(left,right,7).astype(int)

# Body: pixel columns with the widest candle body; wick: full vertical range.
def measure_six(red,green):
    all_ink=red|green
    h,w=all_ink.shape
    top=[];bottom=[];body_top=[];body_bottom=[];colors=[]
    for j in range(6):
        x0,x1=int(edges[j]),int(edges[j+1])
        if x1<=x0:
            raise ValueError("Invalid sample crop.")
        clip=all_ink[:,x0:x1]
        nr=int(red[:,x0:x1].sum())
        ng=int(green[:,x0:x1].sum())
        if max(nr,ng)<7:
            raise ValueError(
                f"Cannot detect candle {j+1}; provide six candles with no overlay."
            )
        color=1 if ng>=nr else 0
        colors.append(color)
        target=green[:,x0:x1] if color else red[:,x0:x1]
        ys,xs=np.nonzero(target)
        if len(ys)<5:
            raise ValueError("Too few pixels for candle "+str(j+1))
        top.append(int(ys.min()))
        bottom.append(int(ys.max()))
        col_density=target.sum(axis=0)
        if np.max(col_density)<3:
            raise ValueError("Cannot measure candle body "+str(j+1))
        # Thickest ink columns are primarily the rectangular body.
        thick=np.flatnonzero(col_density>=max(2,np.max(col_density)*0.65))
        core=target[:,thick]
        row_density=core.sum(axis=1)
        body_rows=np.flatnonzero(row_density>=max(2,len(thick)*0.55))
        if len(body_rows)==0:
            body_rows=np.flatnonzero(core.sum(axis=1)>0)
        body_top.append(int(body_rows.min()))
        body_bottom.append(int(body_rows.max()))
    # Normalization makes matching independent of image size and BTC price.
    low_y=min(top)
    high_y=max(bottom)
    scale=max(1,high_y-low_y)
    vec=np.stack([
        (np.array(top)-low_y)/scale,
        (np.array(body_top)-low_y)/scale,
        (np.array(body_bottom)-low_y)/scale,
        (np.array(bottom)-low_y)/scale
    ],axis=1)
    return vec,np.array(colors,dtype=int)

query_features,query_colors=measure_six(red,green)
color_text="".join("G" if z else "R" for z in query_colors)
print("Detected SIX sample candle colors:",color_text)
print("Measured shape features: 24 OHLC corner positions + upper/lower wick.")

# 2013-present native Bitstamp original hourly values, used by SRK PDFs.
df=pd.read_csv(OHLC)
df["time"]=pd.to_datetime(df["time"],format="mixed",utc=True)
df=df.sort_values("time").drop_duplicates("time").reset_index(drop=True)
df=df.set_index("time",drop=False)
m=pd.read_csv(MANIFEST)
expected_columns={"filename","window_first_utc","data_sha256"}
if not expected_columns.issubset(set(m.columns)):
    raise RuntimeError("SRK manifest columns changed. Check source export.")

# On original 36-candle PDF, central 60% is 7.2...28.8 candle widths.
# Candle centers 7..28 are inside it. Any six-candle matching window
# must fit completely there: starting indexes 7..23 inclusive.
CANDLES=36
CANDLES_TO_MATCH=6
CENTRAL_FIRST=7
CENTRAL_LAST=28
STARTS=range(CENTRAL_FIRST,CENTRAL_LAST-CANDLES_TO_MATCH+2)
assert len(list(STARTS))==17

def candidate_features(window):
    # Pixel-space counterpart to sample; y increases downward.
    high=window.high.to_numpy(dtype=float)
    low=window.low.to_numpy(dtype=float)
    op=window.open.to_numpy(dtype=float)
    cl=window.close.to_numpy(dtype=float)
    pmax=float(np.max(high))
    pmin=float(np.min(low))
    scale=pmax-pmin
    if scale<=0: return None,None
    top=(pmax-high)/scale
    body_t=(pmax-np.maximum(op,cl))/scale
    body_b=(pmax-np.minimum(op,cl))/scale
    bottom=(pmax-low)/scale
    shape=np.stack([top,body_t,body_b,bottom],axis=1)
    colors=(cl>=op).astype(int)
    return shape,colors

# Supports the ungrouped original root and all ten SRK_PART_* folders.
def source_pdf_path(filename):
    direct=ORIGINALS/filename
    if direct.is_file(): return direct
    number=int(re.fullmatch(r"SRK(\\d+)\\.pdf",filename,re.IGNORECASE).group(1))
    part=min(10,(number-1)//1000+1)
    match=list(ORIGINALS.glob(f"SRK_PART_{part:02d}_*/{filename}"))
    if len(match)==1: return match[0]
    return direct

results=[]
skipped=0
for _,row in m.iterrows():
    pdf_name=str(row["filename"])
    pdf_path=source_pdf_path(pdf_name)
    if not pdf_path.is_file():
        skipped+=1
        continue
    start_time=pd.to_datetime(
        row["window_first_utc"],format="mixed",utc=True
    )
    times=pd.date_range(start_time,periods=36,freq="h")
    if not times.isin(df.index).all():
        skipped+=1
        continue
    block=df.loc[times]
    if len(block)!=36:
        skipped+=1
        continue
    for i in STARTS:
        cand=block.iloc[i:i+6]
        features,colors=candidate_features(cand)
        if features is None: continue
        # Compare 24 body corners: top/bottom repeated for left+right.
        # These 24 values correspond to four body vertices for each of 6 candles.
        qbody=np.repeat(query_features[:,1:3],2,axis=1)
        cbody=np.repeat(features[:,1:3],2,axis=1)
        body_error=np.mean(np.abs(qbody-cbody))
        wick_error=np.mean(np.abs(query_features[:,[0,3]]-features[:,[0,3]]))
        color_disagreement=np.mean(query_colors!=colors)
        shape_error=0.70*body_error+0.30*wick_error
        # This is a heuristic SHAPE SIMILARITY percentage, NOT an
        # independently validated predictive/market accuracy percentage.
        similarity=max(0.0,min(100.0,
            100.0*(1.0-1.5*shape_error-0.25*color_disagreement)))
        results.append({
            "source_pdf":pdf_name,
            "srk_pattern_number":int(str(pdf_name)[3:-4]),
            "position_in_36":i+1,
            "first_candle_utc":str(cand.time.iloc[0]),
            "last_candle_utc":str(cand.time.iloc[-1]),
            "sample_color_code":color_text,
            "matched_color_code":"".join("G" if x else "R" for x in colors),
            "matching_color_candles":int(np.sum(query_colors==colors)),
            "body_24_corners_shape_error":float(body_error),
            "upper_lower_wick_error":float(wick_error),
            "shape_similarity_percent":float(round(similarity,2))
        })

if not results:
    raise RuntimeError("No complete historical six-candle matches found.")
ranking=pd.DataFrame(results).sort_values(
    ["shape_similarity_percent","matching_color_candles"],
    ascending=[False,False]
).head(10).reset_index(drop=True)
ranking.insert(0,"rank",np.arange(1,len(ranking)+1))
ranking.to_csv(DEST/"TOP10_RESULTS.csv",index=False)

# Original PDF coordinate system, before page-wide 180-degree drawing transform.
PDF_W,PDF_H=1100,520
CHART_X0,CHART_X1=78,1025
CHART_Y0,CHART_Y1=92,420
def preview_arrow(original_pdf,at_index,rank):
    doc=fitz.open(str(original_pdf))
    if len(doc)!=1:
        raise ValueError("Expected one page per SRK PDF")
    page=doc[0]
    zoom=2.0
    pix=page.get_pixmap(matrix=fitz.Matrix(zoom,zoom),alpha=False)
    rgb=np.frombuffer(pix.samples,dtype=np.uint8).reshape(
        pix.height,pix.width,pix.n
    )[:,:,:3].copy()
    bgr=cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR)
    # Source PDF content was rotated 180°, so original X is mirrored.
    xs=[CHART_X0+(j+0.5)*(CHART_X1-CHART_X0)/36
        for j in range(at_index,at_index+6)]
    visible_x=[int((PDF_W-x)*zoom) for x in xs]
    midpoint=int(np.mean(visible_x))
    xa=max(0,min(visible_x)-15)
    xb=min(bgr.shape[1],max(visible_x)+15)
    region=bgr[int(CHART_Y0*zoom):int(CHART_Y1*zoom),xa:xb]
    mr,mg=colored_masks(region)
    mask=mr|mg
    ys,_=np.nonzero(mask)
    if len(ys):
        # Image top origin after 180° rotation: y_screen = y_original.
        wick_visual_top=int(CHART_Y0*zoom)+int(ys.min())
    else:
        wick_visual_top=int(CHART_Y0*zoom)+40
    offset=int(round(3/25.4*72*zoom)) # exactly 3 mm in rendered units
    tip_y=max(15,wick_visual_top-offset)
    # One arrow per 6-candle pattern, on COPIED PNG ONLY.
    cv2.arrowedLine(
        bgr,(midpoint,max(5,tip_y-45)),(midpoint,tip_y),
        (20,90,230),thickness=5,tipLength=0.28
    )
    # Do not add any other annotation to the page/image.
    outfile=DEST/f"TOP{rank:02d}_{original_pdf.stem}_6C.png"
    if not cv2.imwrite(str(outfile),bgr):
        raise IOError("Could not write "+str(outfile))
    doc.close()
    return outfile

images=[]
for _,item in ranking.iterrows():
    out=preview_arrow(
        source_pdf_path(item.source_pdf),
        int(item.position_in_36)-1,
        int(item["rank"])
    )
    images.append(out)
    print(
        f"TOP {int(item['rank'])}: {item.source_pdf}, "
        f"candles {int(item.position_in_36)}-{int(item.position_in_36)+5}, "
        f"VISUAL SHAPE SIMILARITY {item.shape_similarity_percent:.2f}%"
    )

zip_path=DEST/"TOP10_FOR_PHONE_GALLERY.zip"
with zipfile.ZipFile(zip_path,"w",compression=zipfile.ZIP_DEFLATED) as archive:
    for p in images:
        archive.write(p,arcname=p.name)
    archive.write(DEST/"TOP10_RESULTS.csv",arcname="TOP10_RESULTS.csv")

print("\nSample visual features:",query_features.round(3))
print("Scanned SRK pages:",len(m),"missing source pages:",skipped)
print("Compared six-candle windows:",len(results))
print("Original PDFs were not edited.")
print("Drive output:",DEST)
print("ZIP for phone:",zip_path)
print("For Android Gallery, download/unzip images from Drive; Colab cannot silently write to the phone Gallery.")
display(ranking[["rank","source_pdf","position_in_36","shape_similarity_percent",
                 "matching_color_candles","first_candle_utc"]])
display(Image(filename=str(images[0]),width=850))
