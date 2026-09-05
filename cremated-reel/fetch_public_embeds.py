#!/usr/bin/env python3
import concurrent.futures as cf
import json
import subprocess as sp
import sys
from pathlib import Path
OUT=Path('cremated_public_sources');OUT.mkdir(exist_ok=True)

def task(key,url,audio=False):
    d=OUT/key;d.mkdir(exist_ok=True)
    args=[sys.executable,'-m','yt_dlp','--no-playlist','--no-progress','--socket-timeout','20','--retries','1','--fragment-retries','1','--impersonate','chrome','--write-info-json','-o',str(d/'source.%(ext)s')]
    if audio:args+=['-f','bestaudio/best','-x','--audio-format','wav']
    else:args+=['-f','best[height>=1080]/bestvideo[height>=1080]','--match-filter','duration < 600']
    try:
        p=sp.run(args+[url],stdout=sp.PIPE,stderr=sp.STDOUT,text=True,timeout=180)
        (d/'download.log').write_text(p.stdout)
    except sp.TimeoutExpired:(d/'download.log').write_text('Acquisition timed out.');return
    print(key,'status',p.returncode,flush=True)
    for p in d.glob('source.*'):
        if p.suffix not in ['.mp4','.mkv','.webm','.wav','.mov','.mp3','.m4a']:continue
        try:meta=json.loads(sp.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(p)]))
        except Exception:continue
        (d/'provenance.json').write_text(json.dumps({'url':url,'probe':meta},indent=2))
        if not audio:
            interval=max(float(meta['format']['duration'])/48,.5)
            vf=f'fps=1/{interval},scale=256:144:force_original_aspect_ratio=decrease,pad=256:144:(ow-iw)/2:(oh-ih)/2,tile=6x8:padding=2:margin=2'
            sp.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(p),'-vf',vf,'-frames:v','1',str(d/'contact.jpg')],timeout=80)
    for p in d.glob('*.info.json'):
        data=json.loads(p.read_text());p.write_text(json.dumps({k:data.get(k) for k in ['id','title','description','uploader','duration','webpage_url','width','height','fps']},ensure_ascii=False,indent=2))

items=[('audio_repost','https://soundcloud.com/venndye/want-to-be-cremated-abuse',True),
 ('audio_repost_b','https://soundcloud.com/eiahg-47866398/want-to-be-cremated-abuse-with',True),
 ('equipment','https://player.vimeo.com/video/570123801',False),
 ('cremation_process','https://player.vimeo.com/video/465568950',False),
 ('cremation_center','https://player.vimeo.com/video/1022888676',False)]
with cf.ThreadPoolExecutor(max_workers=5) as ex:list(ex.map(lambda a:task(*a),items))
