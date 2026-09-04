#!/usr/bin/env bash
set -euo pipefail

mkdir -p probe/{search,meta,clips,contacts}

PIPED_APIS=(
  "https://pipedapi.kavin.rocks"
  "https://pipedapi.adminforge.de"
  "https://pipedapi.reallyaweso.me"
  "https://pipedapi.moomoo.me"
  "https://api-piped.mha.fi"
  "https://piped-api.garudalinux.org"
  "https://pipedapi.syncpundit.io"
  "https://pipedapi.tokhmi.xyz"
)

urlencode() {
  python - "$1" <<'PY'
import sys, urllib.parse
print(urllib.parse.quote(sys.argv[1], safe=''))
PY
}

piped_search() {
  local key="$1" query="$2"
  local encoded base tmp
  encoded=$(urlencode "$query")
  tmp="probe/search/${key}.json"
  : > "$tmp"
  for base in "${PIPED_APIS[@]}"; do
    echo "Trying Piped search ${base} :: ${query}"
    if curl -LfsS --retry 2 --connect-timeout 12 --max-time 45 \
      -A 'Mozilla/5.0' "${base}/search?q=${encoded}&filter=videos" -o "${tmp}.part"; then
      if jq -e '(.items // .) | type == "array"' "${tmp}.part" >/dev/null 2>&1; then
        mv "${tmp}.part" "$tmp"
        printf '%s\n' "$base" > "probe/search/${key}.api.txt"
        return 0
      fi
    fi
  done
  echo "No Piped search instance succeeded for ${query}" >&2
  return 1
}

piped_streams() {
  local id="$1" out="$2" preferred="${3:-}"
  local base
  if [[ -n "$preferred" ]]; then
    if curl -LfsS --retry 2 --connect-timeout 12 --max-time 45 \
      -A 'Mozilla/5.0' "${preferred}/streams/${id}" -o "${out}.part" && \
      jq -e '.videoStreams and (.videoStreams|length>0)' "${out}.part" >/dev/null 2>&1; then
      mv "${out}.part" "$out"
      return 0
    fi
  fi
  for base in "${PIPED_APIS[@]}"; do
    [[ "$base" == "$preferred" ]] && continue
    echo "Trying Piped streams ${base} :: ${id}"
    if curl -LfsS --retry 2 --connect-timeout 12 --max-time 45 \
      -A 'Mozilla/5.0' "${base}/streams/${id}" -o "${out}.part"; then
      if jq -e '.videoStreams and (.videoStreams|length>0)' "${out}.part" >/dev/null 2>&1; then
        mv "${out}.part" "$out"
        return 0
      fi
    fi
  done
  echo "No Piped stream instance succeeded for ${id}" >&2
  return 1
}

search_and_prepare() {
  local category="$1" query="$2" limit="${3:-2}"
  piped_search "$category" "$query" || return 0
  local api
  api=$(cat "probe/search/${category}.api.txt")

  jq -r '(.items // .)[]
    | select((.type // "stream") == "stream" or (.type // "video") == "video")
    | [(.url // .videoId // ""),(.title // ""),(.duration // 0),(.uploaderName // .uploader // "")]
    | @tsv' "probe/search/${category}.json" \
    | head -n "$limit" > "probe/meta/${category}_candidates.tsv"

  local rank=0 rawid id title duration uploader key streams stream_url width height quality
  while IFS=$'\t' read -r rawid title duration uploader; do
    [[ -n "$rawid" ]] || continue
    id=$(printf '%s' "$rawid" | sed -E 's#^/watch\?v=##; s#^https?://[^/]+/watch\?v=##; s#&.*$##')
    [[ "$id" =~ ^[A-Za-z0-9_-]{11}$ ]] || continue
    rank=$((rank+1))
    key="${category}_${rank}_${id}"
    streams="probe/meta/${key}_streams.json"
    piped_streams "$id" "$streams" "$api" || continue

    # Probe copies need only be readable enough for visual selection. Prefer a
    # direct/proxied progressive stream, otherwise the highest video-only stream
    # at or below 1080p. Final rendering downloads the selected source at 1080p+.
    stream_url=$(jq -r '
      ([.videoStreams[] | select((.videoOnly // true) == false and (.height // 0) >= 360)]
        | sort_by(.height // 0) | last | .url) //
      ([.videoStreams[] | select((.height // 0) <= 1080)]
        | sort_by(.height // 0) | last | .url) //
      ([.videoStreams[]] | sort_by(.height // 0) | last | .url) // empty
    ' "$streams")
    [[ -n "$stream_url" && "$stream_url" != null ]] || continue
    width=$(jq -r --arg u "$stream_url" '[.videoStreams[] | select(.url==$u)][0].width // 0' "$streams")
    height=$(jq -r --arg u "$stream_url" '[.videoStreams[] | select(.url==$u)][0].height // 0' "$streams")
    quality=$(jq -r --arg u "$stream_url" '[.videoStreams[] | select(.url==$u)][0].quality // "unknown"' "$streams")

    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$key" "$id" "$duration" "$width" "$height" "$quality" "$title" "$uploader" \
      >> probe/meta/candidates.tsv

    echo "Encoding review proxy ${key}: ${title}"
    ffmpeg -y -hide_banner -loglevel warning -i "$stream_url" -t 150 -an \
      -vf "scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=24,format=yuv420p" \
      -c:v libx264 -preset veryfast -crf 27 -maxrate 900k -bufsize 1800k \
      -movflags +faststart "probe/clips/${key}.mp4" || continue

    ffmpeg -y -hide_banner -loglevel error -i "probe/clips/${key}.mp4" \
      -vf "fps=1/5,scale=320:180,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='%{pts\\:hms}':x=8:y=8:fontsize=17:fontcolor=white:borderw=2:bordercolor=black,tile=6x5:padding=3:margin=3:color=black" \
      -frames:v 1 -q:v 2 "probe/contacts/${key}.jpg" || true
  done < "probe/meta/${category}_candidates.tsv"
}

: > probe/meta/candidates.tsv
search_and_prepare bank_dark_knight 'The Dark Knight opening bank robbery scene 1080p' 3
search_and_prepare bank_heat 'Heat bank robbery scene 1080p' 3
search_and_prepare bank_town 'The Town bank robbery scene 1080p' 3
search_and_prepare bank_point_break 'Point Break bank robbery scene 1080p' 2
search_and_prepare bank_inside_man 'Inside Man bank robbery scene 1080p' 2
search_and_prepare flag_revolution_club 'Revolution Club burns American flag White House raw footage' 3
search_and_prepare flag_left_protest 'left wing protesters burn American flag raw footage' 3
search_and_prepare flag_antifa 'antifa burns American flag protest raw video' 3

find probe -type f -printf '%P\t%s bytes\n' | sort > probe/meta/manifest.txt
cat probe/meta/candidates.tsv
