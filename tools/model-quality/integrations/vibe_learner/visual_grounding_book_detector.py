"""Book-image-only OCR and closed-contour layout baseline; not a learned detector.

No task/query/gold input. All bounded candidates are returned; geometry and text
remain separate kinds. Closed contour detection may fail for open/touching diagrams.
"""
import csv,io,subprocess,time
import cv2,numpy as np
from PIL import Image
from .visual_grounding_detector import TESSERACT

def iou(a,b):
    inter=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]));aa=(a[2]-a[0])*(a[3]-a[1]);bb=(b[2]-b[0])*(b[3]-b[1]);return inter/(aa+bb-inter)

def propose_book(png):
    start=time.monotonic();gray=np.array(Image.open(io.BytesIO(png)).convert('L'));height,width=gray.shape
    raw=subprocess.run([TESSERACT,'stdin','stdout','-l','eng','--psm','11','tsv'],input=png,capture_output=True,timeout=40,check=True)
    groups={}
    for row in csv.DictReader(io.StringIO(raw.stdout.decode()),delimiter='\t'):
        if row['level']!='5' or not row['text'].strip() or float(row['conf'])<0:continue
        groups.setdefault(tuple(row[k] for k in ('block_num','par_num','line_num')),[]).append(row)
    text=[]
    for words in groups.values():
        box=[min(int(w['left']) for w in words),min(int(w['top']) for w in words),max(int(w['left'])+int(w['width']) for w in words),max(int(w['top'])+int(w['height']) for w in words)]
        text.append({'kind':'ocr_text_line','text':' '.join(w['text'] for w in words),'box_px':box})
    _,binary=cv2.threshold(gray,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
    contours,_=cv2.findContours(binary,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE);geometry=[]
    for contour in contours:
        area=cv2.contourArea(contour);x,y,w,h=cv2.boundingRect(contour)
        if area<200 or w<20 or h<18 or w>.95*width or h>.8*height:continue
        approx=cv2.approxPolyDP(contour,.025*cv2.arcLength(contour,True),True);fill=area/(w*h)
        rectangle=len(approx)==4 and fill>.65
        curved=(len(approx)>=5 and area>1000 and w>=30 and h>=40 and fill>.45)
        if not(rectangle or curved):continue
        box=[max(0,x-2),max(0,y-2),min(width,x+w+2),min(height,y+h+2)]
        geometry.append({'kind':'closed_rectangle' if rectangle else 'closed_irregular_region','box_px':box,'contour_area':float(area),'contour_vertices':len(approx),'text':''})
    # Duplicate edges of the same closed boundary collapse deterministically to the outermost box.
    unique=[]
    for p in sorted(geometry,key=lambda p:-((p['box_px'][2]-p['box_px'][0])*(p['box_px'][3]-p['box_px'][1]))):
        if not any(iou(p['box_px'],q['box_px'])>.9 for q in unique):unique.append(p)
    for p in unique:
        x,y,r,b=p['box_px'];p['text']=' '.join(t['text'] for t in text if x<=(t['box_px'][0]+t['box_px'][2])/2<=r and y<=(t['box_px'][1]+t['box_px'][3])/2<=b)[:500]
    result=sorted([*text,*unique],key=lambda p:(p['box_px'][1],p['box_px'][0],p['kind']))
    if len(result)>160:raise ValueError('book_proposal_limit_exceeded')
    for i,p in enumerate(result,1):p['id']=i
    return result,{'method':'tesseract-psm11+closed-contour-layout-v1','seconds':time.monotonic()-start,'full_ocr_lines':[t['text'] for t in text],'ocr_count':len(text),'geometry_count':len(unique),'tesseract_version':subprocess.check_output([TESSERACT,'--version']).decode().splitlines()[0],'limitations':'Image-processing baseline; not semantic segmentation or a paper reproduction; no query/gold filtering.'}
