#!/usr/bin/env python3
from __future__ import annotations
import argparse, functools, json, subprocess
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parent
W,H=1080,1920
RENDER_FPS=30
OUTPUT_FPS=60
OVERLAY_OPACITY=.30
SERIF='/usr/share/fonts/truetype/noto/NotoSerifDisplay-Black.ttf'
SANS='/usr/share/fonts/truetype/noto/NotoSansDisplay-CondensedBlack.ttf'
if not Path(SERIF).exists(): SERIF='/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf'
if not Path(SANS).exists(): SANS='/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf'
PALETTES=[((10,8,12),(245,238,205)),((242,248,48),(14,8,18)),((32,3,70),(205,255,47)),((255,53,51),(13,10,16)),((10,8,15),(239,30,155)),((235,232,203),(26,5,61)),((77,8,230),(239,247,70)),((14,12,15),(252,75,36))]
STYLE_NAMES=['Godard full-bleed serif impact','counter-scrolling text wall','upright vertical conveyor','full-height word emphasis','stepped horizontal slices','rectilinear outline echoes','hard typographic shutters','high-density type barrage','upright column poster grid','chromatic axial pulse','upright checkerboard matrix','orthogonal serif-sans wipe','stuttered straight zoom','final full-frame impact']
PHRASES=[
'MY VALUES LEFT ON THE LAST TRAIN','EVERYONE STARES THEN LOOKS AWAY','YOU ASK WHETHER I WANT OUT','YOU SAY YOU WOULD NOT STOP ME','THIS WORLD MAKES THE FALL FEEL LOGICAL','NORMAL IS PRAISED LIKE A LAW','DEVIANCE IS FINE UNTIL IT HAS MY FACE','YOU HOLD THE REASONS I KEEP HIDDEN','I AM BENDING MY HEART WILL NOT SLOW','IT HURTS I WANT TO VANISH','STOP AIMING EVERYTHING AT MY HEAD','WHEN PAIN GETS THIS LOUD DEATH SOUNDS SIMPLE','EVEN THEN I CANNOT MAKE MYSELF MOVE','MY BODY LOCKS BEFORE THE EDGE','LIVE LEAVE THE WORDS COLLIDE','MY SKIN IS SCREAMING BEFORE I CAN','LET ME MAKE SOME NOISE AT LEAST','YOUR VERSION OF NORMAL MADE THE FIRST WOUND','YOUR GOOD DEEDS MADE THE NEXT ONE','THE LOVE YOU TAKE LEAVES ITS MARK','WHAT YOU PRAISE KEEPS PUSHING ME DOWN','I WANT TO EMPTY EVERYTHING OUT','I WANT TO TASTE PROOF I AM STILL HERE','I WANT TO TEST WHETHER I EVER LIVED','I WAS HERE I KNOW I WAS HERE','SOME SONG TOLD ME LIFE HAD AN ANSWER','HOPE DEATH WEAKNESS EVERYBODY PREACHES','MAYBE EVERY ANSWER IS JUST SOMEONES EGO','SO I STAND HERE AND SING ALONE','BAD DOG','DO NOT CRY OVER ME','EVEN MY BODY IS TIRED OF STAYING','YOU LOOK SO MUCH HAPPIER FROM THERE','YOUR PITY MAKES SOMETHING VICIOUS IN ME','BODY AND MIND KEEP COMING APART','I KEEP SHOUTING TOWARD THE EXIT','SOMEHOW THE RUIN STILL LOOKS BEAUTIFUL','MY VALUES BREAK OPEN IN EVERY DIRECTION','EVERYTHING LEFT BEHIND TURNS RED','YOU DID NOT PULL THE TRIGGER','I ONLY WANT THE WEIGHT TO REACH YOU','YOUR NORMALITY IS WHERE THIS BEGAN','YOUR KINDNESS CAN STILL BECOME A WEAPON','YOUR LOVE CAN STILL BECOME A WOUND','WHAT YOU WORSHIP CAN STILL DESTROY ME','SAY IT AGAIN CALL IT NORMAL','SAY IT AGAIN CALL IT GOOD','SAY IT AGAIN CALL IT LOVE','SAY IT AGAIN THEN LOOK AWAY','I AM STILL HERE UNDER ALL OF IT','MY BODY REFUSES THE END','MY MOUTH KEEPS MAKING SOUND','THE TRAIN KEEPS MOVING WITHOUT ME','EVERY WINDOW TURNS INTO A MIRROR','EVERY MIRROR ASKS THE SAME QUESTION','I WANT OUT I WANT IN I CANNOT TELL','THE BODY KNOWS BEFORE THE MIND DOES','I WAS ALIVE ENOUGH TO HURT','I WAS ALIVE ENOUGH TO SCREAM','I WAS ALIVE ENOUGH TO BE SEEN','NO ANSWERS LEFT ONLY THE VOICE','NO WORDS LEFT ONLY THE RHYTHM','LET THE SOUND KEEP GOING AFTER ME']

@functools.lru_cache(maxsize=1024)
def glyph(text,w,h,family='sans',outline=0):
    font=ImageFont.truetype(SERIF if family=='serif' else SANS,160)
    box=font.getbbox(text);pad=outline+5
    im=Image.new('L',(max(2,box[2]-box[0]+pad*2),max(2,box[3]-box[1]+pad*2)))
    ImageDraw.Draw(im).text((pad-box[0],pad-box[1]),text,font=font,fill=255)
    a=np.array(im)
    if outline:a=cv2.subtract(cv2.dilate(a,np.ones((outline*2+1,outline*2+1),np.uint8)),a)
    ys,xs=np.where(a>0)
    if not len(xs):return np.zeros((h,w),np.uint8)
    a=a[ys.min():ys.max()+1,xs.min():xs.max()+1]
    return cv2.resize(a,(max(1,w),max(1,h)),interpolation=cv2.INTER_LANCZOS4)

def paste(dst,src,x,y):
    sh,sw=src.shape[:2];x0,y0=max(0,x),max(0,y);x1,y1=min(dst.shape[1],x+sw),min(dst.shape[0],y+sh)
    if x1<=x0 or y1<=y0:return
    np.maximum(dst[y0:y1,x0:x1],src[y0-y:y1-y,x0-x:x1-x],out=dst[y0:y1,x0:x1])

def split_rows(text,max_rows=4):
    words=text.split()
    if len(words)<=2:return words
    rows=min(max_rows,max(2,round(len(words)/3)));target=sum(map(len,words))/rows
    out=[];cur=[];chars=0
    for i,w in enumerate(words):
        remaining=len(words)-i;rows_left=rows-len(out)
        if cur and chars+1+len(w)>target*1.18 and remaining>=rows_left:
            out.append(' '.join(cur));cur=[w];chars=len(w)
        else:
            cur.append(w);chars+=len(w)+(1 if chars else 0)
    if cur:out.append(' '.join(cur))
    while len(out)>max_rows:out[-2]+=' '+out[-1];out.pop()
    return out

@functools.lru_cache(maxsize=512)
def lockup(text,w=W,h=H,family='serif',outline=0):
    rows=split_rows(text);out=np.zeros((h,w),np.uint8);edges=np.rint(np.linspace(0,h,len(rows)+1)).astype(int)
    for line,y0,y1 in zip(rows,edges,edges[1:]):paste(out,glyph(line,w,max(1,int(y1-y0)-2),family,outline),0,int(y0))
    return out

@functools.lru_cache(maxsize=512)
def repeated_rows(text,rows,family='sans'):
    out=np.zeros((H,W),np.uint8);edges=np.rint(np.linspace(0,H,rows+1)).astype(int);phrase=(text+'  ')*3
    for _,(y0,y1) in enumerate(zip(edges,edges[1:])):paste(out,glyph(phrase,W,int(y1-y0),family),0,int(y0))
    return out

def transform(a,scale=1.0):
    if scale<1:scale=1
    if abs(scale-1)<1e-6:return a
    hh,ww=a.shape;M=np.array([[scale,0,(1-scale)*ww/2],[0,scale,(1-scale)*hh/2]],np.float32)
    return cv2.warpAffine(a,M,(ww,hh),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)

def mask_frame(text,style,u,n):
    out=np.zeros((H,W),np.uint8);step=min(9,int(u*10))
    if style in (0,13):out=transform(lockup(text,family='serif'),[1.30,1.18,1.08,1,1,1.055,1,1,1.03,1][step])
    elif style==1:
        rows=8;edges=np.rint(np.linspace(0,H,rows+1)).astype(int)
        for row,(y0,y1) in enumerate(zip(edges,edges[1:])):
            tw=1400;tile=glyph(text+'  ',tw,int(y1-y0),'sans');off=(int(u*1100)+row*151)*(1 if row%2 else -1)
            for j in range(-2,3):paste(out,tile,j*tw+(off%tw)-tw,int(y0))
    elif style==2:out=np.roll(repeated_rows(text,4,'serif'),-int(u*960)//4*4,axis=0)
    elif style==3:
        words=text.split();focus=(step//2)%max(1,len(words));rows=split_rows(text);edges=np.rint(np.linspace(0,H,len(rows)+1)).astype(int)
        for line,y0,y1 in zip(rows,edges,edges[1:]):
            fam='sans' if any(w in line for w in words[max(0,focus-1):focus+1]) else 'serif';paste(out,glyph(line,W,int(y1-y0),fam),0,int(y0))
    elif style==4:
        base=lockup(text,family='serif');offs=[0,132,-80,220,-154,56,-224,0]
        for r,y in enumerate(range(0,H,120)):out[y:y+120]=np.roll(base[y:y+120],offs[(r*3+step)%len(offs)],axis=1)
    elif style==5:
        out=lockup(text,family='sans',outline=2).copy()
        for i in range(1,5):
            z=max(.25,.88-i*.14+(step%3)*.035);ww,hh=round(W*z),round(H*z);paste(out,lockup(text,ww,hh,'sans',2 if i<4 else 0),(W-ww)//2,(H-hh)//2)
    elif style==6:
        a=lockup(text,family='serif');b=lockup(text,family='sans');edges=np.rint(np.linspace(0,W,5)).astype(int)
        for c,(x0,x1) in enumerate(zip(edges,edges[1:])):out[:,x0:x1]=(a if (c+step)%2 else b)[:,x0:x1]
    elif style==7:out=repeated_rows(text,[8,12,16,8,24,12,8,16,12,20][step],'sans' if step%2 else 'serif').copy()
    elif style==8:
        cols=[1,2,4,2,3,1,4,2,3,1][step];edges=np.rint(np.linspace(0,W,cols+1)).astype(int)
        for c,(x0,x1) in enumerate(zip(edges,edges[1:])):paste(out,lockup(text,int(x1-x0),H,'sans' if c%2 else 'serif'),int(x0),0)
    elif style==9:out=transform(lockup(text,family='serif'),[1,1.045,1.09,1,1.15,1.075,1,1.03,1.08,1][step])
    elif style==10:
        for r in range(4):
            for c in range(3):paste(out,lockup(text,W//3,H//4,'serif' if (r+c+step)%2 else 'sans'),c*W//3,r*H//4)
    elif style==11:
        a=lockup(text,family='sans');b=lockup(text,family='serif');out=b.copy();lim=int(H*u);out[:lim]=a[:lim]
        if step%2:out[:,W//2:]=a[:,W//2:]
    elif style==12:out=transform(lockup(text,family='serif'),[1.5,1.25,1.5,1.12,1.25,1,1.12,1,1.05,1][step])
    return out

class Footage:
    def __init__(self,files):self.files=files;self.caps={};self.state={}
    def frame(self,n,phrase_index):
        category=['er','pyres','ventilator'][phrase_index%3];choices=self.files[category];path=choices[(phrase_index//3)%len(choices)]
        if path not in self.caps:
            cap=cv2.VideoCapture(str(ROOT/path))
            if not cap.isOpened():raise RuntimeError('cannot read '+str(path))
            self.caps[path]=cap;self.state[path]=(-1,None)
        cap=self.caps[path];fps=cap.get(cv2.CAP_PROP_FPS) or 30;count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));dur=count/fps
        t=((n/RENDER_FPS)*.83+(phrase_index*2.7))%max(.1,dur-.05);target=int(t*fps);lastframe,lastimage=self.state[path]
        if target<lastframe or target-lastframe>max(6,int(fps*.35)):
            cap.set(cv2.CAP_PROP_POS_FRAMES,target);lastframe=target-1;lastimage=None
        while lastframe<target:
            ok,lastimage=cap.read();lastframe+=1
            if not ok:
                cap.set(cv2.CAP_PROP_POS_FRAMES,0);lastframe=-1;lastimage=None;ok,lastimage=cap.read();lastframe=0
                if not ok:raise RuntimeError('read failed '+str(path))
        self.state[path]=(lastframe,lastimage);a=lastimage
        if a is None:raise RuntimeError('empty frame '+str(path))
        if a.shape[:2]!=(H,W):a=cv2.resize(a,(W,H),interpolation=cv2.INTER_LANCZOS4)
        return cv2.cvtColor(a,cv2.COLOR_BGR2RGB)
    def close(self):
        for c in self.caps.values():c.release()

def compose(n,total_frames,footage):
    pos=n/max(1,total_frames);phrase_index=min(len(PHRASES)-1,int(pos*len(PHRASES)));phrase_start=phrase_index/len(PHRASES);phrase_end=(phrase_index+1)/len(PHRASES);u=(pos-phrase_start)/(phrase_end-phrase_start)
    style=phrase_index%14;text=PHRASES[phrase_index];local=int(u*240);u2=(local//2*2)/239 if style in (4,9,12) else u
    mask=mask_frame(text,style,min(1,u2),n);accent=int(u*16);bg,fg=PALETTES[(style+phrase_index+accent//2)%len(PALETTES)];bg=np.array(bg,np.float32);fg=np.array(fg,np.float32)
    alpha=mask.astype(np.float32)[:,:,None]/255;frame=bg*(1-alpha)+fg*alpha
    if style==9:
        off=[14,24,10,34][(accent//2)%4]
        for ch in (0,2):
            sh=np.roll(mask,off*(1 if ch==0 else -1),axis=1).astype(np.float32)/255;frame[:,:,ch]=bg[ch]*(1-sh)+fg[ch]*sh
    if style==10:
        for r in range(4):
            for c in range(3):
                if (r+c+accent//2)%2:frame[r*H//4:(r+1)*H//4,c*W//3:(c+1)*W//3]=255-frame[r*H//4:(r+1)*H//4,c*W//3:(c+1)*W//3]
    if style in (0,4,6,9,12) and accent%8 in (0,1):frame=255-frame
    src=footage.frame(n,phrase_index).astype(np.float32)
    return np.clip(frame*(1-OVERLAY_OPACITY)+src*OVERLAY_OPACITY,0,255).astype(np.uint8)

def render(manifest,output):
    audio=ROOT/manifest['audio'];duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nk=1:nw=1',str(audio)],text=True).strip());total_frames=round(duration*RENDER_FPS);ft=Footage(manifest['footage'])
    temp=ROOT/'output'/'picture30.mp4';temp.parent.mkdir(exist_ok=True)
    cmd=['ffmpeg','-y','-hide_banner','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(RENDER_FPS),'-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','19','-maxrate','14M','-bufsize','28M','-profile:v','high','-pix_fmt','yuv420p','-movflags','+faststart',str(temp)]
    p=subprocess.Popen(cmd,stdin=subprocess.PIPE)
    try:
        for n in range(total_frames):
            p.stdin.write(compose(n,total_frames,ft).tobytes())
            if n%300==0:print('render',n,'/',total_frames,flush=True)
        p.stdin.close();rc=p.wait()
        if rc:raise RuntimeError('picture encode failed')
    finally:ft.close()
    final_frames=round(duration*OUTPUT_FPS)
    cmd=['ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(temp),'-i',str(audio),'-map','0:v:0','-map','1:a:0','-vf','fps=60,setsar=1,format=yuv420p','-frames:v',str(final_frames),'-c:v','libx264','-preset','fast','-crf','19','-maxrate','16M','-bufsize','32M','-profile:v','high','-level:v','4.2','-c:a','aac','-b:a','256k','-ar','48000','-ac','2','-shortest','-movflags','+faststart',str(output)]
    subprocess.run(cmd,check=True)
    data=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-show_streams','-show_format','-of','json',str(output)]));(ROOT/'qc').mkdir(exist_ok=True);(ROOT/'qc'/'ffprobe.json').write_text(json.dumps(data,indent=2))
    v=next(s for s in data['streams'] if s['codec_type']=='video');a=next(s for s in data['streams'] if s['codec_type']=='audio')
    assert (v['width'],v['height'])==(W,H);assert v['codec_name']=='h264';assert v['avg_frame_rate']=='60/1';assert a['codec_name']=='aac';assert a['sample_rate']=='48000';assert abs(float(data['format']['duration'])-duration)<.05
    subprocess.run(['ffmpeg','-v','error','-i',str(output),'-f','null','-'],check=True);print('VERIFIED',output,duration)

def preview(manifest):
    ft=Footage(manifest['footage']);board=Image.new('RGB',(5*216,3*410),(20,20,20));duration=350.946;total=round(duration*RENDER_FPS)
    for i in range(14):
        n=round((i+.5)/len(PHRASES)*total);a=Image.fromarray(compose(n,total,ft)).resize((216,384),Image.Resampling.LANCZOS);x=i%5*216;y=i//5*410;board.paste(a,(x,y));ImageDraw.Draw(board).text((x+4,y+388),STYLE_NAMES[i][:23],fill='white')
    ft.close();(ROOT/'qc').mkdir(exist_ok=True);board.save(ROOT/'qc'/'typography_proof.jpg',quality=92)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--manifest',type=Path,default=ROOT/'manifest.json');ap.add_argument('--output',type=Path,default=ROOT/'output'/'dogdog_covid_typography_reel.mp4');ap.add_argument('--preview',action='store_true');args=ap.parse_args();m=json.loads(args.manifest.read_text());preview(m) if args.preview else render(m,args.output)
