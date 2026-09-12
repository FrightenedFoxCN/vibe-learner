"""Synthetic PNG authoring; gold is exported separately and never passed to detector."""
import hashlib, io, json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
FONT=Path('/System/Library/Fonts/Supplemental/Arial.ttf')

def build_fixtures(directory,include_diagnostic=False):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    rows=[]
    specs=[
      ('equation-upper','text','Find the exact equation 7x + 2 = 30.', [('7x + 2 = 30',55,42,28),('Check the result.',60,250,18)],None,0),
      ('equation-lower','text','Find the exact equation 5y - 8 = 17.', [('Practice',50,30,25),('5y - 8 = 17',330,265,26)],None,1),
      ('equation-small','text','Find the exact equation 9a + 1 = 46.', [('9a + 1 = 46',270,170,16),('Do not mark this heading',50,40,27)],None,0),
      ('similar-rows','text','Find only 3x + 4 = 19, not 3x + 4 = 18.', [('3x + 4 = 18',70,70,27),('3x + 4 = 19',70,145,27),('3x - 4 = 19',70,230,27)],None,1),
      ('right-column','text','Find the equation on the right: 8b - 6 = 10.', [('8b - 6 = 11',35,130,24),('8b - 6 = 10',350,130,24)],None,1),
      ('blue-circle','geometry','Locate the entire blue circle, excluding the other shapes.', [], [('ellipse',(70,75,190,195),'blue'),('rectangle',(310,60,430,145),'red'),('triangle',(425,205,545,310),'green')],0),
      ('green-triangle','geometry','Locate the entire green triangle.', [('Shapes',35,20,22)], [('ellipse',(60,180,150,270),'orange'),('triangle',(330,70,505,250),'green')],1),
      ('highest-bar','chart','Locate only the tallest colored bar, excluding labels and axes.', [('A',110,310,18),('B',275,310,18),('C',435,310,18)], [('rectangle',(90,205,150,300),'red'),('rectangle',(255,70,315,300),'blue'),('rectangle',(415,155,475,300),'green')],1),
      ('wide-orange','geometry','Locate the wide orange rectangle, not the narrow orange rectangle.', [], [('rectangle',(45,50,105,250),'orange'),('rectangle',(230,160,535,225),'orange')],1),
      ('missing-equation','negative','Find the exact equation 4z + 9 = 21; abstain if absent.', [('4z + 9 = 20',70,70,28),('4z - 9 = 21',70,210,28)],None,None),
      ('duplicate-equation','ambiguous','Find 6q + 1 = 25. If more than one region matches and no position is specified, abstain as ambiguous.', [('6q + 1 = 25',40,65,26),('6q + 1 = 25',345,240,26)],None,None),
      ('missing-shape','negative','Locate a purple triangle. Abstain if absent.', [], [('ellipse',(65,70,190,195),'purple'),('triangle',(320,140,480,290),'green')],None),
    ]
    if include_diagnostic:specs.append(('gray-circle','geometry','Locate the entire gray circle. If a target is visible but no candidate covers it, say unlocalized, not absent.',[],[('ellipse',(230,85,390,245),'gray')],0))
    for ident,kind,request,texts,shapes,target_index in specs:
        im=Image.new('RGB',(640,360),'white');draw=ImageDraw.Draw(im); boxes=[]
        for text,x,y,size in texts:
            font=ImageFont.truetype(str(FONT),size);draw.text((x,y),text,font=font,fill='black');boxes.append(list(draw.textbbox((x,y),text,font=font)))
        shape_boxes=[]
        for typ,box,color in shapes or []:
            if typ=='triangle':
                x0,y0,x1,y1=box;draw.polygon([(int((x0+x1)/2),y0),(x0,y1),(x1,y1)],fill=color)
            else:getattr(draw,typ)(box,fill=color)
            shape_boxes.append([box[0],box[1],box[2]+1,box[3]+1])
        buf=io.BytesIO();im.save(buf,format='PNG',optimize=True);png=buf.getvalue()
        if len(png)>32768:raise ValueError('fixture_png_budget')
        path=directory/(ident+'.png');path.write_bytes(png)
        target=(shape_boxes if shapes else boxes)[target_index] if target_index is not None else None
        gold={'expected':'ambiguous' if kind=='ambiguous' else 'absent' if kind=='negative' else 'found','target_px':target,'width':640,'height':360,'object_class':kind,'minimum_iou':.5,'minimum_coverage':.8}
        rows.append(dict(id=ident,family=ident,lane=kind,split='development',provenance='synthetic-authored',request=request,source=json.dumps({'path':str(path.resolve()),'sha256':hashlib.sha256(png).hexdigest()}),gold=json.dumps(gold),rubric='visual-grounding-v1'))
    return rows
