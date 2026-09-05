#!/usr/bin/env python3
"""Retrieve public documentary sources for non-graphic active-cremation shots.
Source candidates require visual review before inclusion. No source media are
committed to the repository. The prior edit and source files are unchanged.
"""
import concurrent.futures as cf
import json
import subprocess as sp
import sys
from pathlib import Path

OUT=Path('active_cremation_v2'); OUT.mkdir(exist_ok=True)
SOURCES=[('process','https://player.vimeo.com/video/867221874'),
         ('canberra','https://player.vimeo.com/video/842357988')]

def get(item):
    key,url=item
    folder=OUT/key; folder.mkdir(exist_ok=True)
    cmd=[sys.executable,'-m','yt_dlp','--no-playlist','--no-progress',
         '--socket-timeout','25','--retries','2','--fragment-retries','2',
         '--impersonate','chrome','--write-info-json',
         '-f','best[height=1080]/bestvideo[height=1080]/best[height>=1080][height<=2160]/bestvideo[height>=1080][height<=2160]',
         '-o',str(folder/'source.%(ext)s'),url]
    try:
        result=sp.run(cmd,stdout=sp.PIPE,stderr=sp.STDOUT,text=True,timeout=260)
        (folder/'download.log').write_text(result.stdout)
        print(key,'download returncode',result.returncode,flush=True)
    except sp.TimeoutExpired:
        (folder/'download.log').write_text('Bounded acquisition timed out.')
        return False
    media=[p for p in folder.glob('source.*') if p.suffix in ('.mp4','.mkv','.webm','.mov')]
    if not media: return False
    p=media[0]
    meta=json.loads(sp.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(p)]))
    video=next(s for s in meta['streams'] if s['codec_type']=='video')
    if int(video['height'])<1080: raise ValueError('HD source required')
    (folder/'provenance.json').write_text(json.dumps({'url':url,'probe':meta},indent=2))
    duration=float(meta['format']['duration']); interval=duration/96
    for page in range(2):
        begin=page*duration/2
        vf=(f'fps=1/{interval},scale=320:180:force_original_aspect_ratio=decrease,'
            'pad=320:180:(ow-iw)/2:(oh-ih)/2,'
            'drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:'
            "text='%{pts\\:hms}':fontsize=16:fontcolor=white:box=1:boxcolor=black@0.8:x=3:y=3,"
            'tile=6x8:padding=2:margin=2')
        sp.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-ss',str(begin),'-i',str(p),'-t',str(duration/2),'-vf',vf,'-frames:v','1',str(folder/f'contact_{page}.jpg')],check=True,timeout=140)
    (folder/'contact_timing.json').write_text(json.dumps({'page_seconds':duration/2,'interval_seconds':interval,'cells_per_page':48},indent=2))
    for ip in folder.glob('*.info.json'):
        data=json.loads(ip.read_text())
        ip.write_text(json.dumps({k:data.get(k) for k in ['id','title','description','uploader','duration','webpage_url','width','height','fps','license']},ensure_ascii=False,indent=2))
    return True

with cf.ThreadPoolExecutor(max_workers=2) as pool:
    result=list(pool.map(get,SOURCES))
(OUT/'summary.json').write_text(json.dumps({'downloaded':result},indent=2))
print(result,flush=True)
