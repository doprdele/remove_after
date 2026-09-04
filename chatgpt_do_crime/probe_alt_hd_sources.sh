#!/usr/bin/env bash
set -euo pipefail

mkdir -p probe/{formats,info,contacts,stills,tmp}
YTDLP=(yt-dlp --no-playlist --force-ipv4 --retries 10 --fragment-retries 10 --socket-timeout 45 --impersonate chrome)

probe_url() {
  local key="$1" url="$2" maxsec="$3"
  echo "=== ${key} :: ${url} ==="
  "${YTDLP[@]}" -F "$url" > "probe/formats/${key}.txt" 2>&1 || true
  rm -f "probe/tmp/${key}."* 2>/dev/null || true

  if ! "${YTDLP[@]}" --write-info-json --download-sections "*0-${maxsec}" \
      --force-keyframes-at-cuts \
      -f 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best' \
      --merge-output-format mp4 -o "probe/tmp/${key}.%(ext)s" "$url"; then
    echo "download failed ${key}" >&2
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
    -vf "fps=1/2,scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2:black,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='%{pts\\:hms}':x=7:y=7:fontsize=17:fontcolor=white:borderw=2:bordercolor=black,tile=6x10:padding=3:margin=3:color=black" \
    -frames:v 1 -q:v 2 "probe/contacts/${key}_page0.jpg" || true

  if [[ "$maxsec" -gt 120 ]]; then
    ffmpeg -y -hide_banner -loglevel error -ss 120 -i "$src" \
      -vf "fps=1/2,scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2:black,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='%{pts\\:hms}':x=7:y=7:fontsize=17:fontcolor=white:borderw=2:bordercolor=black,tile=6x10:padding=3:margin=3:color=black" \
      -frames:v 1 -q:v 2 "probe/contacts/${key}_page1.jpg" || true
  fi

  for ts in 2 5 8 12 20 30 45 60 90 120 150; do
    [[ "$ts" -lt "$maxsec" ]] || continue
    ffmpeg -y -hide_banner -loglevel error -ss "$ts" -i "$src" -frames:v 1 \
      -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:black" \
      -q:v 2 "probe/stills/${key}_t${ts}.jpg" || true
  done
  rm -f "$src"
}

# Recent raw/social-source flag-burning footage mirrored by major video sites.
probe_url fox_paramount_flag 'https://www.foxnews.com/video/6374003948112' 15
probe_url fox_la_flag 'https://www.foxnews.com/video/6374048349112' 170
probe_url fox_seattle_flag 'https://www.fox13seattle.com/video/1656122' 100
probe_url fox_dc_flag 'https://www.fox5dc.com/video/733148' 100
probe_url national_dc_flag 'https://www.thenationalnews.com/video/YCwbZJv4/anti-netanyahu-protesters-burn-american-flag-and-hoist-palestinian-one-in-washington/' 70
probe_url storyful_la_flag 'https://video.storyful.com/record/35459' 160

# Alternative hosted film-scene sources that may expose native 1080p.
probe_url vimeo_heat_bank 'https://vimeo.com/273675143' 180
probe_url vimeo_dark_knight_bank 'https://vimeo.com/144934696' 180
probe_url bilibili_dark_knight_bank 'https://www.bilibili.tv/en/video/2041663288' 180
probe_url okru_town_bank 'https://ok.ru/video/1355451532694' 180
probe_url okru_dark_knight_bank 'https://ok.ru/video/9175607611703' 180

find probe -type f -printf '%P\t%s bytes\n' | sort > probe/info/manifest.txt
