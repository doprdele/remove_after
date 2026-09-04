#!/usr/bin/env python3
"""Replace guerrilla/FARC and old flag shots in the completed 15 s reel.

The detector uses CLIP on the already-finished baseline, so every other edit,
title card, timing decision and soundtrack sample remains unchanged. Replacement
clips are tightly portrait-cropped to remove corner bugs and are OCR-screened.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
from PIL import Image, ImageDraw
import pytesseract
import torch
from transformers import CLIPModel, CLIPProcessor

DURATION = 15.0
FPS = 60
WIDTH = 1080
HEIGHT = 1920

LABELS = [
    "armed guerrilla fighters training in a green jungle wearing camouflage and carrying rifles",
    "masked armed bank robbers inside a bank with guns and bags of money",
    "people counting stacks of cash surrounded by luxury goods",
    "people taking groceries in a supermarket",
    "a real computer hacker using a Linux terminal on a cyberdeck or laptop",
    "a car drifting fast through snow",
    "left wing demonstrators burning an American flag at a protest",
    "a flat graphic title card dominated by large typography",
    "an unrelated cinematic scene",
]

@dataclass
class Interval:
    start: float
    end: float
    kind: str
    score: float
    source_index: int = -1
    source_start: float = 0.0
    anchor: float = 0.5

    @property
    def duration(self) -> float:
        return self.end - self.start


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=check)


def ffprobe(path: Path) -> dict:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,size,bit_rate:stream=index,codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,nb_frames,sample_rate,channels",
        "-of", "json", str(path),
    ], text=True)
    return json.loads(out)


def video_duration(path: Path) -> float:
    return float(ffprobe(path)["format"]["duration"])


def portrait_crop(im: Image.Image, anchor: float) -> Image.Image:
    w, h = im.size
    target = 9 / 16
    if w / h >= target:
        cw = max(1, int(round(h * target)))
        x = int(round((w - cw) * min(1.0, max(0.0, anchor))))
        return im.crop((x, 0, x + cw, h))
    ch = max(1, int(round(w / target)))
    y = max(0, (h - ch) // 2)
    return im.crop((0, y, w, y + ch))


def get_frame(cap: cv2.VideoCapture, t: float) -> Image.Image | None:
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t) * 1000)
    ok, frame = cap.read()
    if not ok:
        return None
    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return Image.fromarray(frame)


def load_clip() -> tuple[CLIPModel, CLIPProcessor, torch.device]:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(device)
    model.eval()
    processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    print(f"CLIP device: {device}", flush=True)
    return model, processor, device


def encode_images(model, processor, device, images: list[Image.Image], batch: int = 24) -> np.ndarray:
    chunks: list[np.ndarray] = []
    with torch.no_grad():
        for i in range(0, len(images), batch):
            inp = processor(images=images[i:i+batch], return_tensors="pt").to(device)
            emb = model.get_image_features(**inp)
            emb = emb / emb.norm(dim=-1, keepdim=True)
            chunks.append(emb.cpu().numpy())
    return np.concatenate(chunks, axis=0)


def encode_texts(model, processor, device, texts: list[str]) -> np.ndarray:
    with torch.no_grad():
        inp = processor(text=texts, return_tensors="pt", padding=True).to(device)
        emb = model.get_text_features(**inp)
        emb = emb / emb.norm(dim=-1, keepdim=True)
    return emb.cpu().numpy()


def merge_intervals(intervals: list[Interval], gap: float = 0.16) -> list[Interval]:
    if not intervals:
        return []
    intervals = sorted(intervals, key=lambda x: x.start)
    out = [intervals[0]]
    for cur in intervals[1:]:
        prev = out[-1]
        if cur.kind == prev.kind and cur.start <= prev.end + gap:
            prev.end = max(prev.end, cur.end)
            prev.score = max(prev.score, cur.score)
        else:
            out.append(cur)
    return out


def detect_baseline(path: Path, model, processor, device) -> tuple[list[Interval], dict]:
    cap = cv2.VideoCapture(str(path))
    times = np.arange(0.05, DURATION - 0.05, 0.10)
    images: list[Image.Image] = []
    green: list[float] = []
    valid_times: list[float] = []
    for t in times:
        im = get_frame(cap, float(t))
        if im is None:
            continue
        crop = portrait_crop(im, 0.5).resize((224, 224), Image.Resampling.LANCZOS)
        arr = np.asarray(crop).astype(np.float32) / 255.0
        g = float(arr[...,1].mean() - 0.5 * (arr[...,0].mean() + arr[...,2].mean()))
        images.append(crop)
        green.append(g)
        valid_times.append(float(t))
    cap.release()

    image_emb = encode_images(model, processor, device, images)
    text_emb = encode_texts(model, processor, device, LABELS)
    sims = image_emb @ text_emb.T
    green_arr = np.asarray(green)
    green_z = (green_arr - np.median(green_arr)) / (np.std(green_arr) + 1e-6)

    farc_comp = np.max(sims[:, 1:], axis=1)
    farc_score = (sims[:,0] - farc_comp) + 0.010 * green_z
    flag_comp = np.max(np.delete(sims, [6], axis=1), axis=1)
    flag_score = sims[:,6] - flag_comp
    title_top = np.argmax(sims, axis=1) == 7

    # All samples that are plausibly guerrilla footage. Expansion covers the
    # rapid glitch frames and flashes at each side of the shot.
    f_thresh = max(float(np.quantile(farc_score, 0.80)), -0.010)
    raw_farc: list[Interval] = []
    for t, score, top, gz in zip(valid_times, farc_score, np.argmax(sims, axis=1), green_z):
        if not title_top[len(raw_farc) if False else 0]:
            pass
        if (top == 0 or (score >= f_thresh and gz > -0.15)) and top != 7:
            raw_farc.append(Interval(max(0.0, t-0.13), min(DURATION, t+0.13), "bank", float(score)))
    farc = merge_intervals(raw_farc, 0.18)

    # Drop tiny glitch-only detections and implausibly long false positives.
    farc = [x for x in farc if x.duration >= 0.18 and x.duration <= 2.2]
    farc.sort(key=lambda x: x.score, reverse=True)
    if len(farc) > 7:
        farc = farc[:7]
    farc.sort(key=lambda x: x.start)

    # Guarantee three distinct bank insert opportunities by taking the three
    # strongest separated guerrilla peaks when grouping was too conservative.
    if len(farc) < 3:
        order = np.argsort(farc_score)[::-1]
        chosen: list[float] = [0.5*(x.start+x.end) for x in farc]
        for idx in order:
            t = valid_times[int(idx)]
            if title_top[int(idx)] or any(abs(t-c) < 0.65 for c in chosen):
                continue
            chosen.append(t)
            farc.append(Interval(max(0,t-0.28), min(DURATION,t+0.32), "bank", float(farc_score[int(idx)])))
            if len(farc) >= 3:
                break
        farc = merge_intervals(sorted(farc, key=lambda x:x.start), 0.08)

    # Use the strongest compact flag-burning cluster, excluding bank windows.
    flag_order = np.argsort(flag_score)[::-1]
    flag: Interval | None = None
    for idx in flag_order:
        t = valid_times[int(idx)]
        if title_top[int(idx)] or any(x.start-0.2 <= t <= x.end+0.2 for x in farc):
            continue
        flag = Interval(max(0,t-0.42), min(DURATION,t+0.46), "flag", float(flag_score[int(idx)]))
        break
    if flag is None:
        raise RuntimeError("Could not identify a flag-burning shot in the baseline")

    # Expand bank windows modestly to ensure no jungle frames survive, then
    # resolve any overlap with the independently detected flag window.
    expanded: list[Interval] = []
    for x in farc:
        expanded.append(Interval(max(0,x.start-0.08), min(DURATION,x.end+0.08), x.kind, x.score))
    expanded = merge_intervals(expanded, 0.08)
    expanded = [x for x in expanded if x.end <= flag.start-0.03 or x.start >= flag.end+0.03]
    intervals = sorted(expanded + [flag], key=lambda x:x.start)

    # Keep a maximum of about four seconds of replacement so the rest of the
    # approved edit remains untouched.
    bank_total = sum(x.duration for x in intervals if x.kind == "bank")
    if bank_total > 4.0:
        banks = sorted([x for x in intervals if x.kind=="bank"], key=lambda x:x.score, reverse=True)
        kept=[]; total=0.0
        for x in banks:
            if total + x.duration <= 4.0 or len(kept)<3:
                kept.append(x); total += x.duration
        intervals = sorted(kept + [flag], key=lambda x:x.start)

    diagnostics = {
        "sample_times": valid_times,
        "similarities": sims.tolist(),
        "green_excess": green,
        "farc_score": farc_score.tolist(),
        "flag_score": flag_score.tolist(),
        "labels": LABELS,
        "detected_intervals": [asdict(x) for x in intervals],
    }
    return intervals, diagnostics


def ocr_chars(im: Image.Image) -> int:
    txt = pytesseract.image_to_string(im.resize((720,1280), Image.Resampling.LANCZOS), config="--psm 11")
    return sum(ch.isalnum() for ch in txt)


def choose_source_moment(path: Path, prompt: str, model, processor, device, duration_needed: float) -> tuple[float,float,dict]:
    dur = video_duration(path)
    cap = cv2.VideoCapture(str(path))
    if dur < 1.0:
        raise RuntimeError(f"Source too short: {path}")
    step = 0.35 if dur <= 40 else 0.75
    times = np.arange(0.35, max(0.36, dur-0.35), step)
    anchors = [0.05,0.25,0.50,0.75,0.95]
    images=[]; keys=[]
    for t in times:
        im=get_frame(cap,float(t))
        if im is None: continue
        for a in anchors:
            crop=portrait_crop(im,a).resize((224,224),Image.Resampling.LANCZOS)
            images.append(crop); keys.append((float(t),float(a)))
    cap.release()
    if not images:
        raise RuntimeError(f"No readable frames in {path}")
    iemb=encode_images(model,processor,device,images)
    temb=encode_texts(model,processor,device,[prompt])[0]
    scores=iemb@temb
    order=np.argsort(scores)[::-1]
    reviewed=[]
    best=None
    for idx in order[:30]:
        t,a=keys[int(idx)]
        cap=cv2.VideoCapture(str(path)); im=get_frame(cap,t); cap.release()
        if im is None: continue
        crop=portrait_crop(im,a)
        chars=ocr_chars(crop)
        adjusted=float(scores[int(idx)]) - min(chars,80)*0.0009
        reviewed.append({"time":t,"anchor":a,"clip_similarity":float(scores[int(idx)]),"ocr_chars":chars,"adjusted":adjusted})
        if best is None or adjusted>best[0]:
            best=(adjusted,t,a,chars,crop)
    if best is None:
        raise RuntimeError(f"Unable to select clean moment in {path}")
    _,t,a,chars,crop=best
    source_start=max(0.0,min(dur-duration_needed-0.05,t-duration_needed*0.35))
    return source_start,a,{"duration":dur,"chosen_time":t,"source_start":source_start,"anchor":a,"ocr_chars":chars,"reviewed":reviewed}


def esc_path(p: Path) -> str:
    return str(p).replace("'", "'\\''")


def build_filter(intervals: list[Interval], source_meta: list[dict]) -> str:
    chains=[]; pieces=[]; cursor=0.0; piece=0
    for it in intervals:
        if it.start > cursor + 0.001:
            chains.append(f"[0:v]trim=start={cursor:.6f}:end={it.start:.6f},setpts=PTS-STARTPTS,fps={FPS},scale={WIDTH}:{HEIGHT},setsar=1,format=yuv420p[b{piece}]")
            pieces.append(f"[b{piece}]"); piece+=1
        inp=it.source_index
        a=it.anchor
        # Portrait crop, oversized rescale and animated recrop create a zoom
        # punch and screen shake while permanently excluding source corners.
        chains.append(
            f"[{inp}:v]trim=start={it.source_start:.6f}:duration={it.duration:.6f},setpts=PTS-STARTPTS,"
            f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT}:x='(iw-ow)*{a:.4f}':y='(ih-oh)/2',setsar=1,fps={FPS},"
            f"scale=1188:2112,crop={WIDTH}:{HEIGHT}:x='54+9*sin(39*t)':y='96+11*cos(43*t)',"
            f"eq=contrast=1.16:saturation=1.25:brightness=-0.015,"
            f"colorbalance=rs=.035:bs=.045,noise=alls=7:allf=t+u,"
            f"drawgrid=w=iw:h=4:t=1:c=black@0.11,unsharp=5:5:0.55:5:5:0,"
            f"negate=enable='lt(t,0.017)',format=yuv420p[r{piece}]"
        )
        pieces.append(f"[r{piece}]"); piece+=1
        cursor=it.end
    if cursor < DURATION-0.001:
        chains.append(f"[0:v]trim=start={cursor:.6f}:end={DURATION:.6f},setpts=PTS-STARTPTS,fps={FPS},scale={WIDTH}:{HEIGHT},setsar=1,format=yuv420p[b{piece}]")
        pieces.append(f"[b{piece}]"); piece+=1
    chains.append("".join(pieces)+f"concat=n={len(pieces)}:v=1:a=0,fps={FPS},trim=duration={DURATION},setpts=PTS-STARTPTS,format=yuv420p[vout]")
    return ";".join(chains)


def make_replacement_board(paths: list[Path], choices: list[dict], out: Path) -> None:
    thumbs=[]
    for p,ch in zip(paths,choices):
        cap=cv2.VideoCapture(str(p)); im=get_frame(cap,float(ch["chosen_time"])); cap.release()
        if im is None: continue
        im=portrait_crop(im,float(ch["anchor"])).resize((270,480),Image.Resampling.LANCZOS)
        d=ImageDraw.Draw(im); d.rectangle((0,0,270,34),fill=(0,0,0)); d.text((8,8),p.stem,fill=(255,255,255))
        thumbs.append(im)
    board=Image.new("RGB",(270*len(thumbs),480),(0,0,0))
    for i,im in enumerate(thumbs): board.paste(im,(270*i,0))
    board.save(out,quality=92)


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--baseline",required=True,type=Path)
    ap.add_argument("--bank",required=True,type=Path,nargs=3)
    ap.add_argument("--flag",required=True,type=Path)
    ap.add_argument("--output-dir",required=True,type=Path)
    args=ap.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=True)

    for p in [args.baseline,*args.bank,args.flag]:
        if not p.exists() or p.stat().st_size<10000: raise FileNotFoundError(p)
    base_info=ffprobe(args.baseline)
    v=next(s for s in base_info["streams"] if s["codec_type"]=="video")
    if int(v["width"])!=WIDTH or int(v["height"])!=HEIGHT:
        raise RuntimeError(f"Baseline is not {WIDTH}x{HEIGHT}: {v}")

    model,processor,device=load_clip()
    intervals,diagnostics=detect_baseline(args.baseline,model,processor,device)
    bank_intervals=[x for x in intervals if x.kind=="bank"]
    if len(bank_intervals)<3:
        raise RuntimeError(f"Only {len(bank_intervals)} bank replacement windows detected")

    choices=[]
    bank_prompt="masked armed criminals carrying guns and cash during a bank robbery"
    for p in args.bank:
        maxdur=max((x.duration for x in bank_intervals),default=1.0)+0.5
        ss,a,meta=choose_source_moment(p,bank_prompt,model,processor,device,maxdur)
        choices.append(meta)
    flag_prompt="a clearly recognizable United States American flag actively burning in flames while demonstrators stand around it"
    flag_interval=next(x for x in intervals if x.kind=="flag")
    ss,a,flag_choice=choose_source_moment(args.flag,flag_prompt,model,processor,device,flag_interval.duration+0.5)

    bank_n=0
    for it in intervals:
        if it.kind=="bank":
            idx=bank_n%3
            it.source_index=idx+1
            it.source_start=float(choices[idx]["source_start"])+(bank_n//3)*0.25
            it.anchor=float(choices[idx]["anchor"])
            bank_n+=1
        else:
            it.source_index=4
            it.source_start=float(flag_choice["source_start"])
            it.anchor=float(flag_choice["anchor"])

    report={
        "baseline":str(args.baseline),
        "baseline_ffprobe":base_info,
        "replacement_intervals":[asdict(x) for x in intervals],
        "bank_sources":[str(p) for p in args.bank],
        "bank_choices":choices,
        "flag_source":str(args.flag),
        "flag_choice":flag_choice,
        "detector":diagnostics,
    }
    (args.output_dir/"replacement_report.json").write_text(json.dumps(report,indent=2))
    make_replacement_board([*args.bank,args.flag],[*choices,flag_choice],args.output_dir/"replacement_contact_board.jpg")

    graph=build_filter(intervals,[*choices,flag_choice])
    (args.output_dir/"filter_complex.txt").write_text(graph)
    master=args.output_dir/"do_crime_dont_vote_BANK_ROBBERY_CORRECTED_60fps.mp4"
    cmd=["ffmpeg","-y","-hide_banner","-loglevel","warning","-i",str(args.baseline)]
    for p in args.bank: cmd += ["-i",str(p)]
    cmd += ["-i",str(args.flag),"-filter_complex",graph,"-map","[vout]","-map","0:a:0?",
            "-c:v","libx264","-preset","medium","-crf","16","-profile:v","high","-level","4.2",
            "-pix_fmt","yuv420p","-r",str(FPS),"-frames:v",str(int(DURATION*FPS)),
            "-c:a","aac","-b:a","256k","-ar","48000","-ac","2","-t",f"{DURATION:.3f}",
            "-movflags","+faststart",str(master)]
    run(cmd)
    run(["ffmpeg","-v","error","-i",str(master),"-f","null","-"])

    final_info=ffprobe(master)
    vv=next(s for s in final_info["streams"] if s["codec_type"]=="video")
    if int(vv["width"])!=WIDTH or int(vv["height"])!=HEIGHT or vv["codec_name"]!="h264":
        raise RuntimeError(f"Bad final video stream: {vv}")
    if abs(float(final_info["format"]["duration"])-DURATION)>0.02:
        raise RuntimeError(f"Bad duration: {final_info['format']['duration']}")
    frames=int(subprocess.check_output([
        "ffprobe","-v","error","-count_frames","-select_streams","v:0",
        "-show_entries","stream=nb_read_frames","-of","default=nw=1:nk=1",str(master)
    ],text=True).strip())
    if frames!=900: raise RuntimeError(f"Expected 900 frames, got {frames}")
    final_info["validated_frame_count"]=frames
    (args.output_dir/"final_ffprobe.json").write_text(json.dumps(final_info,indent=2))

    run(["ffmpeg","-y","-hide_banner","-loglevel","error","-i",str(master),
         "-vf","fps=4/3,scale=216:384,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='%{pts\\:hms}':x=6:y=6:fontsize=16:fontcolor=white:borderw=2:bordercolor=black,tile=5x4:padding=4:margin=4:color=black",
         "-frames:v","1","-q:v","2",str(args.output_dir/"final_contact_sheet.jpg")])
    print(json.dumps({"master":str(master),"frames":frames,"duration":final_info["format"]["duration"],"intervals":[asdict(x) for x in intervals]},indent=2))

if __name__=="__main__":
    main()
