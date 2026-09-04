#!/usr/bin/env python3
"""Choose a visually active, usable source window and an optional horizontal anchor."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np


def analyze(path: Path, mode: str, max_seconds: float = 150.0) -> dict[str, float]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
    duration = frame_count / fps if frame_count else max_seconds
    duration = min(duration, max_seconds)
    sample_step = 0.75
    times = np.arange(0.0, max(1.0, duration), sample_step)
    rows: list[tuple[float, float, float]] = []
    prev_gray: np.ndarray | None = None

    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, float(t * 1000.0))
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        h, w = frame.shape[:2]
        # Ignore the outer 8% and the lowest 14%; these are common bug/lower-third regions.
        frame = frame[int(h * 0.05):int(h * 0.86), int(w * 0.08):int(w * 0.92)]
        small = cv2.resize(frame, (320, 180), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        brightness = float(gray.mean())
        contrast = float(gray.std())
        motion = 0.0 if prev_gray is None else float(cv2.absdiff(gray, prev_gray).mean())
        prev_gray = gray
        edges = cv2.Canny(gray, 70, 170)
        edge_frac = float((edges > 0).mean())
        sat = float(hsv[:, :, 1].mean())

        if mode == "flag":
            # Flame is normally orange/yellow; the flag contributes red and blue regions.
            orange = cv2.inRange(hsv, np.array([3, 110, 115]), np.array([34, 255, 255])) > 0
            red = ((hsv[:, :, 0] <= 10) | (hsv[:, :, 0] >= 170)) & (hsv[:, :, 1] > 95) & (hsv[:, :, 2] > 80)
            blue = (hsv[:, :, 0] >= 90) & (hsv[:, :, 0] <= 135) & (hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 55)
            orange_frac = float(orange.mean())
            red_frac = float(red.mean())
            blue_frac = float(blue.mean())
            center = orange[:, 56:264]
            if center.any():
                xs = np.where(center)[1] + 56
                anchor = float(xs.mean() / 319.0)
            else:
                anchor = 0.5
            score = (
                orange_frac * 900.0
                + min(red_frac, 0.10) * 180.0
                + min(blue_frac, 0.08) * 120.0
                + motion * 0.65
                + edge_frac * 30.0
                + contrast * 0.08
            )
        else:
            anchor = 0.5
            exposure_ok = 1.0 if 25.0 <= brightness <= 225.0 else 0.15
            score = exposure_ok * (
                motion * 1.15
                + edge_frac * 50.0
                + contrast * 0.12
                + sat * 0.025
            )
        # Avoid title cards and end credits when possible.
        if t < 3.0 or t > duration - 3.0:
            score *= 0.30
        rows.append((float(t), float(score), float(anchor)))

    cap.release()
    if not rows:
        raise RuntimeError(f"no frames decoded from {path}")

    window = 7.5 if mode == "flag" else 8.5
    best = None
    for start, _, _ in rows:
        subset = [r for r in rows if start <= r[0] < start + window]
        if len(subset) < 4:
            continue
        scores = sorted(r[1] for r in subset)
        # Robust mean favors consistently useful footage over a single flash.
        robust = float(np.mean(scores[len(scores) // 4:]))
        anchor = float(np.average([r[2] for r in subset], weights=[max(r[1], 0.01) for r in subset]))
        candidate = (robust, start, anchor)
        if best is None or candidate[0] > best[0]:
            best = candidate
    if best is None:
        best = (rows[0][1], rows[0][0], rows[0][2])

    score, start, anchor = best
    start = max(0.0, min(float(start), max(0.0, duration - window)))
    anchor = max(0.28, min(0.72, float(anchor)))
    return {
        "start": round(start, 3),
        "score": round(float(score), 4),
        "anchor_x": round(anchor, 4),
        "duration": round(float(duration), 3),
        "fps": round(float(fps), 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--mode", choices=("robbery", "flag"), default="robbery")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze(args.video, args.mode)
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
