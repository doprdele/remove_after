#!/usr/bin/env bash
set -euo pipefail
mkdir -p work/raw work/src work/audio work/title work/qc output
fetch() { echo "FETCH $2"; curl -LfsS --retry 4 --retry-delay 2 --connect-timeout 15 --max-time 300 "$1" -o "$2"; test -s "$2"; }
fetch 'https://www.pexels.com/download/video/3196002/' work/raw/cash.mp4
fetch 'https://www.pexels.com/download/video/6157913/' work/raw/luxury.mp4
fetch 'https://www.pexels.com/download/video/36628017/' work/raw/cyber.mp4
fetch 'https://www.pexels.com/download/video/6833872/' work/raw/snow.mp4
fetch 'https://commons.wikimedia.org/wiki/Special:Redirect/file/DNC_Day_4-_Protesters_Attempt_To_Burn_A_Flag.webm' work/raw/flag.webm
fetch 'https://dnznrvs05pmza.cloudfront.net/gemini/gemini-3-pro-image/images/afd11171-8735-48b3-a939-6819b519a28c/Single_photorealistic_documentary_frame__Colombian_Marxist_g.png?_jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJrZXlIYXNoIjoiM2FjNTFkYTBhMTZmOTU5MyIsImJ1Y2tldCI6InJ1bndheS10YXNrLWFydGlmYWN0cyIsInN0YWdlIjoicHJvZCIsImV4cCI6MTc4ODY1MjcwNH0.RoACRkGaGZpsNwLZX4Gz4LUi0w53cpy65nFhPnws90c' work/raw/farc1.png
fetch 'https://dnznrvs05pmza.cloudfront.net/gemini/gemini-3-pro-image/images/4a2d0121-248a-424b-a1ba-5eb3bc77caee/Single_photorealistic_documentary_frame__Colombian_Marxist_g.png?_jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJrZXlIYXNoIjoiMzM4Nzc2OWEyMTc3MzVmYSIsImJ1Y2tldCI6InJ1bndheS10YXNrLWFydGlmYWN0cyIsInN0YWdlIjoicHJvZCIsImV4cCI6MTc4ODY1MDEzOH0.TpPg51bqbIdr1hrlonLrNdC3gX02mOK2bs5KcZYB_kg' work/raw/farc2.png
fetch 'https://blogger.googleusercontent.com/img/b/R29vZ2xl/AVvXsEhwpLzuBN8_34_vp-D4gYR_rX3PdXnbI1dsgdtHtJk3IA2usnxrvZB3GLW7qdhSdvTkA0IIcHE7PG9xiXvOt-_GFR5vj0PiPSNo4X0I2renYG3st07fGTrZPm49TrMC1lDci7FcB12DrVE/s0/Screen%2Bshot%2B2010-11-27%2Bat%2B4.57.32%2BPM.png' work/raw/tout.png

# Exact Raya (Slowed) track. The official Audiomack page currently returns a
# stale API 404 to yt-dlp, so retry an identical artist-attributed mirror upload.
audio_ok=0
for u in 'https://audiomack.com/zericxxn/song/raya-slowed' 'https://audiomack.com/darwin_10/song/raya-slowed'; do
  rm -f work/audio/raya_source.* 2>/dev/null || true
  if yt-dlp --no-playlist --retries 5 --socket-timeout 45 -f 'bestaudio/best' -x --audio-format m4a --audio-quality 0 -o 'work/audio/raya_source.%(ext)s' "$u"; then audio_ok=1; break; fi
done
test "$audio_ok" -eq 1
audio=$(find work/audio -type f -name 'raya_source.*' ! -name '*.part' | head -n1)
ffmpeg -y -v warning -i "$audio" -vn -c:a aac -b:a 256k -ar 48000 -ac 2 work/audio/raya.m4a

{
 for f in work/raw/cash.mp4 work/raw/luxury.mp4 work/raw/cyber.mp4 work/raw/snow.mp4 work/raw/flag.webm; do echo "=== $f ==="; ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height,r_frame_rate:format=duration -of default=nw=1 "$f" || true; done
 python - <<'PY'
from PIL import Image
for p in ['work/raw/farc1.png','work/raw/farc2.png','work/raw/tout.png']:
 im=Image.open(p); print(p, im.size)
PY
} | tee work/qc/source_dimensions.txt

norm() { key="$1"; in="$2"; x="$3"; top="$4"; bottom="$5"; ffmpeg -y -v warning -i "$in" -an -vf "crop=iw*0.54:ih*(1-${top}-${bottom}):(iw-iw*0.54)*${x}:ih*${top},scale=1080:1920:flags=lanczos,setsar=1,fps=60,format=yuv420p" -t 18 -c:v libx264 -preset veryfast -crf 18 -profile:v high "work/src/${key}.mp4"; }
norm cash work/raw/cash.mp4 0.50 0.03 0.06
norm luxury work/raw/luxury.mp4 0.50 0.03 0.06
norm cyber work/raw/cyber.mp4 0.50 0.03 0.06
norm snow work/raw/snow.mp4 0.50 0.03 0.06
norm flag work/raw/flag.webm 0.50 0.05 0.13
ffmpeg -y -v warning -loop 1 -framerate 60 -i work/raw/farc1.png -loop 1 -framerate 60 -i work/raw/farc2.png -filter_complex "[0:v]scale=2000:-2:flags=lanczos,zoompan=z='1.06+0.00045*on':x='iw/2-(iw/zoom/2)+on*0.55':y='ih/2-(ih/zoom/2)':d=360:s=1080x1920:fps=60,setsar=1[f0];[1:v]scale=2000:-2:flags=lanczos,zoompan=z='1.20-0.00035*on':x='iw/2-(iw/zoom/2)-on*0.35':y='ih/2-(ih/zoom/2)':d=360:s=1080x1920:fps=60,setsar=1[f1];[f0][f1]concat=n=2:v=1:a=0,format=yuv420p" -t 12 -c:v libx264 -preset veryfast -crf 17 work/src/farc.mp4
ffmpeg -y -v warning -loop 1 -framerate 60 -i work/raw/tout.png -vf "scale=2300:-2:flags=lanczos,zoompan=z='1.10+0.00028*on':x='iw/2-(iw/zoom/2)+sin(on/45)*90':y='ih/2-(ih/zoom/2)':d=720:s=1080x1920:fps=60,setsar=1,format=yuv420p" -t 12 -c:v libx264 -preset veryfast -crf 17 work/src/tout.mp4
python - <<'PY'
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
W,H=1080,1920; rows=12; rh=H//rows
fp=next(p for p in [Path('/usr/share/fonts/opentype/didot/GFSDidotBold.otf'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf')] if p.exists())
font=ImageFont.truetype(str(fp),154); phrase='DO CRIME. DON’T VOTE  DO CRIME. DON’T VOTE'
probe=Image.new('L',(5000,400)); d=ImageDraw.Draw(probe); b=d.textbbox((0,0),phrase,font=font); d.text((-b[0],-b[1]),phrase,font=font,fill=255); mask=probe.crop(probe.getbbox()).resize((W,rh),Image.Resampling.LANCZOS)
pals=[(('#1015C7','#E5FF00'),('#FF0A78','#FFF4DA')),(('#E5FF00','#090909'),('#1015C7','#FF0A78')),(('#FF0A78','#FFF4DA'),('#090909','#E5FF00')),(('#FFF4DA','#1015C7'),('#E5FF00','#FF0A78'))]
out=Path('work/title');out.mkdir(exist_ok=True)
for ci,pairs in enumerate(pals):
 c=Image.new('RGB',(W,H),pairs[0][0])
 for r in range(rows):
  bg,fg=pairs[(r+ci)%2]; band=Image.new('RGB',(W,rh),bg); ink=Image.new('RGB',(W,rh),fg); band.paste(ink,(0,0),mask); c.paste(band,(0,r*rh))
 c.save(out/f'title{ci}.png')
PY
python - <<'PY'
from pathlib import Path
S=3/11;N=55;cats=['cash','luxury','cyber','snow','farc','tout','flag','cyber','cash','snow','farc','tout','luxury','flag','cyber','snow','cash','farc','tout'];idx={'cash':0,'luxury':1,'cyber':2,'snow':3,'farc':4,'tout':5,'flag':6};counts={k:0 for k in idx};speed=[.72,1.33,2.55,.61,1.82,2.95,1,2.18,.84,1.56,2.72,.68];parts=[];labels=[]
for i in range(N):
 cat=cats[i%len(cats)];c=counts[cat];counts[cat]+=1;cue=(.25+c*1.07)%9.7;sp=speed[i%len(speed)];need=S*sp;zoom=1.035+(i%5)*.014;sw=round(1080*zoom);sh=round(1920*zoom);x=max(0,(sw-1080)//2+((i%3)-1)*11);y=max(0,(sh-1920)//2+((i%4)-2)*7);chain=f'[{idx[cat]}:v]trim=start={cue:.5f}:end={cue+need:.5f},setpts=(PTS-STARTPTS)/{sp:.5f},fps=60,scale={sw}:{sh}:flags=bicubic,crop=1080:1920:{x}:{y}';chain+=f',format=yuv420p[s{i}]';parts.append(chain);labels.append(f'[s{i}]')
parts.append(''.join(labels)+f'concat=n={N}:v=1:a=0[base]');parts.append("[base]eq=contrast=1.31:saturation=1.48:brightness=-0.035,rgbashift=rh=12:bh=-12:rv=3:bv=-3,noise=alls=12:allf=t+u,drawgrid=w=1080:h=4:t=1:c=black@0.28,unsharp=5:5:0.9:5:5:0[fx0]");neg='+'.join(f'between(t,{t:.4f},{t+.0334:.4f})' for t in [1.091,2.455,3.818,5.455,8.455,9.545,11.455,12.545,14.182]);white='+'.join(f'between(t,{t:.4f},{t+.0334:.4f})' for t in [3.273,5.727,8.727,11.727,14.455]);parts.append(f"[fx0]negate=enable='{neg}',drawbox=x=0:y=0:w=iw:h=ih:color=white@1:t=fill:enable='{white}'[fx1]");parts.append('[fx1]split=4[m][a][b][c]');parts.append('[a]format=rgba,crop=1080:105:0:335,pad=1080:1920:0:335:color=black@0[ta]');parts.append('[b]format=rgba,crop=1080:88:0:915,pad=1080:1920:0:915:color=black@0[tb]');parts.append('[c]format=rgba,crop=1080:125:0:1435,pad=1080:1920:0:1435:color=black@0[tc]');e1='+'.join(f'between(t,{t:.4f},{t+.080:.4f})' for t in [2.18,5.18,8.18,11.18,13.64]);e2='+'.join(f'between(t,{t:.4f},{t+.065:.4f})' for t in [3,6,9,12]);e3='+'.join(f'between(t,{t:.4f},{t+.070:.4f})' for t in [4.09,7.09,10.09,13.09]);parts.append(f"[m][ta]overlay=x=72:y=0:enable='{e1}'[o1]");parts.append(f"[o1][tb]overlay=x=-58:y=0:enable='{e2}'[o2]");parts.append(f"[o2][tc]overlay=x=86:y=0:enable='{e3}'[o3]");prev='o3'
for n,(inp,slot) in enumerate(zip([8,9,10,11],[0,20,40,54]),1):
 st=slot*S;en=(slot+1)*S;parts.append(f'[{prev}][{inp}:v]overlay=0:0:enable=between(t\\,{st:.6f}\\,{en:.6f})[t{n}]');prev=f't{n}'
parts.append(f'[{prev}]trim=duration=15,setpts=PTS-STARTPTS[outv]');Path('work/filter.txt').write_text(';\n'.join(parts)+'\n')
PY
ffmpeg -y -hide_banner -loglevel warning -i work/src/cash.mp4 -i work/src/luxury.mp4 -i work/src/cyber.mp4 -i work/src/snow.mp4 -i work/src/farc.mp4 -i work/src/tout.mp4 -i work/src/flag.mp4 -ss 44.742 -i work/audio/raya.m4a -loop 1 -framerate 60 -i work/title/title0.png -loop 1 -framerate 60 -i work/title/title1.png -loop 1 -framerate 60 -i work/title/title2.png -loop 1 -framerate 60 -i work/title/title3.png -filter_complex_script work/filter.txt -map '[outv]' -map 7:a:0 -frames:v 900 -t 15 -c:v libx264 -preset medium -crf 17 -maxrate 16M -bufsize 32M -profile:v high -level:v 4.2 -pix_fmt yuv420p -r 60 -g 60 -keyint_min 60 -sc_threshold 0 -color_primaries bt709 -color_trc bt709 -colorspace bt709 -c:a aac -b:a 256k -ar 48000 -ac 2 -af 'afade=t=in:st=0:d=.012,afade=t=out:st=14.93:d=.07,alimiter=limit=.97' -movflags +faststart output/do_crime_dont_vote_reel.mp4
ffprobe -v error -count_frames -show_entries format=duration,size,bit_rate:stream=index,codec_type,codec_name,profile,width,height,pix_fmt,r_frame_rate,avg_frame_rate,sample_rate,channels,duration,nb_frames,nb_read_frames -of json output/do_crime_dont_vote_reel.mp4 | tee work/qc/final_ffprobe.json
ffmpeg -v error -i output/do_crime_dont_vote_reel.mp4 -f null -
ffmpeg -y -v error -i output/do_crime_dont_vote_reel.mp4 -vf "fps=4/3,scale=216:384,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='%{pts\\:hms}':x=5:y=5:fontsize=14:fontcolor=white:borderw=2:bordercolor=black,tile=5x4:padding=4:margin=4:color=black" -frames:v 1 -q:v 2 work/qc/final_contact_sheet.jpg
for key in cash luxury cyber snow farc tout flag; do ffmpeg -y -v error -i "work/src/$key.mp4" -vf 'fps=1/2,scale=180:320,tile=6x5:padding=3:margin=3:color=black' -frames:v 1 -q:v 2 "work/qc/${key}_contact.jpg" || true; done
python - <<'PY'
import json
d=json.load(open('work/qc/final_ffprobe.json'));s={x['codec_type']:x for x in d['streams']};v=s['video'];a=s['audio'];e=[]
if abs(float(d['format']['duration'])-15)>.025:e.append('duration')
if (v.get('width'),v.get('height'))!=(1080,1920):e.append('resolution')
if v.get('codec_name')!='h264' or v.get('pix_fmt')!='yuv420p':e.append('video')
if v.get('r_frame_rate')!='60/1':e.append('fps')
if int(v.get('nb_read_frames') or v.get('nb_frames') or 0)!=900:e.append('frames')
if a.get('codec_name')!='aac' or a.get('sample_rate')!='48000':e.append('audio')
if e:raise SystemExit('QC FAILED '+','.join(e))
print('QC PASSED')
PY
cp work/filter.txt work/qc/source_dimensions.txt work/qc/final_ffprobe.json work/qc/final_contact_sheet.jpg output/
cp work/qc/*_contact.jpg output/ || true
