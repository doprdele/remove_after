from pathlib import Path

p = Path('chatgpt_do_crime/do_crime_render.sh')
s = p.read_text()

# Current renderer already uses real Vimeo FARC footage and contains no Runway
# media references. Fail hard if that ever changes.
if 'runway' in s.lower() or 'dnznrvs05pmza.cloudfront.net' in s:
    raise SystemExit('Runway-derived media reference detected in renderer')

# Replace the Audiomack block with Apple's official public preview for
# Zericxxn - Raya (Slowed). The preview is 30 seconds, enough for this reel.
start = s.index('# Exact track version via artist-attributed Audiomack mirror')
end_marker = 'ffmpeg -y -v warning -i "$audio" -vn -c:a aac -b:a 256k -ar 48000 -ac 2 work/audio/raya_master.m4a\n'
end = s.index(end_marker, start) + len(end_marker)
audio_block = r'''# Exact Raya (Slowed) soundtrack via Apple public catalog preview.
fetch 'https://itunes.apple.com/search?term=Raya%20Slowed%20Zericxxn&entity=song&limit=25' work/audio/itunes.json
preview=$(jq -r '.results[] | select(.artistName=="Zericxxn" and ((.trackName|ascii_downcase)=="raya - slowed" or (.trackName|ascii_downcase)=="raya (slowed)")) | .previewUrl' work/audio/itunes.json | head -n1)
if [ -z "$preview" ] || [ "$preview" = null ]; then
  preview=$(jq -r '.results[] | select(.artistName=="Zericxxn" and (.trackName|ascii_downcase|contains("raya")) and (.trackName|ascii_downcase|contains("slowed")) and ((.trackName|ascii_downcase|contains("super"))|not) and ((.trackName|ascii_downcase|contains("ultra"))|not)) | .previewUrl' work/audio/itunes.json | head -n1)
fi
test -n "$preview"; test "$preview" != null
fetch "$preview" work/audio/raya_preview.m4a
ffmpeg -y -v warning -i work/audio/raya_preview.m4a -vn -c:a aac -b:a 256k -ar 48000 -ac 2 work/audio/raya_master.m4a
'''
s = s[:start] + audio_block + s[end:]

# Raya (Slowed) is 98 BPM. 49 eighth notes = exactly 15.000 seconds.
s = s.replace('S=3/11; N=55', 'S=15/49; N=49')
s = s.replace("zip([7,8,9,10],[0,20,40,54])", "zip([7,8,9,10],[0,17,34,48])")
s = s.replace('-i work/src/flag.mp4 -ss 44.742 -i work/audio/raya_master.m4a', '-i work/src/flag.mp4 -i work/audio/raya_master.m4a')

p.write_text(s)
assert 'S=15/49; N=49' in s
assert '-ss 44.742 -i work/audio/raya_master.m4a' not in s
assert 'audiomack.com' not in s
assert 'runway' not in s.lower()
print('Patched renderer: no Runway; official Raya preview; 98 BPM / 49-slot grid')
