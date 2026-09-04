#!/usr/bin/env bash
set -euo pipefail

mkdir -p probe/{formats,info,contacts,stills,tmp}
YTDLP=(yt-dlp --no-playlist --force-ipv4 --retries 10 --fragment-retries 10 --socket-timeout 45)

probe_video() {
  local key="$1" id="$2" duration="$3"
  local url="https://www.dailymotion.com/video/${id}"
  echo "=== PROBE ${key} ${url} ==="

  "${YTDLP[@]}" -F "$url" > "probe/formats/${key}.txt" 2>&1 || true
  rm -f "probe/tmp/${key}."* 2>/dev/null || true

  # Review proxy only. Final workflow will retrieve selected ranges at 1080p+.
  if ! "${YTDLP[@]}" --write-info-json --download-sections "*0-${duration}" \
      --force-keyframes-at-cuts \
      -f 'bestvideo[height<=720]+bestaudio/best[height<=720]/best' \
      --merge-output-format mp4 -o "probe/tmp/${key}.%(ext)s" "$url"; then
    echo "Download failed: ${key}" >&2
    return 0
  fi

  local src info
  src=$(find probe/tmp -maxdepth 1 -type f -name "${key}.*" ! -name '*.info.json' ! -name '*.part' | head -n1)
  info=$(find probe/tmp -maxdepth 1 -type f -name "${key}*.info.json" | head -n1)
  [[ -s "$src" ]] || return 0
  [[ -s "$info" ]] && cp "$info" "probe/info/${key}.info.json"

  ffprobe -v error -show_entries \
    format=filename,duration,size,bit_rate:stream=index,codec_name,width,height,r_frame_rate \
    -of json "$src" > "probe/info/${key}.ffprobe.json"

  ffmpeg -y -hide_banner -loglevel error -i "$src" \
    -vf "fps=1/3,scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2:black,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='%{pts\\:hms}':x=7:y=7:fontsize=17:fontcolor=white:borderw=2:bordercolor=black,tile=6x10:padding=3:margin=3:color=black" \
    -frames:v 1 -q:v 2 "probe/contacts/${key}_page0.jpg" || true

  if [[ "$duration" -gt 180 ]]; then
    ffmpeg -y -hide_banner -loglevel error -ss 180 -i "$src" \
      -vf "fps=1/3,scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2:black,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='%{pts\\:hms}':x=7:y=7:fontsize=17:fontcolor=white:borderw=2:bordercolor=black,tile=6x10:padding=3:margin=3:color=black" \
      -frames:v 1 -q:v 2 "probe/contacts/${key}_page1.jpg" || true
  fi

  for ts in 5 15 30 45 60 90 120 150 180 210 240; do
    [[ "$ts" -lt "$duration" ]] || continue
    ffmpeg -y -hide_banner -loglevel error -ss "$ts" -i "$src" -frames:v 1 \
      -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:black" \
      -q:v 2 "probe/stills/${key}_t${ts}.jpg" || true
  done

  rm -f "$src"
}

# Dailymotion upload explicitly titled 4K Ultra HD; use three distinct shots
# from this bank-heist sequence if its format list verifies 1080p or above.
probe_video dark_knight_4k x5khd1 300

# Recent and older protest uploads showing actual U.S. flags being ignited.
probe_video flag_anti_ice_2025 x9l6a1o 150
probe_video flag_brooklyn x8wvzcw 130
probe_video flag_minneapolis_raw x9xdcdk 150
probe_video flag_greece x527tv0 103
probe_video flag_white_house x9phdo2 87

find probe -type f -printf '%P\t%s bytes\n' | sort > probe/info/manifest.txt
