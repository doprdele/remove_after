#!/usr/bin/env bash
set -euo pipefail

mkdir -p work/{raw,src,audio,title,qc,frames} output
YTDLP=(yt-dlp --no-playlist --retries 8 --fragment-retries 8 --socket-timeout 45)

fetch() {
  local url="$1" out="$2"
  echo "FETCH ${out}"
  curl -LfsS --retry 6 --retry-delay 2 --connect-timeout 20 --max-time 900 "$url" -o "$out"
  test -s "$out"
}

dm_section() {
  local key="$1" id="$2" section="$3"
  rm -f "work/raw/${key}."* 2>/dev/null || true
  "${YTDLP[@]}" --download-sections "*${section}" --force-keyframes-at-cuts \
    -f 'bestvideo+bestaudio/best' --merge-output-format mp4 \
    -o "work/raw/${key}.%(ext)s" "https://www.dailymotion.com/video/${id}"
  local src
  src=$(find work/raw -maxdepth 1 -type f -name "${key}.*" ! -name '*.part' ! -name '*.info.json' | head -n1)
  test -s "$src"
  if [[ "$src" != "work/raw/${key}.mp4" ]]; then mv "$src" "work/raw/${key}.mp4"; fi
}

# Clean native-HD/4K stock masters.
fetch 'https://videos.pexels.com/video-files/3196002/3196002-uhd_3840_2160_25fps.mp4' work/raw/cash_counting.mp4
fetch 'https://videos.pexels.com/video-files/6266293/6266293-uhd_2160_3840_25fps.mp4' work/raw/cash_bag.mp4
fetch 'https://videos.pexels.com/video-files/13522186/13522186-uhd_3840_2160_25fps.mp4' work/raw/programmer.mp4
fetch 'https://videos.pexels.com/video-files/4578336/4578336-hd_1920_1080_25fps.mp4' work/raw/linux.mp4
fetch 'https://videos.pexels.com/video-files/30244590/12967797_3840_2160_24fps.mp4' work/raw/snow.mp4

# Preserve the already-approved Tout Va Bien supermarket sequence.
TOUT_URL='https://archive.org/download/tout.-va.-bien.-1972.-jean-luc.-godard.-1080p.-brrip.x-264-classics/Tout.Va.Bien.1972.%28Jean-Luc.Godard%29.1080p.BRRip.x264-Classics/Tout.Va.Bien.1972.%28Jean-Luc.Godard%29.1080p.BRRip.x264-Classics.mp4'
ffmpeg -y -hide_banner -loglevel warning -ss 5365 -i "$TOUT_URL" -t 75 -an \
  -c:v libx264 -preset veryfast -crf 17 -movflags +faststart work/raw/tout.mp4

# Replacement documentary sections selected from contact sheets.
# x3ho0sq, 20-28: a FARC column walking through jungle with weapons and field gear.
# x4yv8jf, 24-30: a group of armed FARC members in a jungle camp.
# x696jv6, 103-123: the giant U.S. flag is already visibly burning.
dm_section farc_walk x3ho0sq '20-28'
dm_section farc_armed x4yv8jf '24-30'
dm_section flag_burning x696jv6 '103-123'

# Same supplied track/version as the approved first render.
fetch 'https://itunes.apple.com/search?term=Raya%20Slowed%20Zericxxn&entity=song&limit=25' work/audio/itunes.json
preview=$(jq -r '.results[] | select((.artistName|ascii_downcase)=="zericxxn" and (.trackName|ascii_downcase|contains("raya")) and (.trackName|ascii_downcase|contains("slowed")) and ((.trackName|ascii_downcase|contains("super"))|not) and ((.trackName|ascii_downcase|contains("ultra"))|not)) | .previewUrl' work/audio/itunes.json | head -n1)
test -n "$preview"; test "$preview" != null
fetch "$preview" work/audio/raya_preview.m4a
ffmpeg -y -hide_banner -loglevel warning -i work/audio/raya_preview.m4a -vn \
  -c:a aac -b:a 256k -ar 48000 -ac 2 work/audio/raya_master.m4a

# Record native source dimensions. The two historical FARC mirrors and the protest
# clip are the best clean archival copies available and are deliberately isolated
# to short inserts; all stock and film material is HD/4K.
python - <<'PY'
import glob,json,subprocess
rows=[]
for f in sorted(glob.glob('work/raw/*')):
    if not f.lower().endswith(('.mp4','.mkv','.webm','.mov')): continue
    d=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height,r_frame_rate','-of','json',f]))
    s=d['streams'][0]
    rows.append({'file':f,'width':s['width'],'height':s['height'],'fps':s.get('r_frame_rate')})
open('work/qc/source_dimensions.json','w').write(json.dumps(rows,indent=2))
PY

# Normalize only the selected clean areas. Central documentary crops remove corner
# bugs and all lower-third/subtitle regions before any effects are applied.
ffmpeg -y -hide_banner -loglevel warning -stream_loop -1 -i work/raw/cash_counting.mp4 -an \
  -vf "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920:flags=lanczos,setsar=1,fps=60,format=yuv420p" \
  -t 12 -c:v libx264 -preset veryfast -crf 17 -profile:v high work/src/cash_counting.mp4

ffmpeg -y -hide_banner -loglevel warning -stream_loop -1 -i work/raw/cash_bag.mp4 -an \
  -vf "scale=1080:1920:flags=lanczos,setsar=1,fps=60,format=yuv420p" \
  -t 12 -c:v libx264 -preset veryfast -crf 17 -profile:v high work/src/cash_bag.mp4

ffmpeg -y -hide_banner -loglevel warning -stream_loop -1 -i work/raw/programmer.mp4 -an \
  -vf "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920:flags=lanczos,setsar=1,fps=60,format=yuv420p" \
  -t 9 -c:v libx264 -preset veryfast -crf 17 -profile:v high work/src/programmer.mp4
ffmpeg -y -hide_banner -loglevel warning -stream_loop -1 -i work/raw/linux.mp4 -an \
  -vf "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920:flags=lanczos,setsar=1,fps=60,format=yuv420p" \
  -t 9 -c:v libx264 -preset veryfast -crf 17 -profile:v high work/src/linux.mp4
ffmpeg -y -hide_banner -loglevel warning -i work/src/programmer.mp4 -i work/src/linux.mp4 -filter_complex \
  "[0:v]trim=0:8.5,setpts=PTS-STARTPTS[a];[1:v]trim=0:8.5,setpts=PTS-STARTPTS[b];[a][b]concat=n=2:v=1:a=0,setsar=1,format=yuv420p[v]" \
  -map '[v]' -an -c:v libx264 -preset veryfast -crf 17 -profile:v high work/src/cyber.mp4

ffmpeg -y -hide_banner -loglevel warning -stream_loop -1 -i work/raw/snow.mp4 -an \
  -vf "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920:flags=lanczos,setsar=1,fps=60,format=yuv420p" \
  -t 14 -c:v libx264 -preset veryfast -crf 17 -profile:v high work/src/snow.mp4

# Walking column: exact 9:16 central crop eliminates the Al Jazeera corner bug.
ffmpeg -y -hide_banner -loglevel warning -stream_loop -1 -i work/raw/farc_walk.mp4 -an \
  -vf "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920:flags=lanczos,setsar=1,fps=60,format=yuv420p" \
  -t 8 -c:v libx264 -preset veryfast -crf 16 -profile:v high work/src/farc_walk.mp4

# Armed lineup: crop from the upper-left/middle picture area, excluding both the
# broadcaster bug at upper-right and the burned-in Spanish subtitles below y=220.
ffmpeg -y -hide_banner -loglevel warning -stream_loop -1 -i work/raw/farc_armed.mp4 -an \
  -vf "crop=150:220:90:0,scale=1080:1920:flags=lanczos,setsar=1,fps=60,format=yuv420p" \
  -t 6 -c:v libx264 -preset veryfast -crf 16 -profile:v high work/src/farc_armed.mp4

# Keep the same Godard crop/composition the user approved.
ffmpeg -y -hide_banner -loglevel warning -stream_loop -1 -i work/raw/tout.mp4 -an \
  -vf "crop=iw*0.52:ih*0.86:(iw-iw*0.52)*0.31:ih*0.02,scale=1080:1920:flags=lanczos,setsar=1,fps=60,format=yuv420p" \
  -t 20 -c:v libx264 -preset veryfast -crf 17 -profile:v high work/src/tout.mp4

# Central portrait crop removes the small Newsflare corner mark. Flames and the
# U.S.-flag pattern stay centered throughout the selected range.
ffmpeg -y -hide_banner -loglevel warning -stream_loop -1 -i work/raw/flag_burning.mp4 -an \
  -vf "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920:flags=lanczos,setsar=1,fps=60,format=yuv420p" \
  -t 18 -c:v libx264 -preset veryfast -crf 16 -profile:v high work/src/flag_burning.mp4

# Two clean full-screen Godard/Evangelion-style title cards, with spaces preserved.
python - <<'PY'
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
W,H=1080,1920
rows=11
rh=(H+rows-1)//rows
fonts=[Path('/usr/share/fonts/opentype/didot/GFSDidotBold.otf'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf')]
fp=next(p for p in fonts if p.exists())
phrase='DO CRIME. DON’T VOTE  DO CRIME. DON’T VOTE'
font=ImageFont.truetype(str(fp),150)
probe=Image.new('L',(5200,400),0)
d=ImageDraw.Draw(probe)
box=d.textbbox((0,0),phrase,font=font)
d.text((-box[0],-box[1]),phrase,font=font,fill=255)
mask=probe.crop(probe.getbbox()).resize((W,rh),Image.Resampling.LANCZOS)
palettes=[(('#090909','#E6FF00'),('#1B22D8','#FF167A')),(('#FFF5DD','#1B22D8'),('#090909','#FF167A'))]
out=Path('work/title')
for n,pairs in enumerate(palettes):
    canvas=Image.new('RGB',(W,H),pairs[0][0])
    for r in range(rows):
        bg,fg=pairs[(r+n)%2]
        band=Image.new('RGB',(W,rh),bg)
        ink=Image.new('RGB',(W,rh),fg)
        band.paste(ink,(0,0),mask)
        canvas.paste(band,(0,r*rh))
    canvas.save(out/f'title{n}.png',optimize=True)
PY

# Beat analysis of the approved soundtrack yields approximately 97.51 BPM.
# Cuts use one- or two-beat blocks, instead of the prior eighth-note barrage.
python - <<'PY'
from pathlib import Path
B=60/97.50884433962264
TITLE_OPEN=0.685
TITLE_CLOSE=15-(TITLE_OPEN+22*B)
# 13 footage shots; lengths sum to 22 beats. Most last two full beats (~1.23 s).
shots=[
 ('cash_counting',0,0.25,2,0.92),
 ('cash_bag',1,0.60,2,0.88),
 ('farc_walk',4,0.70,2,0.92),
 ('tout',6,0.45,2,1.00),
 ('cyber',2,0.40,1,1.12),
 ('snow',3,1.10,2,1.18),
 ('flag_burning',7,0.60,2,0.88),
 ('farc_armed',5,0.10,2,0.84),
 ('tout',6,4.10,1,0.96),
 ('cyber',2,8.70,2,1.04),
 ('cash_counting',0,3.10,1,1.10),
 ('farc_walk',4,3.00,2,0.88),
 ('flag_burning',7,7.10,1,0.92),
]
parts=[]
labels=[]
# Clean title streams. They never pass through noise, scanlines or RGB splitting.
parts.append(f'[9:v]trim=duration={TITLE_OPEN:.9f},setpts=PTS-STARTPTS,fps=60,scale=1080:1920,setsar=1,format=yuv420p[topen]')
labels.append('[topen]')
for i,(name,inp,cue,beats,speed) in enumerate(shots):
    dur=beats*B
    source_dur=dur*speed
    zoom=1.045+(i%4)*0.018
    sw=round(1080*zoom); sh=round(1920*zoom)
    maxx=sw-1080; maxy=sh-1920
    xbase=maxx/2; ybase=maxy/2
    # Dynamic crop movement supplies restrained shake while preserving legibility.
    chain=(f'[{inp}:v]trim=start={cue:.4f}:end={cue+source_dur:.4f},'
           f'setpts=(PTS-STARTPTS)/{speed:.6f},fps=60,scale={sw}:{sh}:flags=bicubic,'
           f"crop=1080:1920:x='{xbase:.2f}+min({maxx/3:.2f}\\,10)*sin(31*t+{i})':"
           f"y='{ybase:.2f}+min({maxy/3:.2f}\\,8)*cos(27*t+{i})',setsar=1,")
    if i in {4,7,10}:
        chain+='loop=loop=1:size=4:start=28,'
    chain+=(f'trim=duration={dur:.9f},setpts=PTS-STARTPTS,'
            f'eq=contrast={1.23+(i%3)*0.035:.3f}:saturation={1.34+(i%4)*0.05:.3f}:brightness=-0.025,'
            f'rgbashift=rh={8+(i%3)*3}:bh={-8-(i%3)*3}:rv=2:bv=-2,'
            f'noise=alls={8+(i%4)*2}:allf=t+u,drawgrid=w=1080:h=4:t=1:c=black@0.24,'
            f'unsharp=5:5:0.75:5:5:0,format=yuv420p[s{i}]')
    parts.append(chain)
    labels.append(f'[s{i}]')
parts.append(f'[10:v]trim=duration={TITLE_CLOSE:.9f},setpts=PTS-STARTPTS,fps=60,scale=1080:1920,setsar=1,format=yuv420p[tclose]')
labels.append('[tclose]')
parts.append(''.join(labels)+f'concat=n={len(labels)}:v=1:a=0[base]')

# Impact flashes occur on beat boundaries inside footage, never over title cards.
bounds=[]
t=TITLE_OPEN
for _,_,_,beats,_ in shots:
    t += beats*B
    bounds.append(t)
neg_times=[bounds[i] for i in (1,3,6,9,11)]
white_times=[bounds[i] for i in (2,5,8,10)]
neg='+'.join(f'between(t,{x-.018:.6f},{x+.018:.6f})' for x in neg_times)
white='+'.join(f'between(t,{x-.018:.6f},{x+.018:.6f})' for x in white_times)
parts.append(f"[base]negate=enable='{neg}',drawbox=x=0:y=0:w=iw:h=ih:color=white@1:t=fill:enable='{white}'[impact]")

# Three moving horizontal tear bands, again confined to footage beat impacts.
parts += [
 '[impact]split=4[m][a][b][c]',
 '[a]format=rgba,crop=1080:110:0:335,pad=1080:1920:0:335:color=black@0[ta]',
 '[b]format=rgba,crop=1080:88:0:915,pad=1080:1920:0:915:color=black@0[tb]',
 '[c]format=rgba,crop=1080:125:0:1435,pad=1080:1920:0:1435:color=black@0[tc]',
]
tear_a=[bounds[i] for i in (4,8,12)]
tear_b=[bounds[i] for i in (0,7,10)]
tear_c=[bounds[i] for i in (2,6,11)]
ea='+'.join(f'between(t,{x-.045:.6f},{x+.045:.6f})' for x in tear_a)
eb='+'.join(f'between(t,{x-.038:.6f},{x+.038:.6f})' for x in tear_b)
ec='+'.join(f'between(t,{x-.040:.6f},{x+.040:.6f})' for x in tear_c)
parts += [
 f"[m][ta]overlay=x=78:y=0:enable='{ea}'[o1]",
 f"[o1][tb]overlay=x=-64:y=0:enable='{eb}'[o2]",
 f"[o2][tc]overlay=x=90:y=0:enable='{ec}'[o3]",
 '[o3]trim=duration=15,setpts=PTS-STARTPTS[outv]',
]
Path('work/filter.txt').write_text(';\n'.join(parts)+'\n')
Path('work/qc/timeline.txt').write_text(
    f'BPM=97.508844\nbeat={B:.9f}\nopening_title={TITLE_OPEN:.9f}\nclosing_title={TITLE_CLOSE:.9f}\n' +
    '\n'.join(f'{i+1:02d} {name} {beats} beat(s) {beats*B:.6f}s cue={cue:.3f}' for i,(name,_,cue,beats,_) in enumerate(shots))
)
PY

ffmpeg -y -hide_banner -loglevel warning \
  -i work/src/cash_counting.mp4 \
  -i work/src/cash_bag.mp4 \
  -i work/src/cyber.mp4 \
  -i work/src/snow.mp4 \
  -i work/src/farc_walk.mp4 \
  -i work/src/farc_armed.mp4 \
  -i work/src/tout.mp4 \
  -i work/src/flag_burning.mp4 \
  -i work/audio/raya_master.m4a \
  -loop 1 -framerate 60 -i work/title/title0.png \
  -loop 1 -framerate 60 -i work/title/title1.png \
  -filter_complex_script work/filter.txt \
  -map '[outv]' -map 8:a:0 -t 15 -frames:v 900 \
  -c:v libx264 -preset medium -crf 17 -maxrate 16M -bufsize 32M \
  -profile:v high -level:v 4.2 -pix_fmt yuv420p -r 60 -g 60 -keyint_min 60 -sc_threshold 0 \
  -color_primaries bt709 -color_trc bt709 -colorspace bt709 \
  -c:a aac -b:a 256k -ar 48000 -ac 2 \
  -af 'afade=t=in:st=0:d=0.012,afade=t=out:st=14.93:d=0.07,alimiter=limit=0.97' \
  -movflags +faststart output/do_crime_dont_vote_reel_revision.mp4

# Technical QC and decode test.
ffprobe -v error -count_frames -show_entries \
  format=duration,size,bit_rate:stream=index,codec_type,codec_name,profile,width,height,pix_fmt,r_frame_rate,avg_frame_rate,sample_rate,channels,duration,nb_frames,nb_read_frames \
  -of json output/do_crime_dont_vote_reel_revision.mp4 | tee work/qc/final_ffprobe.json
ffmpeg -v error -i output/do_crime_dont_vote_reel_revision.mp4 -f null -

python - <<'PY'
import json
p='work/qc/final_ffprobe.json'
d=json.load(open(p)); ss={s['codec_type']:s for s in d['streams']}; v=ss['video']; a=ss['audio']; errors=[]
if abs(float(d['format']['duration'])-15)>0.025: errors.append('duration')
if (v.get('width'),v.get('height'))!=(1080,1920): errors.append('resolution')
if v.get('codec_name')!='h264' or v.get('r_frame_rate')!='60/1': errors.append('video')
if v.get('pix_fmt')!='yuv420p': errors.append('pixel format')
if int(v.get('nb_read_frames') or v.get('nb_frames') or 0)!=900: errors.append('frame count')
if a.get('codec_name')!='aac' or a.get('sample_rate')!='48000': errors.append('audio')
if errors: raise SystemExit('FINAL QC FAILED: '+', '.join(errors))
open('work/qc/QC_PASSED.txt','w').write('PASS\n')
print('FINAL QC PASSED')
PY

# Visual-QC sheets and representative frames.
ffmpeg -y -hide_banner -loglevel error -i output/do_crime_dont_vote_reel_revision.mp4 \
  -vf "fps=4/3,scale=216:384,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='%{pts\\:hms}':x=5:y=5:fontsize=14:fontcolor=white:borderw=2:bordercolor=black,tile=5x4:padding=4:margin=4:color=black" \
  -frames:v 1 -q:v 2 work/qc/final_contact_sheet.jpg

for k in cash_counting cash_bag cyber snow farc_walk farc_armed tout flag_burning; do
  ffmpeg -y -hide_banner -loglevel error -i "work/src/${k}.mp4" \
    -vf "fps=1,scale=180:320,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='%{pts\\:hms}':x=4:y=4:fontsize=13:fontcolor=white:borderw=2:bordercolor=black,tile=6x4:padding=3:margin=3:color=black" \
    -frames:v 1 -q:v 2 "work/qc/${k}_contact.jpg" || true
done

for spec in '0.20 title_open' '2.20 farc_walk' '6.00 flag_burning' '7.40 farc_armed' '14.60 title_close'; do
  set -- $spec
  ffmpeg -y -hide_banner -loglevel error -ss "$1" -i output/do_crime_dont_vote_reel_revision.mp4 -frames:v 1 -q:v 1 "work/frames/$2.jpg"
done

cp work/filter.txt output/filter_complex.txt
cp work/qc/final_ffprobe.json output/final_ffprobe.json
cp work/qc/timeline.txt output/timeline.txt
cp work/qc/QC_PASSED.txt output/QC_PASSED.txt
cp work/qc/*_contact.jpg output/ || true
cp work/frames/*.jpg output/ || true
