#!/usr/bin/env python3
from __future__ import annotations
import math, os, shutil, subprocess, sys
from dataclasses import dataclass
from pathlib import Path
import cv2, numpy as np

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'reel_build'/'sources'; OUT=ROOT/'reel_build'/'output'; TMP=ROOT/'reel_build'/'tmp'
for p in (SRC,OUT,TMP): p.mkdir(parents=True,exist_ok=True)
W,H,FPS,DUR=1080,1920,30,15.0
N=int(FPS*DUR); AUDIO_START=268.0
SONG='https://youtu.be/mGGjRtSZrMo?si=2_IvB-aTQSEdrrld'

@dataclass(frozen=True)
class Spec:
    key:str; source:str; start:float; fx:float=.5; fy:float=.5; zoom:float=1.05; crop_top:float=0.; crop_bottom:float=0.

SPECS={
'castle':Spec('castle','https://www.youtube.com/watch?v=85d6sxqJcQ0',55,.52,.48,1.06),
'medford':Spec('medford','ytsearch1:Everett Street Medford Massachusetts driving tour',0,.52,.55,1.17),
'mclean':Spec('mclean','https://www.youtube.com/watch?v=5a-_QGRnhAU',28,.48,.48,1.08),
'mgh':Spec('mgh','ytsearch1:Massachusetts General Hospital Fruit Street entrance Boston walking tour',0,.50,.46,1.15),
'harvard':Spec('harvard','https://www.youtube.com/watch?v=eVcOSG3X2mk',0,.50,.48,1.12),
'jfk':Spec('jfk','ytsearch1:MBTA Red Line JFK UMass station train arriving',0,.50,.48,1.12),
'shinji':Spec('shinji','ytsearch1:Evangelion Shinji alone train scene no subtitles',0,.50,.42,1.20,.05,.20),
'separated':Spec('separated','ytsearch1:Your Name Taki Mitsuha twilight separated time scene no subtitles',0,.50,.45,1.16,.03,.17),
'silhouette':Spec('silhouette','ytsearch1:lonely person silhouette window cinematic no copyright',0,.50,.50,1.12,.04,.12),
}

@dataclass(frozen=True)
class Shot:
    frames:int; key:str; offset:float=0.; speed:float=1.; palette:str='cyan'; mode:str='full'; secondary:str|None=None; glitch:int=0; stutter:int=0

# 450 frames exactly. No title/text frames: the user did not specify a title.
SHOTS=[
Shot(30,'castle',0,.75,'cyan','full',None,1,0),
Shot(36,'shinji',1,.72,'mono','pip','castle',2,2),
Shot(30,'medford',1,.90,'cyan','full',None,1,0),
Shot(30,'mclean',1,.70,'washed','full','silhouette',1,0),
Shot(30,'mgh',1,.82,'washed','full',None,2,0),
Shot(24,'harvard',1,.75,'cyan','full',None,3,2),
Shot(24,'jfk',1,.78,'mono','full',None,3,2),
Shot(42,'separated',1,.62,'red','full','silhouette',2,2),
Shot(30,'shinji',3,.55,'mono','full',None,3,3),
Shot(30,'medford',3,.95,'cyan','pip','mgh',2,0),
Shot(30,'castle',3,.72,'cyan','full','silhouette',2,0),
Shot(18,'harvard',3,1.05,'mono','full',None,4,3),
Shot(18,'jfk',3,1.08,'cyan','full',None,4,3),
Shot(18,'separated',3,.88,'red','pip','shinji',4,2),
Shot(30,'castle',5,.62,'washed','full','separated',3,0),
]
assert sum(s.frames for s in SHOTS)==N

def run(cmd,check=True):
    print('+',' '.join(map(str,cmd)),flush=True); return subprocess.run(cmd,cwd=ROOT,check=check)

def resolve(spec:Spec)->str:
    if spec.source.startswith('http'): return spec.source
    cp=subprocess.run(['yt-dlp','--quiet','--no-warnings','--skip-download','--print','%(webpage_url)s',spec.source],cwd=ROOT,text=True,stdout=subprocess.PIPE,check=True)
    return cp.stdout.strip().splitlines()[0]

def dl_video(spec:Spec):
    dst=SRC/f'{spec.key}.mp4'
    if dst.exists() and dst.stat().st_size>100000:return
    url=resolve(spec); end=spec.start+10
    run(['yt-dlp','--no-warnings','--retries','5','--fragment-retries','5','--download-sections',f'*{spec.start:.3f}-{end:.3f}','--force-keyframes-at-cuts','-f','bv*[height<=1080]+ba/b[height<=1080]','--merge-output-format','mp4','-o',str(dst),url])

def dl_audio():
    dst=SRC/'track.m4a'
    if dst.exists() and dst.stat().st_size>100000:return dst
    run(['yt-dlp','--no-warnings','--retries','5','-f','bestaudio[ext=m4a]/bestaudio','-o',str(dst),SONG]); return dst

def crop(frame,s:Spec,phase=0.):
    h,w=frame.shape[:2]
    t=int(h*s.crop_top); b=int(h*s.crop_bottom); frame=frame[t:max(t+8,h-b),:]; h,w=frame.shape[:2]
    aspect=W/H
    if w/h>=aspect: cw=int(h*aspect); ch=h
    else: cw=w; ch=int(w/aspect)
    z=max(1,s.zoom*(1+.018*phase)); cw=max(8,int(cw/z)); ch=max(8,int(ch/z))
    cx=int(np.clip(s.fx,0,1)*w); cy=int(np.clip(s.fy,0,1)*h)
    x=max(0,min(w-cw,cx-cw//2)); y=max(0,min(h-ch,cy-ch//2))
    return cv2.resize(frame[y:y+ch,x:x+cw],(W,H),interpolation=cv2.INTER_LANCZOS4)

def grade(f,p):
    x=f.astype(np.float32)/255.; soft=cv2.GaussianBlur(x,(0,0),1.2); x=.72*x+.28*soft
    g=cv2.cvtColor(x,cv2.COLOR_BGR2GRAY)
    if p=='red': x=np.dstack((g*.10,g*.12,g*.86))
    elif p=='mono': x=np.dstack((g*.72,g*.88,g*.78))
    elif p=='washed': x=.18*x+.82*np.dstack((g,g,g)); x*=np.array([.95,1.0,.90])
    else: x*=np.array([1.08,.93,.58]); x=(x-.39)*1.22+.27
    lum=cv2.cvtColor(np.clip(x,0,1).astype(np.float32),cv2.COLOR_BGR2GRAY); hi=np.clip((lum-.58)*3.2,0,1); glow=cv2.GaussianBlur(hi,(0,0),9); x+=glow[...,None]*.18
    yy,xx=np.ogrid[:H,:W]; vig=1-.38*(((xx-W/2)/(W/2))**2+((yy-H/2)/(H/2))**2); x*=np.clip(vig,.48,1)[...,None]
    return np.clip(x*255,0,255).astype(np.uint8)

def rgb_tear(f,amt):
    if amt<=0:return f
    o=f.copy(); o[:,:,0]=np.roll(f[:,:,0],-amt,1); o[:,:,2]=np.roll(f[:,:,2],amt,1); return o

def glitch(f,frame_idx,intensity):
    if intensity<=0:return f
    rng=np.random.default_rng(7703+frame_idx*131)
    out=f.copy(); local=frame_idx%15
    # digital corruption is clustered, not continuous
    if local not in (0,1,2,7,8) and intensity<4:return out
    bands=1+intensity
    for _ in range(bands):
        y=int(rng.integers(60,H-120)); hh=int(rng.integers(12,50+intensity*18)); shift=int(rng.integers(-50,51)*(0.55+.25*intensity)); out[y:y+hh]=np.roll(out[y:y+hh],shift,1)
    if local in (0,1): out=rgb_tear(out,3+intensity*3)
    if intensity>=3 and local in (1,7):
        # macroblock mosaic resembling a corrupt I-frame
        y=int(rng.integers(180,H-420)); x=int(rng.integers(0,W-360)); h=int(rng.integers(120,300)); w=int(rng.integers(180,420)); roi=out[y:y+h,x:x+w]; small=cv2.resize(roi,(max(2,w//28),max(2,h//28)),interpolation=cv2.INTER_AREA); out[y:y+h,x:x+w]=cv2.resize(small,(w,h),interpolation=cv2.INTER_NEAREST)
    if intensity>=4 and local==2: out=cv2.bitwise_not(out)
    return out

class Reader:
    def __init__(self):self.cap={};self.fps={}
    def get(self,key,t):
        if key not in self.cap:
            c=cv2.VideoCapture(str(SRC/f'{key}.mp4')); self.cap[key]=c; self.fps[key]=c.get(cv2.CAP_PROP_FPS) or 30
        c=self.cap[key]; c.set(cv2.CAP_PROP_POS_MSEC,max(0,t)*1000); ok,f=c.read()
        if not ok: c.set(cv2.CAP_PROP_POS_FRAMES,0); ok,f=c.read()
        if not ok: raise RuntimeError(key)
        return f
    def close(self):
        for c in self.cap.values():c.release()

def render():
    for s in SPECS.values(): dl_video(s)
    audio=dl_audio(); out_raw=TMP/'visual.mp4'; writer=cv2.VideoWriter(str(out_raw),cv2.VideoWriter_fourcc(*'mp4v'),FPS,(W,H))
    r=Reader(); prev=None; gf=0
    for si,shot in enumerate(SHOTS):
        print('shot',si,shot.key,shot.frames,flush=True)
        for j in range(shot.frames):
            phase=j/max(1,shot.frames-1); idx=j
            if shot.stutter and j%9<shot.stutter: idx=max(0,j-(j%shot.stutter))
            t=shot.offset+(idx/FPS)*shot.speed
            f=crop(r.get(shot.key,t),SPECS[shot.key],phase); f=grade(f,shot.palette)
            # ghost previous scene for 2-4 frames
            if prev is not None and j<4: f=cv2.addWeighted(f,.62,prev,.38,0)
            if shot.secondary:
                sf=crop(r.get(shot.secondary,shot.offset+(j/FPS)*.55),SPECS[shot.secondary],phase); sf=grade(sf,'mono')
                if shot.mode=='pip':
                    sw,sh=520,720; sf=cv2.resize(sf,(sw,sh)); x=70 if si%2 else W-sw-70; y=230 if si%3 else 900; cv2.rectangle(f,(x-3,y-3),(x+sw+3,y+sh+3),(238,238,230),3); f[y:y+sh,x:x+sw]=sf
                else: f=cv2.addWeighted(f,.79,sf,.21,0)
            f=glitch(f,gf,shot.glitch)
            writer.write(f); prev=f.copy(); gf+=1
    r.close(); writer.release();
    final=OUT/'massachusetts_glitch_separation_reel.mp4'
    run(['ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(out_raw),'-ss',str(AUDIO_START),'-i',str(audio),'-t',str(DUR),'-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','slow','-crf','17','-pix_fmt','yuv420p','-r',str(FPS),'-c:a','aac','-b:a','256k','-ar','48000','-ac','2','-movflags','+faststart',str(final)])
    run(['ffmpeg','-v','error','-i',str(final),'-f','null','-'])
    run(['ffprobe','-v','error','-show_entries','format=duration,size:stream=codec_name,codec_type,width,height,r_frame_rate,nb_frames,sample_rate,channels','-of','json',str(final)])
    print('FINAL',final)
if __name__=='__main__':render()
