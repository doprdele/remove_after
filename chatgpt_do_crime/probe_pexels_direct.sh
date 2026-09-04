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

  local candidates=()
  [[ "$final" == http* ]] && candidates+=("$final")
  for fps in 24 25 30 50 60; do
    candidates+=("https://videos.pexels.com/video-files/${id}/${id}-uhd_3840_2160_${fps}fps.mp4")
    candidates+=("https://videos.pexels.com/video-files/${id}/${id}-hd_1920_1080_${fps}fps.mp4")
    candidates+=("https://videos.pexels.com/video-files/${id}/${id}-hd_1280_720_${fps}fps.mp4")
  done

  local n=0 url code ctype size selected=''
  : > "probe/headers/${key}_candidates.tsv"
  for url in "${candidates[@]}"; do
    n=$((n+1))
    read -r code ctype size < <(curl -LIsS --retry 2 --connect-timeout 15 --max-time 45 \
      -A 'Mozilla/5.0' -o /dev/null -w '%{http_code} %{content_type} %{size_download}' "$url" || echo '000 none 0')
    printf '%s\t%s\t%s\t%s\n' "$code" "$ctype" "$size" "$url" >> "probe/headers/${key}_candidates.tsv"
    if [[ "$code" =~ ^2 && "$ctype" == video/* ]]; then
      selected="$url"
      break
    fi
  done

  if [[ -z "$selected" ]]; then
    echo "No direct candidate for ${key}" >&2
    return 0
  fi
  printf '%s\n' "$selected" > "probe/meta/${key}_selected_url.txt"
  curl -LfsS --retry 6 --retry-delay 2 --connect-timeout 20 --max-time 900 \
    -A 'Mozilla/5.0' "$selected" -o "probe/raw/${key}.mp4"
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
probe_id robber_planning_car 8102787
probe_id robber_car_entry 8102788
probe_id robbers_cash_gun_car 8102523

find probe -type f -printf '%P\t%s bytes\n' | sort > probe/meta/manifest.txt
