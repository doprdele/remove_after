#!/usr/bin/env bash
set -euo pipefail

mkdir -p probe/{pages,meta,raw,contacts,stills}

fetch_pexels() {
  local key="$1" id="$2" slug="$3"
  local page="https://www.pexels.com/video/${slug}-${id}/"
  echo "=== ${key} :: ${page} ==="
  curl -LfsS --retry 6 --retry-delay 2 --connect-timeout 20 --max-time 120 \
    -A 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/127 Safari/537.36' \
    "$page" -o "probe/pages/${key}.html"

  python - "$key" "$id" <<'PY'
from pathlib import Path
import html,re,sys,json
key,id=sys.argv[1:]
s=html.unescape(Path(f'probe/pages/{key}.html').read_text(errors='ignore'))
urls=[]
for u in re.findall(r'https://videos\.pexels\.com/video-files/[^"\\\s<]+?\.mp4(?:\?[^"\\\s<]*)?',s):
    u=u.replace('\\u0026','&').replace('\\/','/')
    if u not in urls: urls.append(u)
# Prefer assets explicitly named UHD/4K, then 1920x1080, then largest URL by apparent dimensions.
def score(u):
    m=re.search(r'(\d{3,4})_(\d{3,4})',u)
    dims=(int(m.group(1))*int(m.group(2))) if m else 0
    return (('uhd' in u.lower()) or ('4k' in u.lower()), dims, len(u))
urls.sort(key=score,reverse=True)
Path(f'probe/meta/{key}_urls.json').write_text(json.dumps(urls,indent=2))
if not urls: raise SystemExit(f'no MP4 URL found for {key}')
Path(f'probe/meta/{key}_selected_url.txt').write_text(urls[0]+'\n')
print(urls[0])
PY

  local url
  url=$(head -n1 "probe/meta/${key}_selected_url.txt")
  curl -LfsS --retry 6 --retry-delay 2 --connect-timeout 20 --max-time 900 \
    "$url" -o "probe/raw/${key}.mp4"
  test -s "probe/raw/${key}.mp4"

  ffprobe -v error -show_entries \
    format=filename,duration,size,bit_rate:stream=index,codec_name,width,height,r_frame_rate \
    -of json "probe/raw/${key}.mp4" > "probe/meta/${key}.ffprobe.json"

  ffmpeg -y -hide_banner -loglevel error -i "probe/raw/${key}.mp4" \
    -vf "fps=2,scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2:black,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='%{pts\\:hms}':x=7:y=7:fontsize=17:fontcolor=white:borderw=2:bordercolor=black,tile=6x6:padding=3:margin=3:color=black" \
    -frames:v 1 -q:v 2 "probe/contacts/${key}.jpg" || true

  for ts in 0.5 1.5 2.5 3.5 5 7 9 12; do
    ffmpeg -y -hide_banner -loglevel error -ss "$ts" -i "probe/raw/${key}.mp4" \
      -frames:v 1 -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:black" \
      -q:v 2 "probe/stills/${key}_t${ts}.jpg" || true
  done
  rm -f "probe/raw/${key}.mp4"
}

fetch_pexels robbers_gun_money 7232003 robbers-holding-a-gun-and-money
fetch_pexels robber_gun_briefcase 7231264 person-in-a-mask-holding-a-gun-and-a-briefcase
fetch_pexels robber_station_approach 8102800 a-robber-man-walking-bringing-a-gun-while-going-to-steal-a-gasoline-station
fetch_pexels robber_getaway_run 8102795 a-robber-man-running-fast-while-bringing-the-stolen-money
fetch_pexels robber_planning_car 8102787 a-criminal-man-bringing-a-gun-to-robbed-a-petrol-station
fetch_pexels robber_car_entry 8102788 a-robber-carrying-a-duffle-bag-while-entering-a-car
fetch_pexels robbers_cash_gun_car 8102523 a-couple-inside-a-car-counting-money-and-cleaning-a-gun

find probe -type f -printf '%P\t%s bytes\n' | sort > probe/meta/manifest.txt
