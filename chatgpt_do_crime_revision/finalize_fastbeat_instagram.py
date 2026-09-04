from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parent
PATCH = ROOT / "patch_fastbeat.py"
GENERATED = ROOT / "render_fastbeat.sh"
FINAL = ROOT / "render_fastbeat_instagram.sh"

subprocess.run(["python3", str(PATCH)], cwd=ROOT.parent, check=True)
s = GENERATED.read_text()

# Replace the prior stock shot of a woman carrying cash bags with the exact
# public Instagram reel supplied by the user. The downloaded source is the
# clean video file, not a screen recording of the Instagram interface.
old_cash = "fetch 'https://videos.pexels.com/video-files/6266293/6266293-uhd_2160_3840_25fps.mp4' work/raw/cash_bag.mp4"
new_cash = r'''rm -f work/raw/cash_bag.* 2>/dev/null || true
"${YTDLP[@]}" --write-info-json \
  -f 'bestvideo+bestaudio/best' --merge-output-format mp4 \
  -o 'work/raw/cash_bag.%(ext)s' \
  'https://www.instagram.com/reel/DbsgjHEtQWO/'
ig_cash=$(find work/raw -maxdepth 1 -type f -name 'cash_bag.*' ! -name '*.part' ! -name '*.info.json' | head -n1)
test -s "$ig_cash"
if [[ "$ig_cash" != "work/raw/cash_bag.mp4" ]]; then
  mv "$ig_cash" work/raw/cash_bag.mp4
fi'''
if old_cash not in s:
    raise SystemExit("stock cash-bag source line missing")
s = s.replace(old_cash, new_cash, 1)

# Keep the same input index and clean early cue, but identify it accurately in
# the reproducible timeline.
old_label = "('cash_bag',1,0.60,3,0.90)"
new_label = "('instagram_cash_opulence',1,0.60,3,0.90)"
if old_label not in s:
    raise SystemExit("cash-bag timeline entry missing")
s = s.replace(old_label, new_label, 1)

# The first fast-grid test landed three frames short because fractional segment
# durations rounded downward. Extend the clean closing title and enforce an
# exact 900-frame clock at 60 fps.
old_tail = "[o3]trim=duration=15,setpts=PTS-STARTPTS[outv]"
new_tail = "[o3]tpad=stop_mode=clone:stop_duration=0.12,trim=end_frame=900,fps=60,setpts=N/(60*TB)[outv]"
if old_tail not in s:
    raise SystemExit("final filter tail missing")
s = s.replace(old_tail, new_tail, 1)

old_audio = "-af 'afade=t=in:st=0:d=0.012,afade=t=out:st=14.93:d=0.07,alimiter=limit=0.97'"
new_audio = "-af 'apad=pad_dur=0.20,atrim=duration=15,asetpts=N/SR/TB,afade=t=in:st=0:d=0.012,afade=t=out:st=14.93:d=0.07,alimiter=limit=0.97'"
if old_audio not in s:
    raise SystemExit("audio filter line missing")
s = s.replace(old_audio, new_audio, 1)

s = s.replace(
    "do_crime_dont_vote_reel_fastbeat",
    "do_crime_dont_vote_reel_fastbeat_instagram",
)

FINAL.write_text(s)
FINAL.chmod(0o755)

checks = [
    "instagram.com/reel/DbsgjHEtQWO",
    "instagram_cash_opulence",
    "trim=end_frame=900",
    "-ss 14.740 -i work/audio/raya_master.m4a",
    "apad=pad_dur=0.20,atrim=duration=15",
    "do_crime_dont_vote_reel_fastbeat_instagram.mp4",
]
for check in checks:
    if check not in s:
        raise SystemExit(f"missing expected patch: {check}")
print(FINAL)
