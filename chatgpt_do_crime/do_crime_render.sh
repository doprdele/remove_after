#!/usr/bin/env bash
set -euo pipefail
mkdir -p work/{raw,src,audio,title,qc} output
YTDLP=(yt-dlp --no-playlist --retries 5 --fragment-retries 5 --socket-timeout 45 --concurrent-fragments 4)
fetch(){ echo "FETCH $2"; curl -LfsS --retry 5 --retry-delay 2 --connect-timeout 20 --max-time 600 "$1" -o "$2"; test -s "$2"; }

# Direct, watermark-free Pexels masters discovered from each page's Free download redirect.
fetch 'https://videos.pexels.com/video-files/3196002/3196002-uhd_3840_2160_25fps.mp4' work/raw/cash.mp4
fetch 'https://videos.pexels.com/video-files/6230464/6230464-hd_1920_1080_24fps.mp4' work/raw/watch.mp4
fetch 'https://videos.pexels.com/video-files/6649983/6649983-uhd_4096_2160_25fps.mp4' work/raw/bag.mp4
fetch 'https://videos.pexels.com/video-files/13522186/13522186-uhd_3840_2160_25fps.mp4' work/raw/programmer.mp4
fetch 'https://videos.pexels.com/video-files/4578336/4578336-hd_1920_1080_25fps.mp4' work/raw/linux.mp4
fetch 'https://videos.pexels.com/video-files/30244590/12967797_3840_2160_24fps.mp4' work/raw/snow.mp4

# Exact requested Godard supermarket sequence, real FARC documentary footage, and real flag-burning protest footage.
get_vimeo(){ key="$1"; url="$2"; section="$3"; echo "VIMEO $key"; "${YTDLP[@]}" --download-sections "*$section" --force-keyframes-at-cuts -f 'bestvideo[height>=1080]+bestaudio/best[height>=1080]' --merge-output-format mp4 -o "work/raw/${key}.%(ext)s" "$url"; f=$(find work/raw -maxdepth 1 -type f -name "${key}.*" ! -name '*.part' | head -n1); test -s "$f"; mv "$f" "work/raw/${key}.mp4"; }
get_vimeo tout 'https://vimeo.com/127193878' '20-90'
get_vimeo farc 'https://vimeo.com/194571130' '0-90'
get_vimeo flag 'https://vimeo.com/218313862' '0-180'

# Exact track version via artist-attributed Audiomack mirror (same RAYA slowed master as supplied link).
audio_ok=0
for u in 'https://audiomack.com/zericxxn/song/raya-slowed' 'https://audiomack.com/darwin_10/song/raya-slowed'; do
  rm -f work/audio/raya.* 2>/dev/null || true
  if "${YTDLP[@]}" -f 'bestaudio/best' -x --audio-format m4a --audio-quality 0 -o 'work/audio/raya.%(ext)s' "$u"; then audio_ok=1; break; fi
done
test "$audio_ok" -eq 1
audio=$(find work/audio -maxdepth 1 -type f -name 'raya.*' ! -name '*.part' | head -n1)
ffmpeg -y -v warning -i "$audio" -vn -c:a aac -b:a 256k -ar 48000 -ac 2 work/audio/raya_master.m4a

# Hard source-resolution gate: every moving source must be native 1080p or better.
python - <<'PY'
import json,subprocess,glob,sys
bad=[]; rows=[]
for f in glob.glob('work/raw/*'):
 if not f.lower().endswith(('.mp4','.webm','.mov','.mkv')): continue
 d=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height,r_frame_rate','-of','json',f]))
 s=d['streams'][0]; rows.append((f,s['width'],s['height'],s.get('r_frame_rate')))
 if int(s['width'])<1080 or int(s['height'])<1080: bad.append((f,s['width'],s['height']))
open('work/qc/source_resolution.txt','w').write('\n'.join(map(str,rows)))
if bad:
 print('SOURCE RESOLUTION FAIL',bad); sys.exit(2)
PY

# Normalize to 9:16 vertical masters. Crops intentionally discard corners/lower thirds.
norm(){ key="$1"; in="$2"; x="$3"; top="$4"; bottom="$5"; ffmpeg -y -v warning -stream_loop -1 -i "$in" -an -vf "crop=iw*0.52:ih*(1-${top}-${bottom}):(iw-iw*0.52)*${x}:ih*${top},scale=1080:1920:flags=lanczos,setsar=1,fps=60,format=yuv420p" -t 20 -c:v libx264 -preset veryfast -crf 18 -profile:v high "work/src/${key}.mp4"; }
norm cash work/raw/cash.mp4 .50 .02 .04
# Mix actual cash with luxury watch + handbag into one wealth master.
ffmpeg -y -v warning -i work/src/cash.mp4 -stream_loop -1 -i work/raw/watch.mp4 -stream_loop -1 -i work/raw/bag.mp4 -filter_complex "[1:v]crop=iw*.52:ih*.94:(iw-iw*.52)/2:ih*.02,scale=1080:1920,fps=60,format=yuv420p[w];[2:v]crop=iw*.52:ih*.94:(iw-iw*.52)/2:ih*.02,scale=1080:1920,fps=60,format=yuv420p[b];[0:v]trim=0:7,setpts=PTS-STARTPTS[c];[w]trim=0:5,setpts=PTS-STARTPTS[w2];[b]trim=0:5,setpts=PTS-STARTPTS[b2];[c][w2][b2]concat=n=3:v=1:a=0" -t 17 -an -c:v libx264 -preset veryfast -crf 18 work/src/wealth.mp4
norm programmer work/raw/programmer.mp4 .50 .02 .04
norm linux work/raw/linux.mp4 .50 .02 .04
ffmpeg -y -v warning -i work/src/programmer.mp4 -i work/src/linux.mp4 -filter_complex "[0:v]trim=0:10,setpts=PTS-STARTPTS[a];[1:v]trim=0:10,setpts=PTS-STARTPTS[b];[a][b]concat=n=2:v=1:a=0" -an -c:v libx264 -preset veryfast -crf 18 work/src/cyber.mp4
norm snow work/raw/snow.mp4 .50 .02 .04
norm farc work/raw/farc.mp4 .50 .03 .10
norm tout work/raw/tout.mp4 .31 .02 .12
norm flag work/raw/flag.mp4 .50 .03 .10

# Clean title cards: no grain/scanlines. Spaced phrase, full screen, saturated acid palette.
python - <<'PY'
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
W,H=1080,1920; rows=11; rh=(H+rows-1)//rows
fonts=[Path('/usr/share/fonts/opentype/didot/GFSDidotBold.otf'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf')]
fp=next(p for p in fonts if p.exists()); phrase='DO CRIME. DON’T VOTE  DO CRIME. DON’T VOTE'
font=ImageFont.truetype(str(fp),150); probe=Image.new('L',(5200,400)); d=ImageDraw.Draw(probe); box=d.textbbox((0,0),phrase,font=font); d.text((-box[0],-box[1]),phrase,font=font,fill=255); mask=probe.crop(probe.getbbox()).resize((W,rh),Image.Resampling.LANCZOS)
pals=[(('#090909','#E6FF00'),('#1B22D8','#FF167A')),(('#E6FF00','#090909'),('#FF167A','#FFF5DD')),(('#FF167A','#FFF5DD'),('#1B22D8','#E6FF00')),(('#FFF5DD','#1B22D8'),('#090909','#FF167A'))]
out=Path('work/title');out.mkdir(exist_ok=True)
for n,pairs in enumerate(pals):
 c=Image.new('RGB',(W,H),pairs[0][0])
 for r in range(rows):
  bg,fg=pairs[(r+n)%2]; band=Image.new('RGB',(W,rh),bg); ink=Image.new('RGB',(W,rh),fg); band.paste(ink,(0,0),mask); c.paste(band,(0,r*rh))
 c.save(out/f'title{n}.png')
PY

# 55 eighth-note slots at 110 BPM + speed ramps, zoom punches, RGB split, VHS/noise, tearing, inversion & white flashes.
python - <<'PY'
from pathlib import Path
S=3/11; N=55
cats=['wealth','cyber','snow','farc','tout','wealth','flag','cyber','snow','wealth','tout','farc','cyber','flag','snow','tout','wealth','cyber','farc','snow','flag','wealth','tout','cyber']
idx={'wealth':0,'cyber':1,'snow':2,'farc':3,'tout':4,'flag':5}; counts={k:0 for k in idx}; spd=[.70,1.35,2.60,.60,1.90,3.10,1.0,2.30,.82,1.60,2.85,.66]
parts=[]; labs=[]
for i in range(N):
 cat=cats[i%len(cats)]; c=counts[cat]; counts[cat]+=1; cue=(.25+c*1.23)%15.4; sp=spd[i%len(spd)]; need=S*sp; z=1.035+(i%5)*.015; sw=round(1080*z); sh=round(1920*z); x=max(0,(sw-1080)//2+((i%3)-1)*13); y=max(0,(sh-1920)//2+((i%4)-2)*8)
 parts.append(f'[{idx[cat]}:v]trim=start={cue:.4f}:end={cue+need:.4f},setpts=(PTS-STARTPTS)/{sp:.5f},fps=60,scale={sw}:{sh}:flags=bicubic,crop=1080:1920:{x}:{y},format=yuv420p[s{i}]'); labs.append(f'[s{i}]')
parts.append(''.join(labs)+f'concat=n={N}:v=1:a=0[base]')
parts.append("[base]eq=contrast=1.30:saturation=1.48:brightness=-0.035,rgbashift=rh=12:bh=-12:rv=3:bv=-3,noise=alls=12:allf=t+u,drawgrid=w=1080:h=4:t=1:c=black@0.28,unsharp=5:5:0.9:5:5:0[fx0]")
neg='+'.join(f'between(t,{t:.3f},{t+.034:.3f})' for t in [1.09,2.46,3.82,5.46,8.46,9.55,11.46,12.55,14.18]); white='+'.join(f'between(t,{t:.3f},{t+.034:.3f})' for t in [3.27,5.73,8.73,11.73,14.46]); parts.append(f"[fx0]negate=enable='{neg}',drawbox=x=0:y=0:w=iw:h=ih:color=white@1:t=fill:enable='{white}'[fx1]")
parts += ['[fx1]split=4[m][a][b][c]','[a]format=rgba,crop=1080:105:0:335,pad=1080:1920:0:335:color=black@0[ta]','[b]format=rgba,crop=1080:88:0:915,pad=1080:1920:0:915:color=black@0[tb]','[c]format=rgba,crop=1080:125:0:1435,pad=1080:1920:0:1435:color=black@0[tc]']
e1='+'.join(f'between(t,{t:.3f},{t+.08:.3f})' for t in [2.18,5.18,8.18,11.18,13.64]); e2='+'.join(f'between(t,{t:.3f},{t+.065:.3f})' for t in [3,6,9,12]); e3='+'.join(f'between(t,{t:.3f},{t+.07:.3f})' for t in [4.09,7.09,10.09,13.09]); parts += [f"[m][ta]overlay=x=75:y=0:enable='{e1}'[o1]",f"[o1][tb]overlay=x=-60:y=0:enable='{e2}'[o2]",f"[o2][tc]overlay=x=88:y=0:enable='{e3}'[o3]"]
prev='o3'
for n,(inp,slot) in enumerate(zip([7,8,9,10],[0,20,40,54]),1):
 st=slot*S; en=(slot+1)*S; parts.append(f'[{prev}][{inp}:v]overlay=0:0:enable=between(t\\,{st:.6f}\\,{en:.6f})[t{n}]'); prev=f't{n}'
parts.append(f'[{prev}]trim=duration=15,setpts=PTS-STARTPTS[outv]'); Path('work/filter.txt').write_text(';\n'.join(parts)+'\n')
PY

ffmpeg -y -hide_banner -loglevel warning -i work/src/wealth.mp4 -i work/src/cyber.mp4 -i work/src/snow.mp4 -i work/src/farc.mp4 -i work/src/tout.mp4 -i work/src/flag.mp4 -ss 44.742 -i work/audio/raya_master.m4a -loop 1 -framerate 60 -i work/title/title0.png -loop 1 -framerate 60 -i work/title/title1.png -loop 1 -framerate 60 -i work/title/title2.png -loop 1 -framerate 60 -i work/title/title3.png -filter_complex_script work/filter.txt -map '[outv]' -map 6:a:0 -frames:v 900 -t 15 -c:v libx264 -preset medium -crf 17 -maxrate 16M -bufsize 32M -profile:v high -level:v 4.2 -pix_fmt yuv420p -r 60 -g 60 -keyint_min 60 -sc_threshold 0 -color_primaries bt709 -color_trc bt709 -colorspace bt709 -c:a aac -b:a 256k -ar 48000 -ac 2 -af 'afade=t=in:st=0:d=.012,afade=t=out:st=14.93:d=.07,alimiter=limit=.97' -movflags +faststart output/do_crime_dont_vote_reel.mp4
ffprobe -v error -count_frames -show_entries format=duration,size,bit_rate:stream=index,codec_type,codec_name,profile,width,height,pix_fmt,r_frame_rate,avg_frame_rate,sample_rate,channels,duration,nb_frames,nb_read_frames -of json output/do_crime_dont_vote_reel.mp4 | tee work/qc/final_ffprobe.json
ffmpeg -v error -i output/do_crime_dont_vote_reel.mp4 -f null -
ffmpeg -y -v error -i output/do_crime_dont_vote_reel.mp4 -vf "fps=4/3,scale=216:384,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='%{pts\\:hms}':x=5:y=5:fontsize=14:fontcolor=white:borderw=2:bordercolor=black,tile=5x4:padding=4:margin=4:color=black" -frames:v 1 -q:v 2 work/qc/final_contact_sheet.jpg
for k in wealth cyber snow farc tout flag; do ffmpeg -y -v error -i work/src/$k.mp4 -vf "fps=1/2,scale=180:320,tile=5x4:padding=3:margin=3" -frames:v 1 -q:v 2 work/qc/${k}_contact.jpg || true; done
cp work/filter.txt output/filter_complex.txt
cp work/qc/final_ffprobe.json output/final_ffprobe.json
cp work/qc/*contact.jpg output/ || true
