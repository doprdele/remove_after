from pathlib import Path
import re

p = Path('chatgpt_do_crime/do_crime_render.sh')
s = p.read_text()

# Never use generated Runway assets. Replace both FARC inputs with genuine
# historical Wikimedia Commons photographs from the Caguan peace-talk period.
s = re.sub(
    r"^fetch 'https://dnznrvs05pmza\.cloudfront\.net/.*?' work/raw/farc1\.png$",
    "fetch 'https://commons.wikimedia.org/wiki/Special:Redirect/file/FARC_guerrillas_during_the_Caguan_peace_talks_(1998-2002).jpg' work/raw/farc1.png",
    s, flags=re.M,
)
s = re.sub(
    r"^fetch 'https://dnznrvs05pmza\.cloudfront\.net/.*?' work/raw/farc2\.png$",
    "fetch 'https://commons.wikimedia.org/wiki/Special:Redirect/file/FARC_guerrillas_marching_during_the_Caguan_peace_talks_(1998-2002).jpg' work/raw/farc2.png",
    s, flags=re.M,
)

# Use Apple's official public 30-second preview of Raya (Slowed). This avoids
# scraping/anti-bot problems while still using the requested released track.
start = s.index('# Exact Raya (Slowed) track.')
end_marker = 'ffmpeg -y -v warning -i "$audio" -vn -c:a aac -b:a 256k -ar 48000 -ac 2 work/audio/raya.m4a\n'
end = s.index(end_marker, start) + len(end_marker)
audio_block = r'''# Exact Raya (Slowed) soundtrack via Apple public catalog preview.
fetch 'https://itunes.apple.com/search?term=Raya%20Slowed%20Zericxxn&entity=song&limit=25' work/audio/itunes.json
preview=$(jq -r '.results[] | select(.artistName=="Zericxxn" and ((.trackName|ascii_downcase)=="raya - slowed" or (.trackName|ascii_downcase)=="raya (slowed)")) | .previewUrl' work/audio/itunes.json | head -n1)
if [ -z "$preview" ] || [ "$preview" = null ]; then
  preview=$(jq -r '.results[] | select(.artistName=="Zericxxn" and (.trackName|ascii_downcase|contains("raya")) and (.trackName|ascii_downcase|contains("slowed")) and ((.trackName|ascii_downcase|contains("super"))|not) and ((.trackName|ascii_downcase|contains("ultra"))|not)) | .previewUrl' work/audio/itunes.json | head -n1)
fi
test -n "$preview"; test "$preview" != null
fetch "$preview" work/audio/raya_preview.m4a
ffmpeg -y -v warning -i work/audio/raya_preview.m4a -vn -c:a aac -b:a 256k -ar 48000 -ac 2 work/audio/raya.m4a
'''
s = s[:start] + audio_block + s[end:]

# Raya (Slowed) is 98 BPM. 49 eighth notes = exactly 15 seconds.
s = s.replace('S=3/11;N=55;', 'S=15/49;N=49;')
s = s.replace("zip([8,9,10,11],[0,20,40,54])", "zip([8,9,10,11],[0,17,34,48])")
s = s.replace('-i work/src/flag.mp4 -ss 44.742 -i work/audio/raya.m4a', '-i work/src/flag.mp4 -i work/audio/raya.m4a')

p.write_text(s)

assert 'dnznrvs05pmza.cloudfront.net' not in '\n'.join(line for line in s.splitlines() if 'farc1.png' in line or 'farc2.png' in line)
assert 'S=15/49;N=49;' in s
assert '-ss 44.742 -i work/audio/raya.m4a' not in s
print('Patched build: Wikimedia FARC archival media, Apple official Raya preview, 98 BPM grid')
