#!/usr/bin/env python3
"""Render an HTML page to PNG frames with headless Chrome; assemble GIFs, MP4s, and stills with ffmpeg.

Standard library only. Needs two binaries:
  - Chrome or Chromium (default /usr/bin/google-chrome; set CHROME to override)
  - ffmpeg on PATH (set FFMPEG to override)

    python3 images/lifecycle/build.py

Each page renders one frame from its URL fragment (for example `#f=12&t=dark`).
Frames are captured at 2x; the GIF and the stills are downsampled with a Lanczos
filter, which gives clean anti-aliased text. The MP4 keeps the full 2x frames.
"""
import concurrent.futures
import os
import shutil
import subprocess
import tempfile
import time

CHROME = os.environ.get("CHROME", "/usr/bin/google-chrome")
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")


def shoot(html, fragment, png, width, height, scale=2, timeout=60):
    """Screenshot html#fragment into png at width x height CSS pixels (png is width*scale wide).

    Each capture gets its own throwaway profile so parallel captures never share
    state. With a custom profile Chrome writes the screenshot but may not exit on
    its own, so we wait until the PNG is complete and then stop the process."""
    if os.path.exists(png):
        os.remove(png)  # a stale file would look "complete" to the poll below
    profile = tempfile.mkdtemp(prefix="gifkit-chrome-")
    url = f"file://{os.path.abspath(html)}" + (f"#{fragment}" if fragment else "")
    proc = subprocess.Popen([
        CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
        "--no-default-browser-check", "--disable-extensions", "--mute-audio",
        f"--user-data-dir={profile}", f"--window-size={width},{height}",
        f"--force-device-scale-factor={scale}", "--virtual-time-budget=1500",
        f"--screenshot={png}", url,
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline, last = time.time() + timeout, -1
        while time.time() < deadline:
            if proc.poll() is not None and os.path.exists(png):
                break
            size = os.path.getsize(png) if os.path.exists(png) else -1
            if size > 0 and size == last:  # unchanged across two polls: fully written
                break
            last = size
            time.sleep(0.25)
        else:
            raise RuntimeError(f"no screenshot for {url} within {timeout}s")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        shutil.rmtree(profile, ignore_errors=True)
    if not os.path.exists(png) or os.path.getsize(png) == 0:
        raise RuntimeError(f"Chrome exited without a screenshot for {url}; is CHROME={CHROME} right?")


def render_frames(html, fragments, width, height, scale=2, workers=6):
    """Capture every fragment at width*scale x height*scale.

    Returns (tmpdir, [png paths in order]); remove tmpdir with cleanup() when done."""
    tmp = tempfile.mkdtemp(prefix="gifkit-frames-")
    pngs = [os.path.join(tmp, f"{i:04d}.png") for i in range(len(fragments))]
    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        list(pool.map(lambda i: shoot(html, fragments[i], pngs[i], width, height, scale), range(len(fragments))))
    return tmp, pngs


def cleanup(tmp):
    shutil.rmtree(tmp, ignore_errors=True)


def _ffmpeg(*args):
    subprocess.run([FFMPEG, "-hide_banner", "-y", "-loglevel", "error", *args], check=True)


def _concat_list(pngs, durations, tmp):
    """ffmpeg concat-demuxer listing that shows each PNG for its duration (ms)."""
    lines = []
    for path, ms in zip(pngs, durations):
        lines += [f"file '{os.path.abspath(path)}'", f"duration {ms / 1000:.3f}"]
    lines.append(lines[-2])  # the concat demuxer ignores the last duration unless the file repeats
    listing = os.path.join(tmp, "frames.txt")
    with open(listing, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return listing


def save_gif(pngs, durations, out, width, height, colors=256, dither="none"):
    """Write a looping GIF with per-frame durations (ms) and ONE palette shared by all frames (no flicker).

    palettegen sees every frame (stats_mode=full) and paletteuse maps each frame onto that
    single palette; diff_mode=rectangle re-encodes only the changed region of each frame.
    ffmpeg rounds concat-demuxer timestamps to 1/25 s and cannot know the last frame's delay,
    so the exact delays are written into the GIF afterwards (set_gif_delays)."""
    tmp = tempfile.mkdtemp(prefix="gifkit-gif-")
    try:
        listing = _concat_list(pngs, durations, tmp)
        scale = f"scale={width}:{height}:flags=lanczos"
        graph = (f"[0:v]{scale},split[a][b];[a]palettegen=max_colors={colors}:stats_mode=full:reserve_transparent=0[p];"
                 f"[b][p]paletteuse=dither={dither}:diff_mode=rectangle")
        _ffmpeg("-f", "concat", "-safe", "0", "-i", listing,
                "-filter_complex", graph, "-fps_mode", "vfr", "-frames:v", str(len(pngs)), "-loop", "0", out)
    finally:
        cleanup(tmp)
    set_gif_delays(out, durations)
    return os.path.getsize(out)


def set_gif_delays(path, durations):
    """Rewrite the delay of every frame's Graphic Control Extension (GIF89a) to durations (ms).

    Walks the GIF block structure (no pixel decoding), so it is exact and stdlib-only."""
    data = bytearray(open(path, "rb").read())
    if data[:6] not in (b"GIF89a", b"GIF87a"):
        raise ValueError(f"{path} is not a GIF")
    pos = 13
    if data[10] & 0x80:  # global color table
        pos += 3 * (2 << (data[10] & 7))
    gces = []
    while pos < len(data):
        block = data[pos]
        if block == 0x3B:  # trailer
            break
        if block == 0x21:  # extension: label, then data sub-blocks
            if data[pos + 1] == 0xF9:
                gces.append(pos)
            pos += 2
        elif block == 0x2C:  # image descriptor, optional local color table, LZW minimum code size
            packed = data[pos + 9]
            pos += 10 + (3 * (2 << (packed & 7)) if packed & 0x80 else 0) + 1
        else:
            raise ValueError(f"unexpected GIF block 0x{block:02x} at {pos}")
        while data[pos]:  # skip sub-blocks up to the terminator
            pos += data[pos] + 1
        pos += 1
    if len(gces) != len(durations):
        raise RuntimeError(f"{path}: {len(gces)} frames written, {len(durations)} expected; "
                           "ffmpeg merged or dropped frames")
    for at, ms in zip(gces, durations):
        cs = max(2, round(ms / 10))  # GIF delays are centiseconds; browsers treat <2 as slow
        data[at + 4:at + 6] = cs.to_bytes(2, "little")
    with open(path, "wb") as fh:
        fh.write(data)


def save_png(src, out, width=None, height=None):
    """Copy a captured PNG to out, downsampled to width x height when given."""
    if width and height:
        _ffmpeg("-i", src, "-vf", f"scale={width}:{height}:flags=lanczos", "-frames:v", "1",
                "-compression_level", "9", "-pred", "mixed", out)
    else:
        _ffmpeg("-i", src, "-frames:v", "1", "-compression_level", "9", "-pred", "mixed", out)
    return os.path.getsize(out)


def save_mp4(pngs, durations, out, fps=30, crf=22):
    """Write an H.264 MP4 (yuv420p, plays everywhere) that shows each PNG for its duration (ms).

    Frames go through ffmpeg's concat demuxer, which takes a per-image duration; fps resamples
    that to a constant rate."""
    tmp = tempfile.mkdtemp(prefix="gifkit-mp4-")
    try:
        listing = _concat_list(pngs, durations, tmp)
        _ffmpeg("-f", "concat", "-safe", "0", "-i", listing,
                "-t", f"{sum(durations) / 1000:.3f}",  # the repeated last file would otherwise add its own duration
                "-vf", f"fps={fps},scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p",
                "-c:v", "libx264", "-preset", "slow", "-crf", str(crf), "-tune", "stillimage",
                "-movflags", "+faststart", out)
    finally:
        cleanup(tmp)
    return os.path.getsize(out)
