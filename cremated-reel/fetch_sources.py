#!/usr/bin/env python3
"""Retrieve the requested recording and short cremation-equipment reference films.
No credentials, paywall workarounds, or full feature films are used.
The output is a private-to-the-workflow artifact, not committed media.
"""
import concurrent.futures as cf
import html
import json
import re
import subprocess as sp
import sys
from pathlib import Path
import requests

OUT = Path('cremated_sources')
OUT.mkdir(exist_ok=True)
BASE = [sys.executable, '-m', 'yt_dlp', '--no-playlist', '--no-progress',
        '--socket-timeout', '15', '--retries', '1', '--fragment-retries', '1',
        '--js-runtimes', 'node', '--remote-components', 'ejs:github']

def command(args, log, timeout=140):
    try:
        p = sp.run(args, stdout=sp.PIPE, stderr=sp.STDOUT, text=True, timeout=timeout)
        text = p.stdout
        # Signed CDN URLs need not be published in the artifact's logs.
        text = re.sub(r'https?://\S+(?:googlevideo|bilivideo)\S*', '<CDN URL>', text)
        Path(log).write_text(text)
        print(Path(log).name, 'status', p.returncode, flush=True)
        return p.returncode == 0
    except sp.TimeoutExpired:
        Path(log).write_text('Timed out after bounded acquisition attempt.')
        print(Path(log).name, 'timed out', flush=True)
        return False

def probe(p):
    try:
        return json.loads(sp.check_output(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(p)], text=True))
    except Exception:
        return None

def audio():
    dest = OUT / 'audio'
    dest.mkdir(exist_ok=True)
    url = 'https://www.youtube.com/watch?v=jDos7axCazU'
    for client in ['default', 'android_vr', 'web_safari', 'web_embedded']:
        args = BASE + ([] if client == 'default' else ['--extractor-args', 'youtube:player_client=' + client])
        ok = command(args + ['-f', 'bestaudio/best', '-x', '--audio-format', 'wav',
                '-o', str(dest / 'requested_track.%(ext)s'), url], dest / ('youtube_' + client + '.log'))
        wav = dest / 'requested_track.wav'
        if ok and wav.exists() and probe(wav):
            (dest / 'provenance.json').write_text(json.dumps({'requested_url': url, 'retrieved_url': url, 'mirror': False}, indent=2))
            return True
    # This page explicitly identifies the same original YouTube recording.
    # Prefer its YouTube version, rather than a cover or an instrumental remix.
    mirror = 'https://www.bilibili.com/video/BV1UJ411U72v/?p=2'
    ok = command(BASE + ['-f', 'bestaudio/best', '-x', '--audio-format', 'wav',
             '-o', str(dest / 'requested_track.%(ext)s'), mirror], dest / 'same_recording_mirror.log', 220)
    if ok and (dest / 'requested_track.wav').exists():
        (dest / 'provenance.json').write_text(json.dumps({'requested_url': url, 'retrieved_url': mirror, 'mirror': True,
            'note': 'Repost explicitly links original jDos7axCazU. Verify audible content before use.'}, indent=2))
        return True
    return False

def discover():
    pages = ['https://dfweurope.com/video/', 'https://www.cremsys.com/installation/']
    refs = []
    for url in pages:
        try:
            text = html.unescape(requests.get(url, timeout=25).text).replace('\\/', '/')
            (OUT / ('page_' + str(len(refs)) + '.html')).write_text(text)
            yt = re.findall(r'(?:youtube(?:-nocookie)?\.com/(?:embed/|watch\?v=)|youtu\.be/)([\w-]{11})', text)
            vi = re.findall(r'(?:player\.)?vimeo\.com/(?:video/)?(\d{6,})', text)
            refs += [('https://www.youtube.com/watch?v=' + i, url) for i in yt]
            refs += [('https://vimeo.com/' + i, url) for i in vi]
        except Exception as e:
            print('Page discovery failed', url, type(e).__name__, flush=True)
    refs += [('https://vimeo.com/570123801', 'Heaven Funeral Supplies equipment demonstration')]
    seen = set()
    refs = [(u, p) for u, p in refs if not (u in seen or seen.add(u))]
    (OUT / 'discovered.json').write_text(json.dumps(refs, indent=2))
    return refs[:8]

def video(item):
    index, (url, origin) = item
    dest = OUT / ('candidate_%02d' % index)
    dest.mkdir(exist_ok=True)
    # Download the short equipment films at 1080p or better. Source overlays,
    # people, bodies, branding and captions will be rejected during visual QC.
    fmt = 'bestvideo[height>=1080][height<=2160][vcodec^=avc1]/bestvideo[height>=1080][height<=2160]/best[height>=1080]'
    ok = command(BASE + ['--match-filter', 'duration < 600', '-f', fmt,
        '--write-info-json', '-o', str(dest / 'source.%(ext)s'), url], dest / 'download.log', 170)
    paths = [p for p in dest.glob('source.*') if p.suffix in ('.mp4', '.mkv', '.webm', '.mov')]
    if not paths:
        print('No HD video', url, flush=True)
        return False
    p = paths[0]
    meta = probe(p)
    if not meta:
        return False
    (dest / 'provenance.json').write_text(json.dumps({'url': url, 'origin': origin, 'probe': meta}, indent=2))
    # A low-resolution contact sheet is for inspection only, never final footage.
    duration = float(meta['format']['duration'])
    interval = max(duration / 48, .5)
    vf = ('fps=1/' + str(interval) + ',scale=256:144:force_original_aspect_ratio=decrease,'
          'pad=256:144:(ow-iw)/2:(oh-ih)/2,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:'
          "text='%{pts\\:hms}':fontsize=14:fontcolor=white:box=1:boxcolor=black@0.8:x=3:y=3,"
          'tile=6x8:padding=2:margin=2')
    command(['ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(p),'-vf',vf,'-frames:v','1',str(dest/'contact.jpg')],dest/'contact.log',80)
    # Remove ephemeral signed URLs from the saved extractor response.
    for ip in dest.glob('*.info.json'):
        data = json.loads(ip.read_text())
        clean = {k:data.get(k) for k in ['id','title','uploader','webpage_url','duration','width','height','fps','license','description']}
        ip.write_text(json.dumps(clean, ensure_ascii=False, indent=2))
    return True

if __name__ == '__main__':
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        af = ex.submit(audio)
        refs = discover()
        results = list(ex.map(video, enumerate(refs)))
        good_audio = af.result()
    summary = {'audio_obtained': good_audio, 'hd_candidates_obtained': sum(results), 'candidates_attempted': len(refs)}
    (OUT/'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)
    # Always upload diagnostic output, including on a partial failure.
