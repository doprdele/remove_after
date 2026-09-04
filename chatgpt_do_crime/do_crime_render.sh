#!/usr/bin/env bash
set -euo pipefail
mkdir -p work/raw work/qc output

YTDLP=(yt-dlp --no-playlist --retries 5 --fragment-retries 5 --socket-timeout 45 --concurrent-fragments 4)

probe_source() {
  local key="$1" url="$2"
  echo "=== $key $url ==="
  "${YTDLP[@]}" --skip-download --write-info-json -o "work/raw/${key}.%(ext)s" "$url"
  info=$(find work/raw -maxdepth 1 -name "${key}.info.json" | head -n1)
  jq '{id,title,duration,uploader,width,height,fps,formats:[.formats[]|select(.vcodec!="none")|{format_id,ext,width,height,fps,vcodec,filesize,filesize_approx}]}' "$info" > "work/qc/${key}_info.json"
  # Download best picture stream. 720p fallback is permitted only for QC; final pass will require 1080p.
  "${YTDLP[@]}" -f 'bestvideo[height>=1080]/best[height>=1080]/bestvideo/best' --merge-output-format mp4 -o "work/raw/${key}.%(ext)s" "$url"
  input=$(find work/raw -maxdepth 1 -type f -name "${key}.*" ! -name '*.info.json' ! -name '*.part' | head -n1)
  ffprobe -v error -show_entries format=duration,size:stream=codec_name,width,height,r_frame_rate -of json "$input" > "work/qc/${key}_ffprobe.json"
  dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$input")
  # 48 frames evenly across the source, packed into an 8x6 sheet.
  interval=$(awk -v d="$dur" 'BEGIN{v=d/48; if(v<0.4)v=0.4; printf "%.5f",v}')
  ffmpeg -y -hide_banner -loglevel error -i "$input" \
    -vf "fps=1/${interval},scale=300:169:force_original_aspect_ratio=decrease,pad=300:169:(ow-iw)/2:(oh-ih)/2:black,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='%{pts\\:hms}':x=5:y=5:fontsize=14:fontcolor=white:borderw=2:bordercolor=black,tile=8x6:padding=3:margin=3:color=black" \
    -frames:v 1 -q:v 2 "work/qc/${key}_contact.jpg"
}

probe_source cash 'https://vimeo.com/437474288'
probe_source luxury 'https://vimeo.com/784619893'
probe_source farc 'https://vimeo.com/467357526'
probe_source flag_ur 'https://vimeo.com/132108480'
probe_source flag_torn 'https://vimeo.com/218313862'
probe_source cyberdeck 'https://vimeo.com/573011448'
probe_source kali 'https://vimeo.com/540209503'
probe_source tout 'https://vimeo.com/127193878'
probe_source snow 'https://vimeo.com/943225150'

# Exact soundtrack alternative host from the artist; only metadata/probe in this pass.
yt-dlp --no-playlist --skip-download --write-info-json -o 'work/raw/raya_audio.%(ext)s' 'https://audiomack.com/zericxxn/song/raya-slowed'
cat work/raw/raya_audio.info.json | jq '{id,title,duration,uploader,extractor,formats:[.formats[]|{format_id,ext,acodec,abr,filesize,filesize_approx}]}' > work/qc/raya_audio_info.json

cp work/qc/*.json output/ || true
cp work/qc/*_contact.jpg output/ || true
echo 'SOURCE_QC_PASS_COMPLETE' > output/status.txt
