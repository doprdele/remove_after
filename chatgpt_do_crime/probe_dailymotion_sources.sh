#!/usr/bin/env bash
set -euo pipefail

mkdir -p probe/{search,meta,raw,contacts}
YTDLP=(yt-dlp --no-playlist --retries 8 --fragment-retries 8 --socket-timeout 45)

urlencode() {
  python - "$1" <<'PY'
import sys, urllib.parse
print(urllib.parse.quote(sys.argv[1], safe=''))
PY
}

search_dm() {
  local key="$1" query="$2" limit="${3:-6}"
  local encoded
  encoded=$(urlencode "$query")
  curl -LfsS --retry 5 --retry-delay 2 --connect-timeout 20 --max-time 90 \
    "https://api.dailymotion.com/videos?search=${encoded}&fields=id,title,duration,owner.screenname,thumbnail_720_url&limit=${limit}" \
    -o "probe/search/${key}.json"
  jq -e '.list and (.list|type=="array")' "probe/search/${key}.json" >/dev/null
}

probe_query() {
  local key="$1" query="$2" count="${3:-3}"
  search_dm "$key" "$query" 10 || return 0
  jq -r '.list[] | [.id,.title,(.duration//0),(."owner.screenname"//"")] | @tsv' \
    "probe/search/${key}.json" | head -n "$count" > "probe/meta/${key}.tsv"

  local rank=0 id title duration owner stem src
  while IFS=$'\t' read -r id title duration owner; do
    [[ -n "$id" ]] || continue
    rank=$((rank+1))
    stem="${key}_${rank}_${id}"
    echo "PROBE ${stem}: ${title}"
    rm -f "probe/raw/${stem}."* 2>/dev/null || true

    # Keep the first 180 seconds, enough to locate action in scene-specific uploads.
    if ! "${YTDLP[@]}" --write-info-json --download-sections '*0-180' \
      --force-keyframes-at-cuts -f 'bestvideo[height>=720]+bestaudio/best[height>=720]/best' \
      --merge-output-format mp4 -o "probe/raw/${stem}.%(ext)s" \
      "https://www.dailymotion.com/video/${id}"; then
      echo "download failed: ${stem}" >&2
      continue
    fi

    src=$(find probe/raw -maxdepth 1 -type f -name "${stem}.*" ! -name '*.info.json' ! -name '*.part' | head -n1)
    [[ -s "$src" ]] || continue

    ffprobe -v error -show_entries \
      format=filename,duration,size,bit_rate:stream=index,codec_name,width,height,r_frame_rate \
      -of json "$src" > "probe/meta/${stem}.ffprobe.json" || true
    printf '%s\t%s\t%s\t%s\t%s\n' "$stem" "$id" "$duration" "$title" "$owner" \
      >> probe/meta/candidates.tsv

    ffmpeg -y -hide_banner -loglevel error -i "$src" \
      -vf "fps=1/4,scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2:black,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='%{pts\\:hms}':x=7:y=7:fontsize=17:fontcolor=white:borderw=2:bordercolor=black,tile=6x8:padding=3:margin=3:color=black" \
      -frames:v 1 -q:v 2 "probe/contacts/${stem}.jpg" || true

    # Preserve representative stills at 10, 35, 70, 110 and 150 seconds.
    for ts in 10 35 70 110 150; do
      ffmpeg -y -hide_banner -loglevel error -ss "$ts" -i "$src" -frames:v 1 \
        -vf "scale=960:540:force_original_aspect_ratio=decrease,pad=960:540:(ow-iw)/2:(oh-ih)/2:black" \
        -q:v 2 "probe/contacts/${stem}_t${ts}.jpg" || true
    done

    rm -f "$src"
  done < "probe/meta/${key}.tsv"
}

: > probe/meta/candidates.tsv
probe_query bank_dark_knight 'The Dark Knight bank robbery scene' 4
probe_query bank_heat 'Heat bank robbery scene' 4
probe_query bank_town 'The Town bank robbery scene' 4
probe_query bank_point_break 'Point Break bank robbery scene' 3
probe_query bank_inside_man 'Inside Man bank robbery scene' 3
probe_query bank_generic 'armed bank robbery movie scene' 4
probe_query flag_revolution_club 'Revolution Club burns American flag White House' 4
probe_query flag_left_protest 'left wing protesters burn American flag' 4
probe_query flag_antifa 'antifa burns American flag protest' 4

find probe -type f -printf '%P\t%s bytes\n' | sort > probe/meta/manifest.txt
cat probe/meta/candidates.tsv
