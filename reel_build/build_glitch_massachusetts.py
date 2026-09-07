#!/usr/bin/env python3
from __future__ import annotations
import json, math, os, random, re, subprocess, sys, time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen
import cv2, numpy as np

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'reel_build'/'sources'; OUT=ROOT/'reel_build'/'output'; TMP=ROOT/'reel_build'/'tmp'
for p in (SRC,OUT,TMP): p.mkdir(parents=True,exist_ok=True)
W,H,FPS,DUR=1080,1920,30,15.0
N=int(FPS*DUR); AUDIO_START=268.0
SONG_ID='mGGjRtSZrMo'

# Dynamic instance list first, then known public fallbacks. Media is requested with local=true
# so the Invidious host proxies the bytes instead of exposing the GitHub runner to googlevideo.
INSTANCE_SEEDS=[
 'https://inv.nadeko.net','https://invidious.nerdvpn.de','https://invidious.f5.si',
 'https://yt.chocolatemoo53.com','https://invidious.tiekoetter.com',
 'https://invidious.jing.rocks','https://inv.us.projectsegfau.lt',
 'https://invidious.privacydev.net','https://yewtu.be'
]
_instances=None

def http_json(url,timeout=8):
    req=Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
    with urlopen(req,timeout=timeout) as r: return json.load(r)

def discover_instances():
    global _instances
    if _instances is not None:return _instances
    candidates=[]
    try:
        data=http_json('https://api.invidious.io/instances.json',10)
        for host,meta in data:
            if not isinstance(meta,dict):continue
            uri=meta.get('uri') or ('https://'+host)
            if str(uri).startswith('https://') and meta.get('api',True): candidates.append(str(uri).rstrip('/'))
    except Exception as e: print('instance list warning',repr(e),flush=True)
    candidates+=INSTANCE_SEEDS
    seen=[]
    for h in candidates:
        if h not in seen: seen.append(h)
    # Probe quickly and keep the first healthy API instances.
    healthy=[]
    for h in seen[:30]:
        try:
            d=http_json(h+'/api/v1/stats',4)
            if isinstance(d,dict):
                healthy.append(h); print('INVIDIOUS OK',h,flush=True)
                if len(healthy)>=8:break
        except Exception: pass
    if not healthy: raise RuntimeError('No usable public Invidious API instance')
    _instances=healthy; return healthy

def inv_json(path,timeout=12):
    last=None
    for host in discover_instances():
        try:return host,http_json(host+path,timeout)
        except Exception as e:last=e
    raise RuntimeError(f'Invidious API failed for {path}: {last!r}')

def parse_video_id(source):
    if source.startswith('ytsearch1:'):
        q=source.split(':',1)[1]
        host,data=inv_json('/api/v1/search?'+urlencode({'q':q,'type':'video','sort_by':'relevance'}),15)
        for item in data:
            vid=item.get('videoId')
            if vid:
                print('SEARCH',q,'=>',item.get('title'),vid,flush=True)
                return vid
        raise RuntimeError('No Invidious search result for '+q)
    m=re.search(r'(?:v=|youtu\.be/)([\w-]{11})',source)
    if not m: raise RuntimeError('Cannot parse video id '+source)
    return m.group(1)

def choose_stream(video_id,audio=False):
    last=None
    for host in discover_instances():
        try:
            info=http_json(host+f'/api/v1/videos/{video_id}?local=true',15)
            fmts=(info.get('adaptiveFormats') or [])+(info.get('formatStreams') or [])
            if audio:
                cand=[]
                for f in fmts:
                    typ=str(f.get('type','')); enc=str(f.get('encoding','')).lower()
                    if typ.startswith('audio/') or (not f.get('resolution') and ('mp4a' in typ or 'opus' in typ or enc in ('aac','opus'))):
                        cand.append(f)
                if not cand: raise RuntimeError('no audio streams')
                fmt=max(cand,key=lambda x:int(x.get('bitrate') or x.get('audioBitrate') or 0))
            else:
                cand=[]
                for f in fmts:
                    typ=str(f.get('type','')).lower(); enc=str(f.get('encoding','')).lower(); res=str(f.get('resolution') or f.get('qualityLabel') or '')
                    nums=re.findall(r'\d+',res); height=int(nums[0]) if nums else 0
                    is_video=('video/' in typ) or height>0
                    if is_video and height<=1080 and (('mp4' in typ) or f.get('container')=='mp4'):
                        cand.append((height,1 if ('avc' in typ or 'h264' in enc) else 0,int(f.get('bitrate') or 0),f))
                if not cand:
                    for f in info.get('formatStreams') or []:
                        nums=re.findall(r'\d+',str(f.get('resolution') or f.get('qualityLabel') or '')); height=int(nums[0]) if nums else 0
                        if height<=1080:cand.append((height,0,int(f.get('bitrate') or 0),f))
                if not cand:raise RuntimeError('no video streams')
                fmt=max(cand,key=lambda x:(x[0],x[1],x[2]))[3]
            itag=str(fmt.get('itag'))
            if not itag:raise RuntimeError('stream has no itag')
            print('STREAM',video_id,'host',host,'itag',itag,'label',fmt.get('qualityLabel') or fmt.get('resolution'),flush=True)
            return host+f'/latest_version?id={video_id}&itag={itag}&local=true'
        except Exception as e:last=e
    raise RuntimeError(f'No proxied stream for {video_id}: {last!r}')

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
 'shinji':Spec('shinji','ytsearch1:Evangelion Shinji alone train scene',0,.50,.42,1.20,.05,.20),
 'separated':Spec('separated','ytsearch1:Your Name Taki Mitsuha twilight scene',0,.50,.45,1.16,.03,.17),
 'silhouette':Spec('silhouette','ytsearch1:lonely person silhouette window cinematic short film',0,.50,.50,1.12,.04,.12),
}

@dataclass(frozen=True)
class Shot:
    frames:int; key:str; offset:float=0.; speed:float=1.; palette:str='cyan'; mode:str='full'; secondary:str|None=None; glitch:int=0; stutter:int=0

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
 Shot(30,'shinji',4,.48,'mono','full','separated',4,3),
 Shot(30,'castle',5,.62,'washed','full','separated',3,0),
]
assert sum(s.frames for s in SHOTS)==N

def run(cmd,check=True):
    print('+',' '.join(map(str,cmd)),flush=True); return subprocess.run(cmd,cwd=ROOT,check=check)

def dl_video(spec:Spec):
    dst=SRC/f'{spec.key}.mp4'
    if dst.exists() and dst.stat().st_size>100000:return
    vid=parse_video_id(spec.source); media=choose_stream(vid,False)
    # Fetch only the short useful window through the proxy, then normalize locally.
    run(['ffmpeg','-y','-nostdin','-hide_banner','-loglevel','warning','-rw_timeout','30000000','-ss',str(spec.start),'-i',media,'-t','10','-an','-vf','fps=30','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p',str(dst)])

def dl_audio():
    dst=SRC/'track.m4a'
    if dst.exists() and dst.stat().st_size>100000:return dst
    media=choose_stream(SONG_ID,True)
    run(['ffmpeg','-y','-nostdin','-hide_banner','-loglevel','warning','-rw_timeout','30000000','-ss',str(AUDIO_START),'-i',media,'-t',str(DUR),'-vn','-c:a','aac','-b:a','256k','-ar','48000','-ac','2',str(dst)])
    return dst

def crop(frame,s:Spec,phase=0.):
    h,w=frame.shape[:2]; t=int(h*s.crop_top); b=int(h*s.crop_bottom); frame=frame[t:max(t+8,h-b),:]; h,w=frame.shape[:2]
    aspect=W/H
    if w/h>=aspect:cw=int(h*aspect);ch=h
    else:cw=w;ch=int(w/aspect)
    z=max(1,s.zoom*(1+.018*phase));cw=max(8,int(cw/z));ch=max(8,int(ch/z))
    cx=int(np.clip(s.fx,0,1)*w);cy=int(np.clip(s.fy,0,1)*h);x=max(0,min(w-cw,cx-cw//2));y=max(0,min(h-ch,cy-ch//2))
    return cv2.resize(frame[y:y+ch,x:x+cw],(W,H),interpolation=cv2.INTER_LANCZOS4)

def grade(f,p):
    x=f.astype(np.float32)/255.; soft=cv2.GaussianBlur(x,(0,0),1.2);x=.72*x+.28*soft;g=cv2.cvtColor(x,cv2.COLOR_BGR2GRAY)
    if p=='red':x=np.dstack((g*.10,g*.12,g*.86))
    elif p=='mono':x=np.dstack((g*.72,g*.88,g*.78))
    elif p=='washed':x=.18*x+.82*np.dstack((g,g,g));x*=np.array([.95,1.0,.90])
    else:x*=np.array([1.08,.93,.58]);x=(x-.39)*1.22+.27
    lum=cv2.cvtColor(np.clip(x,0,1).astype(np.float32),cv2.COLOR_BGR2GRAY);hi=np.clip((lum-.58)*3.2,0,1);glow=cv2.GaussianBlur(hi,(0,0),9);x+=glow[...,None]*.18
    yy,xx=np.ogrid[:H,:W];vig=1-.38*(((xx-W/2)/(W/2))**2+((yy-H/2)/(H/2))**2);x*=np.clip(vig,.48,1)[...,None]
    return np.clip(x*255,0,255).astype(np.uint8)

def rgb_tear(f,amt):
    if amt<=0:return f
    o=f.copy();o[:,:,0]=np.roll(f[:,:,0],-amt,1);o[:,:,2]=np.roll(f[:,:,2],amt,1);return o

def glitch(f,frame_idx,intensity):
    if intensity<=0:return f
    rng=np.random.default_rng(7703+frame_idx*131);out=f.copy();local=frame_idx%15
    if local not in (0,1,2,7,8) and intensity<4:return out
    for _ in range(1+intensity):
        y=int(rng.integers(60,H-120));hh=int(rng.integers(12,50+intensity*18));shift=int(rng.integers(-50,51)*(0.55+.25*intensity));out[y:y+hh]=np.roll(out[y:y+hh],shift,1)
    if local in (0,1):out=rgb_tear(out,3+intensity*3)
    if intensity>=3 and local in (1,7):
        y=int(rng.integers(180,H-420));x=int(rng.integers(0,W-360));hh=int(rng.integers(120,300));ww=int(rng.integers(180,420));roi=out[y:y+hh,x:x+ww];small=cv2.resize(roi,(max(2,ww//28),max(2,hh//28)),interpolation=cv2.INTER_AREA);out[y:y+hh,x:x+ww]=cv2.resize(small,(ww,hh),interpolation=cv2.INTER_NEAREST)
    if intensity>=4 and local==2:out=cv2.bitwise_not(out)
    return out

class Reader:
    def __init__(self):self.cap={}
    def get(self,key,t):
        if key not in self.cap:self.cap[key]=cv2.VideoCapture(str(SRC/f'{key}.mp4'))
        c=self.cap[key];c.set(cv2.CAP_PROP_POS_MSEC,max(0,t)*1000);ok,f=c.read()
        if not ok:c.set(cv2.CAP_PROP_POS_FRAMES,0);ok,f=c.read()
        if not ok:raise RuntimeError(key)
        return f
    def close(self):
        for c in self.cap.values():c.release()

def render():
    for s in SPECS.values():dl_video(s)
    audio=dl_audio();out_raw=TMP/'visual.mp4';writer=cv2.VideoWriter(str(out_raw),cv2.VideoWriter_fourcc(*'mp4v'),FPS,(W,H));r=Reader();prev=None;gf=0
    for si,shot in enumerate(SHOTS):
        print('shot',si,shot.key,shot.frames,flush=True)
        for j in range(shot.frames):
            phase=j/max(1,shot.frames-1);idx=j
            if shot.stutter and j%9<shot.stutter:idx=max(0,j-(j%shot.stutter))
            t=shot.offset+(idx/FPS)*shot.speed;f=grade(crop(r.get(shot.key,t),SPECS[shot.key],phase),shot.palette)
            if prev is not None and j<4:f=cv2.addWeighted(f,.62,prev,.38,0)
            if shot.secondary:
                sf=grade(crop(r.get(shot.secondary,shot.offset+(j/FPS)*.55),SPECS[shot.secondary],phase),'mono')
                if shot.mode=='pip':
                    sw,sh=520,720;sf=cv2.resize(sf,(sw,sh));x=70 if si%2 else W-sw-70;y=230 if si%3 else 900;cv2.rectangle(f,(x-3,y-3),(x+sw+3,y+sh+3),(238,238,230),3);f[y:y+sh,x:x+sw]=sf
                else:f=cv2.addWeighted(f,.79,sf,.21,0)
            f=glitch(f,gf,shot.glitch);writer.write(f);prev=f.copy();gf+=1
    r.close();writer.release();final=OUT/'massachusetts_glitch_separation_reel.mp4'
    run(['ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(out_raw),'-i',str(audio),'-t',str(DUR),'-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','slow','-crf','17','-pix_fmt','yuv420p','-r',str(FPS),'-c:a','aac','-b:a','256k','-ar','48000','-ac','2','-movflags','+faststart',str(final)])
    run(['ffmpeg','-v','error','-i',str(final),'-f','null','-']);run(['ffprobe','-v','error','-show_entries','format=duration,size:stream=codec_name,codec_type,width,height,r_frame_rate,nb_frames,sample_rate,channels','-of','json',str(final)]);print('FINAL',final)
if __name__=='__main__':render()
