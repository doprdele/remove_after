#!/usr/bin/env bash
set -euo pipefail

mkdir -p work/raw work/src work/audio work/title work/qc output

YTDLP=(yt-dlp --no-playlist --force-ipv4 --retries 3 --fragment-retries 3 --socket-timeout 30 --concurrent-fragments 4 --js-runtimes node --remote-components ejs:github)
VFMT='bestvideo[height>=1080]+bestaudio/best[height>=1080]'
INSTANCES=(
  'https://yewtu.be'
  'https://inv.nadeko.net'
  'https://invidious.nerdvpn.de'
  'https://inv.us.projectsegfau.lt'
)

invidious_json() {
  local id="$1" out="$2"
  for base in "${INSTANCES[@]}"; do
    if curl -fsSL --retry 2 --connect-timeout 12 --max-time 30 "$base/api/v1/videos/$id" -o "$out" \
      && jq -e '.adaptiveFormats and .title' "$out" >/dev/null 2>&1; then
      echo "Invidious source: $base"
      return 0
    fi
  done
  return 1
}

invidious_download_section() {
  local key="$1" id="$2" start="$3" dur="$4"
  local j="work/raw/${key}.invidious.json"
  invidious_json "$id" "$j" || return 1
  local video audio height
  video=$(jq -r '[.adaptiveFormats[] | select(.type|startswith("video/mp4")) | select(.qualityLabel != null) | select((.qualityLabel|capture("(?<n>[0-9]+)").n|tonumber) >= 1080)] | sort_by(.bitrate // 0) | last | .url // empty' "$j")
  height=$(jq -r '[.adaptiveFormats[] | select(.url == $u)][0].qualityLabel // empty' --arg u "$video" "$j")
  audio=$(jq -r '[.adaptiveFormats[] | select(.type|startswith("audio/"))] | sort_by(.bitrate // 0) | last | .url // empty' "$j")
  test -n "$video"
  test -n "$audio"
  echo "$key fallback video quality: $height"
  ffmpeg -y -hide_banner -loglevel warning -ss "$start" -t "$dur" -i "$video" -ss "$start" -t "$dur" -i "$audio" \
    -map 0:v:0 -map 1:a:0 -c:v copy -c:a copy "work/raw/${key}.mkv"
}

get_section() {
  local key="$1" id="$2" start="$3" end="$4" anchor="$5" top="$6" bottom="$7"
  local dur
  dur=$(awk -v a="$start" -v b="$end" 'BEGIN{printf "%.3f", b-a}')
  rm -f "work/raw/${key}."* 2>/dev/null || true
  local url="https://www.youtube.com/watch?v=${id}"
  local ok=0
  for client in web_creator web_embedded android_vr tv web_safari default; do
    rm -f "work/raw/${key}."* 2>/dev/null || true
    echo "Trying $key via yt-dlp client $client"
    if [ "$client" = default ]; then
      if "${YTDLP[@]}" --download-sections "*${start}-${end}" --force-keyframes-at-cuts --write-info-json \
        -f "$VFMT" --merge-output-format mp4 -o "work/raw/${key}.%(ext)s" "$url"; then ok=1; break; fi
    else
      if "${YTDLP[@]}" --extractor-args "youtube:player_client=${client}" \
        --download-sections "*${start}-${end}" --force-keyframes-at-cuts --write-info-json \
        -f "$VFMT" --merge-output-format mp4 -o "work/raw/${key}.%(ext)s" "$url"; then ok=1; break; fi
    fi
  done
  if [ "$ok" -ne 1 ]; then
    echo "yt-dlp failed for $key; trying Invidious"
    invidious_download_section "$key" "$id" "$start" "$dur"
  fi
  local input
  input=$(find work/raw -maxdepth 1 -type f -name "${key}.*" ! -name '*.info.json' ! -name '*.json' ! -name '*.part' | head -n 1)
  test -s "$input"
  ffmpeg -y -hide_banner -loglevel warning -i "$input" -an \
    -vf "crop=iw*0.52:ih*(1-${top}-${bottom}):(iw-iw*0.52)*${anchor}:ih*${top},scale=1080:1920:flags=lanczos,setsar=1,fps=60,format=yuv420p" \
    -c:v libx264 -preset veryfast -crf 18 -profile:v high -movflags +faststart "work/src/${key}.mp4"
  ffprobe -v error -show_entries format=duration,size:stream=width,height,codec_name,r_frame_rate -of json \
    "work/src/${key}.mp4" > "work/qc/${key}.ffprobe.json"
  ffmpeg -y -hide_banner -loglevel error -i "work/src/${key}.mp4" \
    -vf "fps=1/2,scale=180:320,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='%{pts\\:hms}':x=5:y=5:fontsize=14:fontcolor=white:borderw=2:bordercolor=black,tile=6x5:padding=3:margin=3:color=black" \
    -frames:v 1 -q:v 2 "work/qc/${key}_contact.jpg" || true
}

resolve_snow() {
  local query='snow drifting cinematic 4K car'
  local id=''
  id=$(yt-dlp --flat-playlist --playlist-end 15 --print '%(id)s %(duration)s' "ytsearch15:${query}" 2>/dev/null \
    | awk '$2>=45 && $2<=900 {print $1; exit}' || true)
  if [ -z "$id" ]; then
    local encoded
    encoded=$(python -c "import urllib.parse; print(urllib.parse.quote('snow drifting cinematic 4K car'))")
    for base in "${INSTANCES[@]}"; do
      id=$(curl -fsSL --connect-timeout 10 --max-time 25 "$base/api/v1/search?q=$encoded&type=video" 2>/dev/null \
        | jq -r '[.[] | select(.type=="video") | select(.lengthSeconds>=45 and .lengthSeconds<=900)][0].videoId // empty' || true)
      [ -n "$id" ] && break
    done
  fi
  test -n "$id"
  echo "$id"
}

# Previously screened source IDs and clean ranges.
get_section cash_luxury Hl5_Lc6b3AU 64 88 0.50 0.03 0.07
get_section farc_training M1OTlP9CV4g 16 34 0.50 0.04 0.13
get_section flag_burning F1M8THQEROk 8 38 0.50 0.04 0.13
get_section authentic_cyberdeck Vb0fdJsjy64 370 450 0.50 0.04 0.10
get_section tout_va_bien_supermarket AxM9rOVGQO4 1380 1440 0.28 0.03 0.15
snow_id=$(resolve_snow)
echo "$snow_id" > work/qc/snow_video_id.txt
get_section snow_drift "$snow_id" 12 47 0.50 0.03 0.07

# Soundtrack supplied by the user.
track_id='sUidFU1nPr8'
track='https://www.youtube.com/watch?v=sUidFU1nPr8'
audio_ok=0
for client in web_creator web_embedded android_vr tv web_safari default; do
  rm -f work/audio/raya_source.* 2>/dev/null || true
  echo "Trying soundtrack via yt-dlp client $client"
  if [ "$client" = default ]; then
    if "${YTDLP[@]}" -f 'bestaudio/best' -x --audio-format m4a --audio-quality 0 \
      -o 'work/audio/raya_source.%(ext)s' "$track"; then audio_ok=1; break; fi
  else
    if "${YTDLP[@]}" --extractor-args "youtube:player_client=${client}" -f 'bestaudio/best' -x \
      --audio-format m4a --audio-quality 0 -o 'work/audio/raya_source.%(ext)s' "$track"; then audio_ok=1; break; fi
  fi
done
if [ "$audio_ok" -ne 1 ]; then
  j=work/raw/track.invidious.json
  invidious_json "$track_id" "$j"
  audio_url=$(jq -r '[.adaptiveFormats[] | select(.type|startswith("audio/"))] | sort_by(.bitrate // 0) | last | .url // empty' "$j")
  test -n "$audio_url"
  ffmpeg -y -hide_banner -loglevel warning -i "$audio_url" -vn -c:a aac -b:a 256k work/audio/raya_source.m4a
fi
audio=$(find work/audio -maxdepth 1 -type f -name 'raya_source.*' ! -name '*.part' | head -n 1)
ffmpeg -y -hide_banner -loglevel warning -i "$audio" -vn -c:a aac -b:a 256k -ar 48000 -ac 2 work/audio/raya_phonk.m4a

# Clean, grain-free Godard/EVA title cards. GFS Didot is the closest installed
# serif to the requested Montisse/Matisse look on the runner.
python <<'PY'
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
W,H=1080,1920
out=Path('work/title'); out.mkdir(parents=True,exist_ok=True)
fonts=[Path('/usr/share/fonts/opentype/didot/GFSDidotBold.otf'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf')]
fp=next(p for p in fonts if p.exists())
phrase='DO CRIME. DON’T VOTE  DO CRIME. DON’T VOTE'
rows=12; rh=H//rows
font=ImageFont.truetype(str(fp),154)
probe=Image.new('L',(4200,400),0); d=ImageDraw.Draw(probe)
box=d.textbbox((0,0),phrase,font=font); d.text((-box[0],-box[1]),phrase,fill=255,font=font)
mask=probe.crop(probe.getbbox()).resize((W,rh),Image.Resampling.LANCZOS)
palettes=[(('#1114C7','#DAFF00'),('#FF006E','#FFF4D6')),(('#DAFF00','#0A0A0A'),('#1114C7','#FF006E')),(('#FF006E','#FFF4D6'),('#0A0A0A','#DAFF00')),(('#FFF4D6','#1114C7'),('#DAFF00','#FF006E'))]
for ci,pairs in enumerate(palettes,1):
    canvas=Image.new('RGB',(W,H),pairs[0][0])
    for row in range(rows):
        bg,fg=pairs[(row+ci-1)%2]
        band=Image.new('RGB',(W,rh),bg); ink=Image.new('RGB',(W,rh),fg)
        band.paste(ink,(0,0),mask); canvas.paste(band,(0,row*rh))
    canvas.save(out/f'title_{ci}.png',optimize=True)
PY

# Build 55 equal eighth-note picture slots: 15 sec / 55 = 0.272727 sec.
python <<'PY'
from pathlib import Path
SLOT=3/11
N=55
categories=['cash','cyber','snow','farc','tout','cash','flag','cyber','snow','cash','tout','farc','cyber','flag','snow','tout','cash','cyber','farc','snow','flag','cash','tout','cyber']
idx={'cash':0,'farc':1,'flag':2,'cyber':3,'tout':4,'snow':5}
durations={'cash':24,'farc':18,'flag':30,'cyber':80,'tout':60,'snow':35}
cues={k:[.35+i*1.13 for i in range(max(8,int(durations[k]//1.13)-2))] for k in durations}
speed=[.70,1.35,2.55,.62,1.85,3.05,1.00,2.25,.82,1.55,2.80,.68]
counts={k:0 for k in idx}
parts=[]; labels=[]
for i in range(N):
    cat=categories[i%len(categories)]; ci=idx[cat]
    cue=cues[cat][counts[cat]%len(cues[cat])]; counts[cat]+=1
    sp=speed[i%len(speed)]; srcdur=SLOT*sp
    zoom=1.035+(i%5)*.012
    sw=round(1080*zoom); sh=round(1920*zoom)
    x=max(0,(sw-1080)//2 + ((i%3)-1)*12); y=max(0,(sh-1920)//2 + ((i%4)-2)*8)
    chain=f'[{ci}:v]trim=start={cue:.4f}:end={cue+srcdur:.4f},setpts=(PTS-STARTPTS)/{sp:.5f},fps=60,scale={sw}:{sh}:flags=bicubic,crop=1080:1920:{x}:{y}'
    if i in {7,16,29,43,50}:
        chain+=',loop=loop=2:size=2:start=3,trim=duration=0.272727,setpts=PTS-STARTPTS'
    chain+=f',format=yuv420p[s{i}]'
    parts.append(chain); labels.append(f'[s{i}]')
parts.append(''.join(labels)+f'concat=n={N}:v=1:a=0[base]')
parts.append("[base]eq=contrast=1.28:saturation=1.42:brightness=-0.035,rgbashift=rh=9:bh=-9:rv=2:bv=-2,noise=alls=10:allf=t+u,drawgrid=w=1080:h=4:t=1:c=black@0.25,unsharp=5:5:0.8:5:5:0.0[fx0]")
neg='+'.join(f'between(t,{t:.4f},{t+.0334:.4f})' for t in [1.091,2.455,3.818,5.455,8.455,9.545,11.455,12.545,14.182])
white='+'.join(f'between(t,{t:.4f},{t+.0334:.4f})' for t in [3.273,5.727,8.727,11.727,14.455])
parts.append(f"[fx0]negate=enable='{neg}',drawbox=x=0:y=0:w=iw:h=ih:color=white@1:t=fill:enable='{white}'[fx1]")
parts.append('[fx1]split=4[main][a][b][c]')
parts.append("[a]format=rgba,crop=1080:110:0:350,pad=1080:1920:0:350:color=black@0[ta]")
parts.append("[b]format=rgba,crop=1080:90:0:930,pad=1080:1920:0:930:color=black@0[tb]")
parts.append("[c]format=rgba,crop=1080:130:0:1450,pad=1080:1920:0:1450:color=black@0[tc]")
tear1='+'.join(f'between(t,{t:.4f},{t+.08:.4f})' for t in [2.18,5.18,8.18,11.18,13.64])
tear2='+'.join(f'between(t,{t:.4f},{t+.06:.4f})' for t in [3.00,6.00,9.00,12.00])
tear3='+'.join(f'between(t,{t:.4f},{t+.07:.4f})' for t in [4.09,7.09,10.09,13.09])
parts.append(f"[main][ta]overlay=x=65:y=0:enable='{tear1}'[o1]")
parts.append(f"[o1][tb]overlay=x=-55:y=0:enable='{tear2}'[o2]")
parts.append(f"[o2][tc]overlay=x=78:y=0:enable='{tear3}'[o3]")
title_slots=[(0,7),(20,8),(40,9),(54,10)]
prev='o3'
for n,(slot,input_idx) in enumerate(title_slots,1):
    st=slot*SLOT; en=(slot+1)*SLOT
    parts.append(f'[{prev}][{input_idx}:v]overlay=x=0:y=0:enable=between(t\\,{st:.6f}\\,{en:.6f})[t{n}]')
    prev=f't{n}'
parts.append(f'[{prev}]trim=duration=15,setpts=PTS-STARTPTS[outv]')
Path('work/filter.txt').write_text(';\n'.join(parts)+'\n')
PY

# Selected track window from the earlier timing analysis: 44.742-59.742 s.
ffmpeg -y -hide_banner -loglevel warning \
  -i work/src/cash_luxury.mp4 \
  -i work/src/farc_training.mp4 \
  -i work/src/flag_burning.mp4 \
  -i work/src/authentic_cyberdeck.mp4 \
  -i work/src/tout_va_bien_supermarket.mp4 \
  -i work/src/snow_drift.mp4 \
  -ss 44.742 -i work/audio/raya_phonk.m4a \
  -loop 1 -framerate 60 -i work/title/title_1.png \
  -loop 1 -framerate 60 -i work/title/title_2.png \
  -loop 1 -framerate 60 -i work/title/title_3.png \
  -loop 1 -framerate 60 -i work/title/title_4.png \
  -filter_complex_script work/filter.txt \
  -map '[outv]' -map 6:a:0 -t 15 -frames:v 900 \
  -c:v libx264 -preset medium -crf 17 -maxrate 16M -bufsize 32M \
  -profile:v high -level:v 4.2 -pix_fmt yuv420p -r 60 -g 60 -keyint_min 60 -sc_threshold 0 \
  -color_primaries bt709 -color_trc bt709 -colorspace bt709 \
  -c:a aac -b:a 256k -ar 48000 -ac 2 \
  -af 'afade=t=in:st=0:d=.012,afade=t=out:st=14.93:d=.07,alimiter=limit=.97' \
  -movflags +faststart output/do_crime_dont_vote_reel.mp4

ffprobe -v error -count_frames -show_entries \
  format=duration,size,bit_rate:stream=index,codec_type,codec_name,profile,width,height,pix_fmt,r_frame_rate,avg_frame_rate,sample_rate,channels,duration,nb_frames,nb_read_frames \
  -of json output/do_crime_dont_vote_reel.mp4 | tee work/qc/final_ffprobe.json
ffmpeg -v error -i output/do_crime_dont_vote_reel.mp4 -f null -
ffmpeg -y -hide_banner -loglevel error -i output/do_crime_dont_vote_reel.mp4 \
  -vf "fps=4/3,scale=216:384,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='%{pts\\:hms}':x=5:y=5:fontsize=14:fontcolor=white:borderw=2:bordercolor=black,tile=5x4:padding=4:margin=4:color=black" \
  -frames:v 1 -q:v 2 work/qc/final_contact_sheet.jpg

python <<'PY'
import json
d=json.load(open('work/qc/final_ffprobe.json'))
streams={s['codec_type']:s for s in d['streams']}; v=streams['video']; a=streams['audio']; e=[]
if abs(float(d['format']['duration'])-15)>.025:e.append('duration')
if (v.get('width'),v.get('height'))!=(1080,1920):e.append('resolution')
if v.get('codec_name')!='h264':e.append('video_codec')
if v.get('pix_fmt')!='yuv420p':e.append('pix_fmt')
if v.get('r_frame_rate')!='60/1':e.append('fps')
if int(v.get('nb_read_frames') or v.get('nb_frames') or 0)!=900:e.append('frames')
if a.get('codec_name')!='aac':e.append('audio_codec')
if a.get('sample_rate')!='48000':e.append('sample_rate')
if e: raise SystemExit('QC FAILED: '+','.join(e))
print('QC PASSED')
PY

cp work/filter.txt output/filter_complex.txt
cp work/qc/final_ffprobe.json output/final_ffprobe.json
cp work/qc/final_contact_sheet.jpg output/final_contact_sheet.jpg
cp work/qc/*_contact.jpg output/ || true
cp work/qc/snow_video_id.txt output/
