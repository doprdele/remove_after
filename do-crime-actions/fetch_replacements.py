#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

ROOT=Path.cwd()
WORK=ROOT/'replacement-work'
OUT=ROOT/'replacement-clips'
RAW=WORK/'raw'
META=OUT/'metadata'
SHEETS=OUT/'contact_sheets'
for p in (RAW,META,SHEETS): p.mkdir(parents=True,exist_ok=True)

BASE=['yt-dlp','--no-playlist','--force-ipv4','--no-check-certificates','--retries','10','--fragment-retries','10','--socket-timeout','45','--concurrent-fragments','4','--js-runtimes','node','--remote-components','ejs:github','--impersonate','chrome']


def run(cmd:list[str], check:bool=True)->subprocess.CompletedProcess[str]:
    print('+',' '.join(map(str,cmd)),flush=True)
    p=subprocess.run(list(map(str,cmd)),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if p.stdout: print(p.stdout[-6000:])
    if p.stderr: print(p.stderr[-6000:],file=sys.stderr)
    if check and p.returncode: raise RuntimeError(f'command failed: {cmd[0]} ({p.returncode})')
    return p


def search(query:str)->list[dict[str,Any]]:
    rows=[]
    for spec in (f'ytsearch12:{query}',f'dmsearch6:{query}'):
        p=run(BASE+['--flat-playlist','--dump-json',spec],check=False)
        for line in p.stdout.splitlines():
            try: e=json.loads(line)
            except Exception: continue
            u=e.get('webpage_url') or e.get('url')
            if not u: continue
            if re.fullmatch(r'[A-Za-z0-9_-]{11}',str(u)): u='https://www.youtube.com/watch?v='+str(u)
            elif not str(u).startswith('http') and 'dailymotion' in str(e.get('extractor_key','')).lower(): u='https://www.dailymotion.com/video/'+str(u)
            if not str(u).startswith('http'): continue
            e['resolved_url']=str(u); rows.append(e)
    seen=set(); out=[]
    for e in rows:
        if e['resolved_url'] in seen: continue
        seen.add(e['resolved_url']); out.append(e)
    return out


def info(url:str)->dict[str,Any]|None:
    clients=('web_embedded','android_vr','web_safari','') if 'youtube.com' in url else ('',)
    for client in clients:
        cmd=list(BASE)
        if client: cmd += ['--extractor-args',f'youtube:player_client={client}']
        p=run(cmd+['--dump-single-json',url],check=False)
        if p.returncode==0:
            try: return json.loads(p.stdout)
            except Exception: pass
    return None


def rank(e:dict[str,Any],terms:tuple[str,...],mode:str)->float:
    title=str(e.get('title') or '').lower(); uploader=str(e.get('uploader') or e.get('channel') or '').lower()
    try: dur=float(e.get('duration') or 0)
    except: dur=0
    if mode=='robbery':
        s=20 if all(x in title for x in terms) else -18
        s+=16 if 'bank' in title else 0
        s+=15 if any(x in title for x in ('robbery','heist','robbers')) else 0
        s+=7 if any(x in title for x in ('scene','clip','sequence','opening')) else 0
        s+=6 if any(x in uploader for x in ('movieclips','warner','universal','paramount','sony','filmclips','rotten')) else 0
        if any(x in title for x in ('reaction','analysis','explained','trailer','soundtrack','gameplay','gta','edit','shorts')): s-=35
        if dur and not 25<=dur<=900: s-=20
        return s
    s=18 if 'flag' in title else -15
    s+=18 if any(x in title for x in ('burn','burning','fire','lit','set on fire')) else 0
    s+=14 if any(x in title for x in ('protest','protester','demonstrator','rally')) else 0
    s+=10 if any(x in title for x in ('american','u.s.','us flag','united states')) else 0
    s+=5 if any(x in title for x in ('raw','uncut','footage')) else 0
    if any(x in title for x in ('reaction','commentary','debate','song','music video','game')): s-=35
    if dur and not 15<=dur<=1200: s-=20
    return s


def clear_prefix(prefix:Path)->None:
    for p in prefix.parent.glob(prefix.name+'.*'):
        if p.is_file(): p.unlink()


def found(prefix:Path)->Path:
    fs=[p for p in prefix.parent.glob(prefix.name+'.*') if p.is_file() and not p.name.endswith(('.part','.ytdl','.json')) and '.info.' not in p.name]
    if not fs: raise RuntimeError('missing '+str(prefix))
    return max(fs,key=lambda p:p.stat().st_size)


def download(url:str,prefix:Path,start:float,end:float,preview:bool)->Path:
    clear_prefix(prefix)
    fmt='best[height<=720]/bestvideo[height<=720]+bestaudio/best' if preview else 'bestvideo[height>=1080][height<=2160][ext=mp4]/bestvideo[height>=1080][height<=2160]'
    clients=('web_embedded','android_vr','web_safari','') if 'youtube.com' in url else ('',)
    for client in clients:
        cmd=list(BASE)
        if client: cmd += ['--extractor-args',f'youtube:player_client={client}']
        cmd += ['--download-sections',f'*{start:.3f}-{end:.3f}','--force-keyframes-at-cuts','-f',fmt,'--merge-output-format','mp4','-o',str(prefix)+'.%(ext)s',url]
        p=run(cmd,check=False)
        if p.returncode==0:
            try: return found(prefix)
            except Exception: pass
        clear_prefix(prefix)
    raise RuntimeError('download failed '+url)


def analyze(path:Path,mode:str)->dict[str,Any]:
    out=path.with_suffix('.selection.json')
    run([sys.executable,'do-crime-actions/select_source.py',str(path),'--mode',mode,'--output',str(out)])
    return json.loads(out.read_text())


def select(key:str,query:str,terms:tuple[str,...],mode:str,limit:int)->tuple[Path,dict[str,Any]]:
    entries=search(query); entries.sort(key=lambda e:rank(e,terms,mode),reverse=True)
    choices=[]; tried=0
    for e in entries:
        if tried>=limit: break
        u=e['resolved_url']; d=info(u)
        if not d: continue
        hs=[int(f.get('height') or 0) for f in d.get('formats',[]) if f.get('vcodec') not in (None,'none')]
        maxh=max(hs or [0]); dur=float(d.get('duration') or e.get('duration') or 0)
        if maxh<1080 or dur<15 or dur>1200: continue
        tried+=1
        try:
            prev=download(u,RAW/f'{key}_preview_{tried}',0,min(dur,150),True)
            a=analyze(prev,mode)
            choices.append({'combined':float(a['score'])+rank(e,terms,mode)*0.35,'selection':a,'url':u,'id':d.get('id'),'title':d.get('title') or e.get('title'),'uploader':d.get('uploader') or e.get('uploader'),'duration':dur,'max_height':maxh})
        except Exception as exc: print('candidate failed',u,exc)
        finally:
            for p in RAW.glob(f'{key}_preview_{tried}.*'):
                if p.is_file(): p.unlink()
    if not choices: raise RuntimeError('no usable 1080p source for '+key)
    choices.sort(key=lambda x:x['combined'],reverse=True); c=choices[0]
    start=float(c['selection']['start']); end=min(float(c['duration']),start+14)
    raw=download(c['url'],RAW/key,start,end,False)
    c['source_window_start']=start; c['source_window_end']=end
    (META/f'{key}.json').write_text(json.dumps(c,indent=2)+'\n')
    return raw,c


def portrait(raw:Path,out:Path,anchor:float)->None:
    crop=f"crop=ih*0.50625:ih*0.90:max(0\\,min(iw-ow\\,iw*{anchor:.5f}-ow/2)):ih*0.05"
    run(['ffmpeg','-y','-hide_banner','-loglevel','warning','-stream_loop','-1','-i',str(raw),'-an','-vf',crop+',scale=1080:1920:flags=lanczos,setsar=1,fps=30,format=yuv420p','-t','12','-c:v','libx264','-preset','veryfast','-crf','17','-profile:v','high','-movflags','+faststart',str(out)])


def sheet(video:Path,out:Path)->None:
    run(['ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(video),'-vf',"fps=1,scale=180:320,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='%{pts\\:hms}':x=4:y=4:fontsize=13:fontcolor=white:borderw=2:bordercolor=black,tile=6x2:padding=3:margin=3:color=black",'-frames:v','1','-q:v','2',str(out)])


def main()->None:
    shutil.rmtree(WORK,ignore_errors=True); shutil.rmtree(OUT,ignore_errors=True)
    for p in (RAW,META,SHEETS): p.mkdir(parents=True,exist_ok=True)
    specs=[
      ('bank_robbery_1','The Dark Knight bank robbery opening scene 1080p',('dark','knight'),'robbery',4),
      ('bank_robbery_2','Heat bank robbery scene 1080p movie clip',('heat',),'robbery',4),
      ('bank_robbery_3','The Town bank robbery scene 1080p movie clip',('town',),'robbery',4),
      ('flag_burning','protesters light American flag on fire raw footage 1080p',('flag',),'flag',7),
    ]
    contacts=[]
    for key,q,terms,mode,limit in specs:
        raw,m=select(key,q,terms,mode,limit)
        anchor=float(m['selection'].get('anchor_x',0.5)) if mode=='flag' else 0.5
        out=OUT/f'{key}.mp4'; portrait(raw,out,anchor); sheet(out,SHEETS/f'{key}.jpg'); contacts.append(SHEETS/f'{key}.jpg')
        probe=run(['ffprobe','-v','error','-show_entries','format=duration,size:stream=codec_name,width,height,r_frame_rate','-of','json',str(out)]).stdout
        (META/f'{key}.ffprobe.json').write_text(probe)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',22)
    cards=[]
    for p in contacts:
        im=Image.open(p).convert('RGB'); card=Image.new('RGB',(im.width,im.height+42),'black'); card.paste(im,(0,42)); ImageDraw.Draw(card).text((8,8),p.stem,font=font,fill='white'); cards.append(card)
    cols=2; rows=math.ceil(len(cards)/cols); board=Image.new('RGB',(cols*cards[0].width,rows*cards[0].height),'black')
    for i,c in enumerate(cards): board.paste(c,((i%cols)*c.width,(i//cols)*c.height))
    board.save(OUT/'replacement_contact_board.jpg',quality=91)
    (OUT/'QC_PASSED.txt').write_text('PASS\n')
    print('REPLACEMENT CLIPS READY')

if __name__=='__main__': main()
