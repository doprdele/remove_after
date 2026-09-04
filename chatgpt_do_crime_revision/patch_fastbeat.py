from pathlib import Path

SOURCE = Path("chatgpt_do_crime_revision/render_revision.sh")
TARGET = Path("chatgpt_do_crime_revision/render_fastbeat.sh")

s = SOURCE.read_text()

start = s.index("# Longer beat-aligned edit:")
end_marker = "\nffmpeg -y -hide_banner -loglevel warning \\\n  -i work/src/cash_counting.mp4"
end = s.index(end_marker, start)

new_block = r'''# Faster later section selected from the full 30-second Raya (Slowed) preview.
# The chosen audio range is 14.740-29.740 seconds, where the percussion resolves
# into a denser double-time pulse. The picture grid uses 49 subdivisions across
# 15 seconds (about 196 BPM), while shots remain 0.92-1.22 seconds for legibility.
python - <<'PY'
from pathlib import Path
SUB=15/49
TITLE_UNITS=2
TITLE_OPEN=TITLE_UNITS*SUB
TITLE_CLOSE=TITLE_UNITS*SUB
shots=[
 ('cash_counting',0,0.25,4,0.95),
 ('cash_bag',1,0.60,3,0.90),
 ('farc_group',4,0.12,4,0.94),
 ('tout',7,0.45,4,1.02),
 ('cyber',2,0.40,3,1.10),
 ('snow',3,1.10,3,1.18),
 ('flag_burning',8,0.60,4,0.92),
 ('farc_armed',5,2.05,4,0.88),
 ('tout',7,4.10,3,1.00),
 ('cyber',2,8.70,3,1.08),
 ('cash_counting',0,3.10,3,1.05),
 ('farc_rifle',6,6.00,4,0.92),
 ('flag_burning',8,7.10,3,0.96),
]
assert TITLE_UNITS + sum(x[3] for x in shots) + TITLE_UNITS == 49
parts=[]
labels=[]
parts.append(f'[10:v]trim=duration={TITLE_OPEN:.9f},setpts=PTS-STARTPTS,fps=60,scale=1080:1920,setsar=1,format=yuv420p[topen]')
labels.append('[topen]')
for i,(name,inp,cue,units,speed) in enumerate(shots):
    dur=units*SUB
    source_dur=dur*speed
    archival=name in {'farc_group','farc_armed','farc_rifle','flag_burning'}
    zoom=(1.022+(i%2)*0.008) if archival else (1.050+(i%4)*0.016)
    shake_x=5 if archival else 11
    shake_y=4 if archival else 9
    contrast=1.15 if archival else 1.25+(i%3)*0.035
    saturation=1.27 if archival else 1.38+(i%4)*0.045
    brightness=0.004 if archival else -0.027
    rgb=5 if archival else 9+(i%3)*3
    rgbv=1 if archival else 2
    grain=5 if archival else 9+(i%4)*2
    scan=0.18 if archival else 0.25
    sw=round(1080*zoom); sh=round(1920*zoom)
    maxx=sw-1080; maxy=sh-1920
    xbase=maxx/2; ybase=maxy/2
    chain=(f'[{inp}:v]trim=start={cue:.4f}:end={cue+source_dur:.4f},'
           f'setpts=(PTS-STARTPTS)/{speed:.6f},fps=60,scale={sw}:{sh}:flags=bicubic,'
           f"crop=1080:1920:x='{xbase:.2f}+min({maxx/3:.2f}\\,{shake_x})*sin(36*t+{i})':"
           f"y='{ybase:.2f}+min({maxy/3:.2f}\\,{shake_y})*cos(31*t+{i})',setsar=1,")
    if i in {4,7,10}:
        chain+='loop=loop=1:size=4:start=24,'
    chain+=(f'trim=duration={dur:.9f},setpts=PTS-STARTPTS,'
            f'eq=contrast={contrast:.3f}:saturation={saturation:.3f}:brightness={brightness:.3f},'
            f'rgbashift=rh={rgb}:bh={-rgb}:rv={rgbv}:bv={-rgbv},'
            f'noise=alls={grain}:allf=t+u,drawgrid=w=1080:h=4:t=1:c=black@{scan:.2f},'
            f'unsharp=5:5:0.78:5:5:0,format=yuv420p[s{i}]')
    parts.append(chain)
    labels.append(f'[s{i}]')
parts.append(f'[11:v]trim=duration={TITLE_CLOSE:.9f},setpts=PTS-STARTPTS,fps=60,scale=1080:1920,setsar=1,format=yuv420p[tclose]')
labels.append('[tclose]')
parts.append(''.join(labels)+f'concat=n={len(labels)}:v=1:a=0[base]')

# Single-frame negative and hard-white impacts land on the faster pulse grid.
bounds=[]
t=TITLE_OPEN
for _,_,_,units,_ in shots:
    t += units*SUB
    bounds.append(t)
neg_times=[bounds[i] for i in (1,3,6,9,11)]
white_times=[bounds[i] for i in (2,5,8,10)]
neg='+'.join(f'between(t,{x-.018:.6f},{x+.018:.6f})' for x in neg_times)
white='+'.join(f'between(t,{x-.018:.6f},{x+.018:.6f})' for x in white_times)
parts.append(f"[base]negate=enable='{neg}',drawbox=x=0:y=0:w=iw:h=ih:color=white@1:t=fill:enable='{white}'[impact]")

parts += [
 '[impact]split=4[m][a][b][c]',
 '[a]format=rgba,crop=1080:110:0:335,pad=1080:1920:0:335:color=black@0[ta]',
 '[b]format=rgba,crop=1080:88:0:915,pad=1080:1920:0:915:color=black@0[tb]',
 '[c]format=rgba,crop=1080:125:0:1435,pad=1080:1920:0:1435:color=black@0[tc]',
]
tear_a=[bounds[i] for i in (4,8,12)]
tear_b=[bounds[i] for i in (0,7,10)]
tear_c=[bounds[i] for i in (2,6,11)]
ea='+'.join(f'between(t,{x-.042:.6f},{x+.042:.6f})' for x in tear_a)
eb='+'.join(f'between(t,{x-.035:.6f},{x+.035:.6f})' for x in tear_b)
ec='+'.join(f'between(t,{x-.038:.6f},{x+.038:.6f})' for x in tear_c)
parts += [
 f"[m][ta]overlay=x=82:y=0:enable='{ea}'[o1]",
 f"[o1][tb]overlay=x=-68:y=0:enable='{eb}'[o2]",
 f"[o2][tc]overlay=x=94:y=0:enable='{ec}'[o3]",
 '[o3]trim=duration=15,setpts=PTS-STARTPTS[outv]',
]
Path('work/filter.txt').write_text(';\n'.join(parts)+'\n')
Path('work/qc/timeline.txt').write_text(
    'audio_preview_start=14.740000\n'
    'audio_preview_end=29.740000\n'
    f'subdivision={SUB:.9f}\nsubdivision_bpm={60/SUB:.6f}\n'
    f'opening_title={TITLE_OPEN:.9f}\nclosing_title={TITLE_CLOSE:.9f}\n' +
    '\n'.join(f'{i+1:02d} {name} {units} subdivisions {units*SUB:.6f}s cue={cue:.3f}' for i,(name,_,cue,units,_) in enumerate(shots))
)
PY
'''

s = s[:start] + new_block + s[end:]
s = s.replace("do_crime_dont_vote_reel_revision", "do_crime_dont_vote_reel_fastbeat")
s = s.replace("  -i work/audio/raya_master.m4a \\", "  -ss 14.740 -i work/audio/raya_master.m4a \\")

TARGET.write_text(s)
TARGET.chmod(0o755)

assert "audio_preview_start=14.740000" in s
assert "S=15/49" not in s
assert "-ss 14.740 -i work/audio/raya_master.m4a" in s
assert "do_crime_dont_vote_reel_fastbeat.mp4" in s
print(TARGET)
