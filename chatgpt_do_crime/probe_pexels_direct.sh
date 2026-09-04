#!/usr/bin/env bash
set -euo pipefail
mkdir -p probe/{headers,raw,meta,contacts,stills}

probe_id() {
  local key="$1" id="$2"
  local endpoint="https://www.pexels.com/download/video/${id}/"
  echo "=== ${key} ${endpoint} ==="
  local final
  final=$(curl -LfsS --retry 4 --retry-delay 2 --connect-timeout 20 --max-time 120 \
    -A 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/127 Safari/537.36' \
    -o /dev/null -w '%{url_effective}' "$endpoint" || true)
  printf '%s\n' "$final" > "probe/headers/${key}_redirect.txt"

  if [[ "$final" != https://videos.pexels.com/*.mp4* ]]; then
    echo "No direct Pexels MP4 redirect for ${key}: ${final}" >&2
    return 0
  fi
  printf '%s\n' "$final" > "probe/meta/${key}_selected_url.txt"

  curl -LfsS --retry 6 --retry-delay 2 --connect-timeout 20 --max-time 1200 \
    -A 'Mozilla/5.0' "$final" -o "probe/raw/${key}.mp4"
  test -s "probe/raw/${key}.mp4"

  ffprobe -v error -show_entries \
    format=filename,duration,size,bit_rate:stream=index,codec_name,width,height,r_frame_rate \
    -of json "probe/raw/${key}.mp4" > "probe/meta/${key}.ffprobe.json"
  ffmpeg -y -hide_banner -loglevel error -i "probe/raw/${key}.mp4" \
    -vf "fps=2,scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2:black,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='%{pts\\:hms}':x=7:y=7:fontsize=17:fontcolor=white:borderw=2:bordercolor=black,tile=6x8:padding=3:margin=3:color=black" \
    -frames:v 1 -q:v 2 "probe/contacts/${key}.jpg" || true
  for ts in 0.5 1.5 2.5 3.5 5 7 9 12 15 20; do
    ffmpeg -y -hide_banner -loglevel error -ss "$ts" -i "probe/raw/${key}.mp4" -frames:v 1 \
      -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:black" \
      -q:v 2 "probe/stills/${key}_t${ts}.jpg" || true
  done
  rm -f "probe/raw/${key}.mp4"
}

probe_id robbers_gun_money 7232003
probe_id robber_gun_briefcase 7231264
probe_id robber_station_approach 8102800
probe_id robber_getaway_run 8102795
probe_id robbers_cash_gun_car 8102523

find probe -type f -printf '%P\t%s bytes\n' | sort > probe/meta/manifest.txt
