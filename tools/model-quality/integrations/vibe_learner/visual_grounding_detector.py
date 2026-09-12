"""Image-only OCR and saturated-pixel component proposals. No fixture/gold import."""
import csv,io,subprocess,time
import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageFont
TESSERACT='/opt/homebrew/bin/tesseract'

def propose(png):
    start=time.monotonic()
    proc=subprocess.run([TESSERACT,'stdin','stdout','-l','eng','--psm','11','tsv'],input=png,capture_output=True,timeout=25,check=True)
    groups={}
    for row in csv.DictReader(io.StringIO(proc.stdout.decode()),delimiter='\t'):
        if row['level']!='5' or not row['text'].strip() or float(row['conf'])<0:continue
        key=tuple(row[k] for k in ('block_num','par_num','line_num'));groups.setdefault(key,[]).append(row)
    proposals=[]
    for words in groups.values():
        x=min(int(w['left']) for w in words);y=min(int(w['top']) for w in words)
        r=max(int(w['left'])+int(w['width']) for w in words);b=max(int(w['top'])+int(w['height']) for w in words)
        proposals.append({'kind':'ocr_line','text':' '.join(w['text'] for w in words),'box_px':[x,y,r,b]})
    rgb=np.array(Image.open(io.BytesIO(png)).convert('RGB'));hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
    mask=(hsv[:,:,1]>80).astype('uint8')
    count,_,stats,_=cv2.connectedComponentsWithStats(mask,8)
    for x,y,w,h,area in stats[1:]:
        if area>=100 and w>=12 and h>=12:proposals.append({'kind':'saturated_pixel_component','text':'','box_px':[int(x),int(y),int(x+w),int(y+h)]})
    proposals=sorted(proposals,key=lambda p:(p['box_px'][1],p['box_px'][0],p['kind']))
    for n,p in enumerate(proposals,1):p['id']=n
    if len(proposals)>40:raise ValueError('proposal_count_exceeded')
    return proposals,{'method':'tesseract-psm11-lines+opencv-saturation-components-v1','seconds':time.monotonic()-start,'tesseract_version':subprocess.check_output([TESSERACT,'--version']).decode().splitlines()[0]}

def mark(png,proposals,max_bytes=32768):
    im=Image.open(io.BytesIO(png)).convert('RGB');draw=ImageDraw.Draw(im)
    font=ImageFont.load_default(size=17)
    for p in proposals:
        x,y,r,b=p['box_px'];draw.rectangle((x,y,r-1,b-1),outline='#a000aa',width=2)
        label=str(p['id']);tx=x;ty=max(0,y-21);box=draw.textbbox((tx,ty),label,font=font)
        draw.rectangle((box[0]-2,box[1]-2,box[2]+2,box[3]+2),fill='white');draw.text((tx,ty),label,font=font,fill='#a000aa')
    out=io.BytesIO();im.save(out,format='PNG',optimize=True)
    if len(out.getvalue())>max_bytes:
        out=io.BytesIO();im.quantize(colors=32,dither=Image.Dither.NONE).save(out,format='PNG',optimize=True)
    if len(out.getvalue())>max_bytes:raise ValueError('marked_png_budget')
    return out.getvalue()
