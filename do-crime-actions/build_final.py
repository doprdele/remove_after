#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

ROOT = Path.cwd()
WORK = ROOT / "gha-work"
RAW = WORK / "raw"
SRC = WORK / "src"
AUDIO = WORK / "audio"
TITLE = WORK / "title"
QC = WORK / "qc"
FRAMES = WORK / "frames"
META = WORK / "metadata"
OUT = ROOT / "gha-final"
SCRIPT_DIR = ROOT / "do-crime-actions"

for path in (RAW, SRC, AUDIO, TITLE, QC, FRAMES, META, OUT):
    path.mkdir(parents=True, exist_ok=True)

YTDLP_BASE = [
    "yt-dlp", "--no-playlist", "--force-ipv4", "--no-check-certificates",
    "--retries", "8", "--fragment-retries", "8", "--socket-timeout", "45",
    "--concurrent-fragments", "4", "--js-runtimes", "node",
    "--remote-components", "ejs:github", "--impersonate", "chrome",
]


def run(cmd: list[str], *, check: bool = True, capture: bool = False, cwd: Path | None = None) -> str:
    print("+", " ".join(str(x) for x in cmd), flush=True)
    p = subprocess.run(
        [str(x) for x in cmd], cwd=str(cwd or ROOT), check=False,
        text=True, stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    if check and p.returncode:
        if capture and p.stdout:
            print(p.stdout[-8000:])
        raise RuntimeError(f"command failed ({p.returncode}): {cmd[0]}")
    return p.stdout or ""


def ffprobe(path: Path) -> dict[str, Any]:
    text = run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=filename,duration,size,bit_rate,start_time:stream=index,codec_type,codec_name,profile,width,height,pix_fmt,r_frame_rate,avg_frame_rate,sample_rate,channels,duration,nb_frames",
        "-of", "json", str(path),
    ], capture=True)
    return json.loads(text)


def fetch(url: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".part")
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=90) as r, tmp.open("wb") as f:
                shutil.copyfileobj(r, f, length=1024 * 1024)
            if tmp.stat().st_size < 1024:
                raise RuntimeError("download was unexpectedly small")
            tmp.replace(out)
            return
        except Exception as exc:
            print(f"fetch attempt {attempt + 1} failed: {exc}")
            time.sleep(2 + attempt * 2)
    raise RuntimeError(f"unable to fetch {url}")


def clean_downloads(prefix: Path) -> None:
    for p in prefix.parent.glob(prefix.name + ".*"):
        if p.is_file():
            p.unlink()


def find_download(prefix: Path) -> Path:
    files = [p for p in prefix.parent.glob(prefix.name + ".*") if p.is_file() and not p.name.endswith((".part", ".ytdl", ".json")) and ".info." not in p.name]
    if not files:
        raise RuntimeError(f"download missing for {prefix}")
    return max(files, key=lambda p: p.stat().st_size)


def yt_info(url: str) -> dict[str, Any] | None:
    for client in ("web_embedded", "android_vr", "web_safari", ""):
        cmd = list(YTDLP_BASE)
        if client:
            cmd += ["--extractor-args", f"youtube:player_client={client}"]
        cmd += ["--dump-single-json", url]
        try:
            return json.loads(run(cmd, capture=True))
        except Exception as exc:
            print(f"metadata client {client or 'default'} failed for {url}: {exc}")
    return None


def search(query: str, limit: int = 8) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for prefix in (f"ytsearch{limit}", f"dmsearch{max(4, limit // 2)}"):
        cmd = list(YTDLP_BASE) + ["--flat-playlist", "--dump-json", f"{prefix}:{query}"]
        try:
            text = run(cmd, capture=True)
        except Exception:
            continue
        for line in text.splitlines():
            try:
                item = json.loads(line)
            except Exception:
                continue
            url = item.get("webpage_url") or item.get("url")
            if not url:
                continue
            if re.fullmatch(r"[A-Za-z0-9_-]{11}", str(url)):
                url = "https://www.youtube.com/watch?v=" + str(url)
            elif not str(url).startswith("http") and item.get("extractor_key") == "Dailymotion":
                url = "https://www.dailymotion.com/video/" + str(url)
            item["resolved_url"] = str(url)
            entries.append(item)
    dedup: dict[str, dict[str, Any]] = {}
    for e in entries:
        dedup.setdefault(e["resolved_url"], e)
    return list(dedup.values())


def title_rank(item: dict[str, Any], movie_terms: tuple[str, ...], mode: str) -> float:
    title = str(item.get("title") or "").lower()
    uploader = str(item.get("uploader") or item.get("channel") or "").lower()
    try:
        duration = float(item.get("duration") or 0)
    except Exception:
        duration = 0.0
    score = 0.0
    if mode == "robbery":
        score += 15 if all(term in title for term in movie_terms) else -12
        score += 15 if "bank" in title else 0
        score += 12 if any(x in title for x in ("robbery", "heist", "robbers")) else 0
        score += 6 if any(x in title for x in ("scene", "clip", "sequence", "opening")) else 0
        score += 5 if any(x in uploader for x in ("movieclips", "warner", "universal", "paramount", "sony", "filmclips", "rotton", "rotten")) else 0
        if any(x in title for x in ("reaction", "analysis", "explained", "trailer", "soundtrack", "gameplay", "gta", "edit", "shorts")):
            score -= 30
        if duration and not (25 <= duration <= 900):
            score -= 20
    else:
        score += 15 if "flag" in title else -10
        score += 16 if any(x in title for x in ("burn", "burning", "fire", "set on fire", "lit")) else 0
        score += 12 if any(x in title for x in ("protest", "protester", "demonstrator", "rally")) else 0
        score += 8 if any(x in title for x in ("american", "u.s.", "us flag", "united states")) else 0
        score += 5 if any(x in title for x in ("raw", "uncut", "footage")) else 0
        if any(x in title for x in ("reaction", "commentary", "debate", "song", "music video", "game")):
            score -= 28
        if duration and not (15 <= duration <= 1200):
            score -= 15
    return score


def download_section(url: str, prefix: Path, start: float, end: float, *, preview: bool) -> Path:
    clean_downloads(prefix)
    fmt = "best[height<=720]/bestvideo[height<=720]+bestaudio/best" if preview else "bestvideo[height>=1080][height<=2160][ext=mp4]/bestvideo[height>=1080][height<=2160]"
    last_exc: Exception | None = None
    for client in ("web_embedded", "android_vr", "web_safari", ""):
        cmd = list(YTDLP_BASE)
        if client and "youtube.com" in url:
            cmd += ["--extractor-args", f"youtube:player_client={client}"]
        cmd += [
            "--download-sections", f"*{start:.3f}-{end:.3f}", "--force-keyframes-at-cuts",
            "-f", fmt, "--merge-output-format", "mp4", "-o", str(prefix) + ".%(ext)s", url,
        ]
        try:
            run(cmd)
            return find_download(prefix)
        except Exception as exc:
            last_exc = exc
            clean_downloads(prefix)
    raise RuntimeError(f"source download failed: {url}: {last_exc}")


def analyze_preview(path: Path, mode: str) -> dict[str, Any]:
    output = path.with_suffix(".selection.json")
    run([sys.executable, str(SCRIPT_DIR / "select_source.py"), str(path), "--mode", mode, "--output", str(output)])
    return json.loads(output.read_text())


def select_source(key: str, query: str, movie_terms: tuple[str, ...], mode: str, attempts: int) -> tuple[Path, dict[str, Any]]:
    candidates = search(query, 10)
    candidates.sort(key=lambda x: title_rank(x, movie_terms, mode), reverse=True)
    records: list[dict[str, Any]] = []
    tried = 0
    for item in candidates:
        if tried >= attempts:
            break
        url = item["resolved_url"]
        info = yt_info(url)
        if not info:
            continue
        heights = [int(f.get("height") or 0) for f in info.get("formats", []) if f.get("vcodec") not in (None, "none")]
        max_height = max(heights or [0])
        duration = float(info.get("duration") or item.get("duration") or 0)
        if max_height < 1080 or duration < 15 or duration > 1200:
            continue
        tried += 1
        preview_prefix = RAW / f"{key}_preview_{tried}"
        try:
            preview = download_section(url, preview_prefix, 0.0, min(duration, 150.0), preview=True)
            selection = analyze_preview(preview, mode)
            combined = float(selection["score"]) + title_rank(item, movie_terms, mode) * 0.35
            records.append({
                "combined_score": combined,
                "selection": selection,
                "url": url,
                "id": info.get("id"),
                "title": info.get("title") or item.get("title"),
                "uploader": info.get("uploader") or item.get("uploader"),
                "duration": duration,
                "max_height": max_height,
            })
        except Exception as exc:
            print(f"candidate failed: {url}: {exc}")
        finally:
            for p in RAW.glob(f"{key}_preview_{tried}.*"):
                if p.is_file():
                    p.unlink()
    if not records:
        raise RuntimeError(f"no usable 1080p candidate for {key}: {query}")
    records.sort(key=lambda x: x["combined_score"], reverse=True)
    selected = records[0]
    sel = selected["selection"]
    start = float(sel["start"])
    # Preserve enough material to support distinct cue points and speed changes.
    end = min(float(selected["duration"]), start + 16.0)
    final = download_section(selected["url"], RAW / key, start, end, preview=False)
    selected["source_window_start"] = start
    selected["source_window_end"] = end
    (META / f"{key}.json").write_text(json.dumps(selected, indent=2) + "\n")
    return final, selected


def normalize_portrait(source: Path, out: Path, *, anchor: float = 0.5, duration: float = 14.0, crf: int = 17) -> None:
    crop = f"crop=ih*0.50625:ih*0.90:max(0\\,min(iw-ow\\,iw*{anchor:.5f}-ow/2)):ih*0.05"
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning", "-stream_loop", "-1", "-i", str(source), "-an",
        "-vf", crop + ",scale=1080:1920:flags=lanczos,setsar=1,fps=60,format=yuv420p",
        "-t", f"{duration:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-profile:v", "high", str(out),
    ])


def direct_sources() -> None:
    fetch("https://videos.pexels.com/video-files/3196002/3196002-uhd_3840_2160_25fps.mp4", RAW / "cash_counting.mp4")
    fetch("https://videos.pexels.com/video-files/13522186/13522186-uhd_3840_2160_25fps.mp4", RAW / "programmer.mp4")
    fetch("https://videos.pexels.com/video-files/4578336/4578336-hd_1920_1080_25fps.mp4", RAW / "linux.mp4")
    fetch("https://videos.pexels.com/video-files/30244590/12967797_3840_2160_24fps.mp4", RAW / "snow.mp4")

    # This source was already chosen in the previous approved cut for cash + designer-bag opulence.
    ig_url = "https://www.instagram.com/reel/DbsgjHEtQWO/"
    try:
        clean_downloads(RAW / "cash_bag")
        run(YTDLP_BASE + ["--write-info-json", "-f", "bestvideo+bestaudio/best", "--merge-output-format", "mp4", "-o", str(RAW / "cash_bag.%(ext)s"), ig_url])
        ig = find_download(RAW / "cash_bag")
        ig.rename(RAW / "cash_bag.mp4")
    except Exception as exc:
        print(f"Instagram source failed; using clean 4K cash fallback: {exc}")
        shutil.copy2(RAW / "cash_counting.mp4", RAW / "cash_bag.mp4")

    tout_url = "https://archive.org/download/tout.-va.-bien.-1972.-jean-luc.-godard.-1080p.-brrip.x-264-classics/Tout.Va.Bien.1972.%28Jean-Luc.Godard%29.1080p.BRRip.x264-Classics/Tout.Va.Bien.1972.%28Jean-Luc.Godard%29.1080p.BRRip.x264-Classics.mp4"
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning", "-ss", "5365", "-i", tout_url, "-t", "75", "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-movflags", "+faststart", str(RAW / "tout.mp4"),
    ])


def normalize_direct_sources() -> None:
    normalize_portrait(RAW / "cash_counting.mp4", SRC / "cash_counting.mp4", duration=12)
    # Instagram source is vertical when available; stretch-to-fill preserves the approved composition.
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning", "-stream_loop", "-1", "-i", str(RAW / "cash_bag.mp4"), "-an",
        "-vf", "scale=1080:1920:flags=lanczos,setsar=1,fps=60,format=yuv420p", "-t", "12",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-profile:v", "high", str(SRC / "cash_bag.mp4"),
    ])
    normalize_portrait(RAW / "programmer.mp4", SRC / "programmer.mp4", duration=9)
    normalize_portrait(RAW / "linux.mp4", SRC / "linux.mp4", duration=9)
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning", "-i", str(SRC / "programmer.mp4"), "-i", str(SRC / "linux.mp4"),
        "-filter_complex", "[0:v]trim=0:8.5,setpts=PTS-STARTPTS[a];[1:v]trim=0:8.5,setpts=PTS-STARTPTS[b];[a][b]concat=n=2:v=1:a=0,setsar=1,format=yuv420p[v]",
        "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-profile:v", "high", str(SRC / "cyber.mp4"),
    ])
    normalize_portrait(RAW / "snow.mp4", SRC / "snow.mp4", duration=14)
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning", "-stream_loop", "-1", "-i", str(RAW / "tout.mp4"), "-an",
        "-vf", "crop=iw*0.52:ih*0.86:(iw-iw*0.52)*0.31:ih*0.02,scale=1080:1920:flags=lanczos,setsar=1,fps=60,format=yuv420p",
        "-t", "20", "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-profile:v", "high", str(SRC / "tout.mp4"),
    ])


def get_audio() -> None:
    query = urllib.parse.urlencode({"term": "Raya Slowed Zericxxn", "entity": "song", "limit": "50"})
    data = json.loads(urllib.request.urlopen("https://itunes.apple.com/search?" + query, timeout=60).read())
    choices = []
    for item in data.get("results", []):
        artist = str(item.get("artistName") or "").lower()
        title = str(item.get("trackName") or "").lower()
        if artist == "zericxxn" and "raya" in title and "slowed" in title and "super" not in title and "ultra" not in title and item.get("previewUrl"):
            choices.append(item)
    if not choices:
        raise RuntimeError("matching Raya (Slowed) preview was not found")
    chosen = choices[0]
    fetch(chosen["previewUrl"], AUDIO / "raya_preview.m4a")
    (META / "audio.json").write_text(json.dumps(chosen, indent=2) + "\n")
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning", "-i", str(AUDIO / "raya_preview.m4a"), "-vn",
        "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2", str(AUDIO / "raya_master.m4a"),
    ])


def make_titles() -> None:
    W, H = 1080, 1920
    rows = 11
    rh = (H + rows - 1) // rows
    font_candidates = [
        Path("/usr/share/fonts/opentype/didot/GFSDidotBold.otf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"),
    ]
    fp = next(p for p in font_candidates if p.exists())
    phrase = "DO CRIME. DON’T VOTE  DO CRIME. DON’T VOTE"
    font = ImageFont.truetype(str(fp), 150)
    probe = Image.new("L", (5200, 400), 0)
    draw = ImageDraw.Draw(probe)
    box = draw.textbbox((0, 0), phrase, font=font)
    draw.text((-box[0], -box[1]), phrase, font=font, fill=255)
    mask = probe.crop(probe.getbbox()).resize((W, rh), Image.Resampling.LANCZOS)
    palettes = [
        (("#080808", "#E9FF00"), ("#2026D9", "#FF126E")),
        (("#FFF2D3", "#2026D9"), ("#080808", "#FF126E")),
    ]
    for n, pairs in enumerate(palettes):
        canvas = Image.new("RGB", (W, H), pairs[0][0])
        for r in range(rows):
            bg, fg = pairs[(r + n) % 2]
            band = Image.new("RGB", (W, rh), bg)
            ink = Image.new("RGB", (W, rh), fg)
            band.paste(ink, (0, 0), mask)
            canvas.paste(band, (0, r * rh))
        canvas.save(TITLE / f"title{n}.png", optimize=True)


def build_filter() -> tuple[str, str]:
    subdivision = 15 / 49
    title_units = 2
    title_open = title_units * subdivision
    title_close = title_units * subdivision
    shots = [
        ("cash_counting", 0, 0.25, 4, 0.95),
        ("instagram_cash_opulence", 1, 0.60, 3, 0.90),
        ("bank_robbery_dark_knight", 4, 0.25, 4, 0.94),
        ("tout", 7, 0.45, 4, 1.02),
        ("cyber", 2, 0.40, 3, 1.10),
        ("snow", 3, 1.10, 3, 1.18),
        ("flag_burning", 8, 0.25, 4, 0.92),
        ("bank_robbery_heat", 5, 1.60, 4, 0.88),
        ("tout", 7, 4.10, 3, 1.00),
        ("cyber", 2, 8.70, 3, 1.08),
        ("cash_counting", 0, 3.10, 3, 1.05),
        ("bank_robbery_town", 6, 4.20, 4, 0.92),
        ("flag_burning", 8, 5.20, 3, 0.96),
    ]
    assert title_units + sum(x[3] for x in shots) + title_units == 49
    parts: list[str] = []
    labels: list[str] = []
    parts.append(f"[10:v]trim=duration={title_open:.9f},setpts=PTS-STARTPTS,fps=60,scale=1080:1920,setsar=1,format=yuv420p[topen]")
    labels.append("[topen]")
    archival_names = {"flag_burning"}
    for i, (name, inp, cue, units, speed) in enumerate(shots):
        dur = units * subdivision
        source_dur = dur * speed
        archival = name in archival_names
        zoom = (1.026 + (i % 2) * 0.008) if archival else (1.052 + (i % 4) * 0.016)
        shake_x = 6 if archival else 11
        shake_y = 5 if archival else 9
        contrast = 1.18 if archival else 1.25 + (i % 3) * 0.035
        saturation = 1.31 if archival else 1.38 + (i % 4) * 0.045
        brightness = 0.002 if archival else -0.027
        rgb = 6 if archival else 9 + (i % 3) * 3
        rgbv = 1 if archival else 2
        grain = 6 if archival else 9 + (i % 4) * 2
        scan = 0.19 if archival else 0.25
        sw = round(1080 * zoom)
        sh = round(1920 * zoom)
        maxx, maxy = sw - 1080, sh - 1920
        xbase, ybase = maxx / 2, maxy / 2
        chain = (
            f"[{inp}:v]trim=start={cue:.4f}:end={cue + source_dur:.4f},"
            f"setpts=(PTS-STARTPTS)/{speed:.6f},fps=60,scale={sw}:{sh}:flags=bicubic,"
            f"crop=1080:1920:x='{xbase:.2f}+min({maxx / 3:.2f}\\,{shake_x})*sin(36*t+{i})':"
            f"y='{ybase:.2f}+min({maxy / 3:.2f}\\,{shake_y})*cos(31*t+{i})',setsar=1,"
        )
        if i in {2, 4, 7, 10}:
            chain += "loop=loop=1:size=4:start=24,"
        chain += (
            f"trim=duration={dur:.9f},setpts=PTS-STARTPTS,"
            f"eq=contrast={contrast:.3f}:saturation={saturation:.3f}:brightness={brightness:.3f},"
            f"rgbashift=rh={rgb}:bh={-rgb}:rv={rgbv}:bv={-rgbv},"
            f"noise=alls={grain}:allf=t+u,drawgrid=w=1080:h=4:t=1:c=black@{scan:.2f},"
            f"unsharp=5:5:0.78:5:5:0,format=yuv420p[s{i}]"
        )
        parts.append(chain)
        labels.append(f"[s{i}]")
    parts.append(f"[11:v]trim=duration={title_close:.9f},setpts=PTS-STARTPTS,fps=60,scale=1080:1920,setsar=1,format=yuv420p[tclose]")
    labels.append("[tclose]")
    parts.append("".join(labels) + f"concat=n={len(labels)}:v=1:a=0[base]")

    bounds = []
    t = title_open
    for _, _, _, units, _ in shots:
        t += units * subdivision
        bounds.append(t)
    neg_times = [bounds[i] for i in (1, 3, 6, 9, 11)]
    white_times = [bounds[i] for i in (2, 5, 8, 10)]
    neg = "+".join(f"between(t,{x - .018:.6f},{x + .018:.6f})" for x in neg_times)
    white = "+".join(f"between(t,{x - .018:.6f},{x + .018:.6f})" for x in white_times)
    parts.append(f"[base]negate=enable='{neg}',drawbox=x=0:y=0:w=iw:h=ih:color=white@1:t=fill:enable='{white}'[impact]")
    parts += [
        "[impact]split=4[m][a][b][c]",
        "[a]format=rgba,crop=1080:110:0:335,pad=1080:1920:0:335:color=black@0[ta]",
        "[b]format=rgba,crop=1080:88:0:915,pad=1080:1920:0:915:color=black@0[tb]",
        "[c]format=rgba,crop=1080:125:0:1435,pad=1080:1920:0:1435:color=black@0[tc]",
    ]
    tear_a = [bounds[i] for i in (4, 8, 12)]
    tear_b = [bounds[i] for i in (0, 7, 10)]
    tear_c = [bounds[i] for i in (2, 6, 11)]
    ea = "+".join(f"between(t,{x - .042:.6f},{x + .042:.6f})" for x in tear_a)
    eb = "+".join(f"between(t,{x - .035:.6f},{x + .035:.6f})" for x in tear_b)
    ec = "+".join(f"between(t,{x - .038:.6f},{x + .038:.6f})" for x in tear_c)
    parts += [
        f"[m][ta]overlay=x=82:y=0:enable='{ea}'[o1]",
        f"[o1][tb]overlay=x=-68:y=0:enable='{eb}'[o2]",
        f"[o2][tc]overlay=x=94:y=0:enable='{ec}'[o3]",
        "[o3]tpad=stop_mode=clone:stop_duration=0.12,trim=end_frame=901,fps=60,setpts=N/(60*TB)[outv]",
    ]
    filter_text = ";\n".join(parts) + "\n"
    timeline = (
        "audio_preview_start=14.740000\n"
        "audio_preview_end=29.740000\n"
        f"subdivision={subdivision:.9f}\nsubdivision_bpm={60 / subdivision:.6f}\n"
        f"opening_title={title_open:.9f}\nclosing_title={title_close:.9f}\n" +
        "\n".join(f"{i + 1:02d} {name} {units} subdivisions {units * subdivision:.6f}s cue={cue:.3f}" for i, (name, _, cue, units, _) in enumerate(shots))
    )
    return filter_text, timeline


def render() -> None:
    filter_text, timeline = build_filter()
    (WORK / "filter_complex.txt").write_text(filter_text)
    (QC / "timeline.txt").write_text(timeline + "\n")
    master = OUT / "do_crime_dont_vote_GITHUB_ACTIONS_60fps.mp4"
    inputs = [
        SRC / "cash_counting.mp4", SRC / "cash_bag.mp4", SRC / "cyber.mp4", SRC / "snow.mp4",
        SRC / "robbery_dark_knight.mp4", SRC / "robbery_heat.mp4", SRC / "robbery_town.mp4",
        SRC / "tout.mp4", SRC / "flag_burning.mp4",
    ]
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "warning"]
    for p in inputs:
        cmd += ["-i", str(p)]
    cmd += ["-ss", "14.740", "-i", str(AUDIO / "raya_master.m4a")]
    cmd += ["-loop", "1", "-framerate", "60", "-i", str(TITLE / "title0.png")]
    cmd += ["-loop", "1", "-framerate", "60", "-i", str(TITLE / "title1.png")]
    cmd += [
        "-filter_complex_script", str(WORK / "filter_complex.txt"), "-map", "[outv]", "-map", "9:a:0",
        "-t", "15", "-frames:v", "900", "-c:v", "libx264", "-preset", "medium", "-crf", "17",
        "-maxrate", "15M", "-bufsize", "30M", "-profile:v", "high", "-level:v", "4.2", "-pix_fmt", "yuv420p",
        "-r", "60", "-g", "60", "-keyint_min", "60", "-sc_threshold", "0",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
        "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2",
        "-af", "apad=pad_dur=0.20,atrim=duration=15,asetpts=N/SR/TB,afade=t=in:st=0:d=0.012,afade=t=out:st=14.93:d=0.07,alimiter=limit=0.97",
        "-movflags", "+faststart", str(master),
    ]
    run(cmd)
    phone = OUT / "do_crime_dont_vote_GITHUB_ACTIONS_iPhone_30fps.mp4"
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning", "-i", str(master),
        "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-maxrate", "11M", "-bufsize", "22M",
        "-profile:v", "high", "-level:v", "4.1", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2",
        "-t", "15", "-movflags", "+faststart", str(phone),
    ])


def make_contact(path: Path, out: Path, fps_expr: str = "4/3") -> None:
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(path),
        "-vf", f"fps={fps_expr},scale=216:384,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='%{{pts\\:hms}}':x=5:y=5:fontsize=14:fontcolor=white:borderw=2:bordercolor=black,tile=5x4:padding=4:margin=4:color=black",
        "-frames:v", "1", "-q:v", "2", str(out),
    ])


def qc_and_package() -> None:
    master = OUT / "do_crime_dont_vote_GITHUB_ACTIONS_60fps.mp4"
    phone = OUT / "do_crime_dont_vote_GITHUB_ACTIONS_iPhone_30fps.mp4"
    master_probe = ffprobe(master)
    phone_probe = ffprobe(phone)
    (OUT / "GITHUB_ACTIONS_60fps_ffprobe.json").write_text(json.dumps(master_probe, indent=2) + "\n")
    (OUT / "GITHUB_ACTIONS_iPhone_ffprobe.json").write_text(json.dumps(phone_probe, indent=2) + "\n")
    run(["ffmpeg", "-v", "error", "-i", str(master), "-f", "null", "-"])
    run(["ffmpeg", "-v", "error", "-i", str(phone), "-f", "null", "-"])

    streams = {s["codec_type"]: s for s in master_probe["streams"]}
    v, a = streams["video"], streams["audio"]
    errors = []
    if abs(float(master_probe["format"]["duration"]) - 15.0) > 0.025:
        errors.append("duration")
    if (int(v.get("width", 0)), int(v.get("height", 0))) != (1080, 1920):
        errors.append("resolution")
    if v.get("codec_name") != "h264" or v.get("r_frame_rate") != "60/1":
        errors.append("video codec/rate")
    if v.get("pix_fmt") != "yuv420p":
        errors.append("pixel format")
    if int(v.get("nb_frames") or 0) != 900:
        errors.append("frame count")
    if a.get("codec_name") != "aac" or a.get("sample_rate") != "48000":
        errors.append("audio")
    if errors:
        raise RuntimeError("FINAL QC FAILED: " + ", ".join(errors))

    make_contact(master, OUT / "do_crime_dont_vote_GITHUB_ACTIONS_contact_sheet.jpg")
    source_contacts = []
    for src in sorted(SRC.glob("*.mp4")):
        contact = QC / f"{src.stem}_contact.jpg"
        run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
            "-vf", "fps=1,scale=180:320,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='%{pts\\:hms}':x=4:y=4:fontsize=13:fontcolor=white:borderw=2:bordercolor=black,tile=6x2:padding=3:margin=3:color=black",
            "-frames:v", "1", "-q:v", "2", str(contact),
        ], check=False)
        if contact.exists():
            source_contacts.append(contact)
    if source_contacts:
        cards = []
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        for p in source_contacts:
            im = Image.open(p).convert("RGB")
            card = Image.new("RGB", (im.width, im.height + 42), "black")
            card.paste(im, (0, 42))
            ImageDraw.Draw(card).text((8, 8), p.stem.replace("_contact", ""), font=font, fill="white")
            cards.append(card)
        cols = 2
        rows = math.ceil(len(cards) / cols)
        board = Image.new("RGB", (cols * cards[0].width, rows * cards[0].height), "black")
        for i, card in enumerate(cards):
            board.paste(card, ((i % cols) * card.width, (i // cols) * card.height))
        board.save(OUT / "do_crime_dont_vote_GITHUB_ACTIONS_source_QC.jpg", quality=90)

    for sec, name in ((0.20, "title_open"), (2.10, "bank_robbery_1"), (6.85, "flag_ignition"), (8.15, "bank_robbery_2"), (12.85, "bank_robbery_3"), (14.65, "title_close")):
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", str(sec), "-i", str(master), "-frames:v", "1", "-q:v", "1", str(FRAMES / f"{name}.jpg")])
        shutil.copy2(FRAMES / f"{name}.jpg", OUT / f"{name}.jpg")

    shutil.copy2(WORK / "filter_complex.txt", OUT / "filter_complex.txt")
    shutil.copy2(QC / "timeline.txt", OUT / "timeline.txt")
    (OUT / "GITHUB_ACTIONS_QC_PASSED.txt").write_text("PASS\n")
    source_manifest = {p.stem: json.loads(p.read_text()) for p in META.glob("*.json")}
    (OUT / "source_manifest.json").write_text(json.dumps(source_manifest, indent=2) + "\n")
    readme = """DO CRIME. DON’T VOTE — GitHub Actions replacement cut

Deliverables:
- do_crime_dont_vote_GITHUB_ACTIONS_60fps.mp4: 1080x1920, 60 fps, H.264/AAC, exactly 15 seconds.
- do_crime_dont_vote_GITHUB_ACTIONS_iPhone_30fps.mp4: 1080x1920, 30 fps compatibility encode.
- do_crime_dont_vote_GITHUB_ACTIONS_contact_sheet.jpg: final timeline visual QC.
- do_crime_dont_vote_GITHUB_ACTIONS_source_QC.jpg: normalized source contact sheets.

The three former FARC positions are replaced by three distinct armed bank-robbery film excerpts. The former flag insert is replaced by a source selected for visible flame plus American-flag color regions. Source clips are tightly center-cropped to remove corner bugs, lower thirds, subtitles and uploader marks. Exactly two grain-free title cards are used.
"""
    (OUT / "README.txt").write_text(readme)

    repro = OUT / "do_crime_dont_vote_GITHUB_ACTIONS_repro.zip"
    with zipfile.ZipFile(repro, "w", zipfile.ZIP_DEFLATED) as z:
        for p in (SCRIPT_DIR / "build_final.py", SCRIPT_DIR / "select_source.py", WORK / "filter_complex.txt", QC / "timeline.txt", OUT / "source_manifest.json", OUT / "README.txt"):
            z.write(p, p.name)


def main() -> None:
    shutil.rmtree(WORK, ignore_errors=True)
    for path in (RAW, SRC, AUDIO, TITLE, QC, FRAMES, META):
        path.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for p in OUT.iterdir():
        if p.is_file():
            p.unlink()

    direct_sources()
    normalize_direct_sources()
    get_audio()
    make_titles()

    robbery_specs = [
        ("robbery_dark_knight", "The Dark Knight bank robbery opening scene 1080p", ("dark", "knight")),
        ("robbery_heat", "Heat bank robbery scene 1080p movie clip", ("heat",)),
        ("robbery_town", "The Town bank robbery scene 1080p movie clip", ("town",)),
    ]
    for key, query, terms in robbery_specs:
        raw, meta = select_source(key, query, terms, "robbery", attempts=3)
        normalize_portrait(raw, SRC / f"{key}.mp4", anchor=0.5, duration=14, crf=16)

    flag_raw, flag_meta = select_source(
        "flag_burning",
        "protesters light American flag on fire raw footage 1080p",
        ("flag",),
        "flag",
        attempts=5,
    )
    flag_anchor = float(flag_meta["selection"].get("anchor_x", 0.5))
    normalize_portrait(flag_raw, SRC / "flag_burning.mp4", anchor=flag_anchor, duration=14, crf=16)

    render()
    qc_and_package()
    print("FINAL BUILD COMPLETE")


if __name__ == "__main__":
    main()
