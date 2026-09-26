#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "requests",
#   "yt-dlp",
#   "youtube-transcript-api",
#   "imageio-ffmpeg",
# ]
# ///
"""Lets Claude look at a video: cuts a piece and lays it out as frames.

The idea comes from bradautomates/claude-video (/watch): frames plus time-coded speech, a
frame budget from the piece's length, near-identical frames dropped. What is different here:
only the needed piece is downloaded (yt-dlp --download-sections), not the whole video; frames
can be taken where the speaker points at the screen (--grep over the captions); duplicates
are judged by the maximum difference, not the mean (see DEDUP_THRESHOLD).

Frame selection modes (one per run; --at/--grep add to any of them):
    default        evenly, fps chosen from the piece's length (frame budget)
    --fps F        evenly at a given rate (at most 2)
    --scene [T]    at shot changes (threshold 0..1, default 0.3)
    --keyframes    codec keyframes only: fast, for an overview of a long video
    --at T1,T2     exactly at these moments; without a piece or a mode, only these
    --grep RE      moments where RE is said in the captions ("slide|on screen|right here")

Output: a folder with frames t_MM-SS.jpg and index.md, a list "t=MM:SS path" and, with
--subs, the speech between this frame and the next. index.md is also printed to stdout.
All times (--start, --end, --at, frame names) are the original video's.

    uv run frames.py <URL|file> --start 12:30 --end 13:10 --subs
    uv run frames.py <URL> --grep "slide|on screen" --width 1024
    uv run frames.py <URL> --start 5:00 --end 5:20 --clip-only   # just cut the piece
    uv run frames.py <URL> --start 1:00 --end 3:00 --sheet       # overview as 5x4 sheets

Exit codes: 0 success, 1 error, 2 missing dependencies or bad arguments, 3 no frames.
"""

from __future__ import annotations

import argparse
import itertools
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import transcript as tr  # noqa: E402  shared binary lookup, yt-dlp and captions

EXIT_SUCCESS, EXIT_ERROR, EXIT_MISSING_DEPS, EXIT_NO_FRAMES = 0, 1, 2, 3

# Frame budget by piece length, from claude-video. It stops growing at 100: a long video is
# watched as an overview, not frame by frame.
BUDGET = [(30, 30), (60, 40), (180, 60), (600, 80)]
MAX_BUDGET = 100
MAX_FPS = 2.0
# A duplicate = no cell of the 32x18 thumbnail got brighter or darker by more than
# DEDUP_THRESHOLD of 255. Not the mean over 16x16 <= 2 as in claude-video: on dark motion
# graphics the mean dropped 36 frames of 40 together with three distinct screens (small text
# on a dark background barely moves the mean but does move the maximum). With max <= 6 the
# same piece kept 22 frames, every screen in place.
DEDUP_THRESHOLD = 6
THUMB_W, THUMB_H = 32, 18
AT_PAD = 1.5    # --grep: a frame slightly after the phrase starts; by then the slide is on screen

_names = itertools.count()


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def parse_time(value: str) -> float:
    """SS, MM:SS or HH:MM:SS (fractional seconds allowed) to seconds."""
    parts = value.strip().split(":")
    if not 1 <= len(parts) <= 3:
        raise argparse.ArgumentTypeError(f"not a time: {value}")
    try:
        nums = [float(x) for x in parts]
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a time: {value}") from None
    seconds = 0.0
    for n in nums:
        seconds = seconds * 60 + n
    return seconds


def fmt(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def fmt_frame(seconds: float) -> str:
    """Frame time with tenths: at 2 fps whole seconds would merge neighbours."""
    whole = int(seconds)
    if seconds - whole >= 0.95:
        return fmt(whole + 1)
    tenth = int(round((seconds - whole) * 10))
    return fmt(whole) if tenth == 0 else f"{fmt(whole)}.{tenth}"


def slug_time(seconds: float) -> str:
    return fmt_frame(seconds).replace(":", "-")


# -- Source: a link or a file ------------------------------------------------------------------
def format_ladder(width: int, with_audio: bool) -> list[str]:
    """Formats one by one, as in transcript.download_audio: YouTube answers 403 to selector
    expressions but serves a single format number. Height follows frame width: 512 px is fine
    with 480p, text on screen needs 720p and up."""
    if width <= 640:
        yt, generic = ["135", "244"], "bv*[height<=480]"
    elif width <= 1280:
        yt, generic = ["136", "247"], "bv*[height<=720]"
    else:
        yt, generic = ["137", "248"], "bv*[height<=1080]"
    if with_audio:
        # Not +140: videos with auto-dubbing name their tracks 140-0, 140-1, and a bare 140 is
        # "not available". ba takes the track marked original (default).
        return [f"{f}+ba" for f in yt] + ["18", f"{generic}+ba/b"]
    return yt + [generic, "b"]


def download(url: str, sections: list[tuple[float, float | None]], width: int,
             with_audio: bool, workdir: Path) -> tuple[list[tuple[Path, float]], str]:
    """Download only the needed pieces, all in one yt-dlp call. Returns ([(file, offset)],
    title); the offset is the second of the original where the file starts. Empty sections
    means the whole video."""
    cmd = tr._yt_dlp_cmd()
    if not cmd:
        log("yt-dlp not found: run the script with `uv run`")
        sys.exit(EXIT_MISSING_DEPS)
    cut: list[str] = []
    for a, b in sections:
        cut += ["--download-sections", f"*{a:.2f}-{b:.2f}" if b is not None else f"*{a:.2f}-inf"]
    if cut:
        # --force-keyframes-at-cuts re-encodes the edges: without it the piece starts at the
        # nearest keyframe before the start, and every time code shifts.
        cut.append("--force-keyframes-at-cuts")
    template = "src_%(section_start)s.%(ext)s" if sections else "src_0.%(ext)s"
    last_error = "no output"
    for fmt_id in format_ladder(width, with_audio):
        for old in workdir.glob("src_*"):
            old.unlink(missing_ok=True)
        args = cmd + ["-f", fmt_id, *cut, "--no-playlist", "--no-warnings",
                      "--print", "after_move:title", "--no-simulate", "-o", str(workdir / template), url]
        try:
            result = tr._run(args, timeout=3600)
        except subprocess.TimeoutExpired:
            log("yt-dlp timed out")
            break
        files = [f for f in workdir.glob("src_*") if f.suffix.lower() not in (".part", ".ytdl")]
        if files and result.returncode == 0:
            titles = [ln for ln in result.stdout.splitlines() if ln.strip()]
            out = []
            for f in files:
                try:
                    out.append((f, float(f.stem.split("_", 1)[1])))
                except ValueError:
                    out.append((f, sections[0][0] if sections else 0.0))
            log(f"downloaded format {fmt_id}: {len(out)} file(s)")
            return sorted(out, key=lambda x: x[1]), (titles[-1] if titles else "")
        detail = (result.stderr or "").strip().splitlines()
        last_error = detail[-1][:200] if detail else "no output"
        log(f"format {fmt_id} failed ({last_error}): trying the next one")
    log(f"the video did not download: {last_error}")
    sys.exit(EXIT_ERROR)


def probe_duration(path: Path) -> float:
    ffprobe = tr._find_binary("ffprobe")
    if not ffprobe:
        return 0.0
    r = tr._run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=nw=1:nk=1", str(path)], timeout=60)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def cut_local(ffmpeg: str, src: Path, start: float | None, end: float | None, dst: Path) -> None:
    """An exact cut from a local file (re-encoded, or the edge drifts). -ss before -i with
    re-encoding is exact and fast; time after it counts from zero, so the end is given as a
    duration (-t), not as a mark of the original."""
    args = [ffmpeg, "-y", "-v", "error"]
    if start:
        args += ["-ss", f"{start:.3f}"]
    args += ["-i", str(src)]
    if end is not None:
        args += ["-t", f"{end - (start or 0):.3f}"]
    args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", str(dst)]
    r = tr._run(args, timeout=1800)
    if r.returncode != 0:
        log(f"ffmpeg did not cut: {(r.stderr or '').strip()[-300:]}")
        sys.exit(EXIT_ERROR)


# -- Frames ------------------------------------------------------------------------------------
Frame = tuple[float, Path, bytes]   # time from the file start, jpg, thumbnail (b"" = ordered)


def auto_fps(duration: float) -> float:
    budget = next((n for limit, n in BUDGET if duration <= limit), MAX_BUDGET)
    return min(MAX_FPS, budget / max(duration, 1.0))


def extract(ffmpeg: str, src: Path, select: str, input_opts: list[str], width: int, outdir: Path) -> list[Frame]:
    """One ffmpeg pass, two outputs: full frames to disk and grey thumbnails to a pipe for
    comparison. split guarantees the i-th big and the i-th small are the same frame;
    showinfo gives its real time."""
    graph = (f"[0:v]{select},showinfo,split=2[a][b];"
             f"[a]scale={width}:-2[big];"
             f"[b]scale={THUMB_W}:{THUMB_H},format=gray[small]")
    args = [ffmpeg, "-hide_banner", *input_opts, "-i", str(src), "-filter_complex", graph,
            "-map", "[big]", "-fps_mode", "vfr", "-q:v", "3", str(outdir / "raw_%05d.jpg"),
            "-map", "[small]", "-fps_mode", "vfr", "-f", "rawvideo", "pipe:1"]
    proc = subprocess.run(args, capture_output=True, timeout=3600)
    if proc.returncode != 0:
        log(f"ffmpeg failed: {proc.stderr.decode('utf-8', 'replace').strip()[-400:]}")
        sys.exit(EXIT_ERROR)
    times = [float(m) for m in re.findall(rb"pts_time:\s*([-\d.]+)", proc.stderr)]
    thumbs = proc.stdout
    size = THUMB_W * THUMB_H
    files = sorted(outdir.glob("raw_*.jpg"))
    n = min(len(files), len(times), len(thumbs) // size)
    if not (len(files) == len(times) == len(thumbs) // size):
        log(f"warning: {len(files)} frames, {len(times)} timestamps, {len(thumbs) // size} thumbnails: "
            f"taking the first {n}")
    return [(times[i], files[i], thumbs[i * size:(i + 1) * size]) for i in range(n)]


def extract_at(ffmpeg: str, src: Path, moments: list[float], width: int, outdir: Path) -> list[Frame]:
    """One frame exactly at each moment (time from the file start). These are ordered
    explicitly, so they have no thumbnail and deduplication leaves them alone."""
    out = []
    for t in moments:
        path = outdir / f"at_{next(_names):05d}.jpg"
        r = tr._run([ffmpeg, "-y", "-v", "error", "-ss", f"{max(t, 0):.3f}", "-i", str(src),
                     "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "3", str(path)], timeout=300)
        if r.returncode == 0 and path.is_file():
            out.append((t, path, b""))
        else:
            log(f"no frame at {fmt(t)} from the file start (past the end?)")
    return out


def dedup(frames: list[Frame]) -> list[Frame]:
    kept: list[Frame] = []
    for frame in frames:
        if kept and frame[2] and kept[-1][2]:
            diff = max(abs(a - b) for a, b in zip(frame[2], kept[-1][2], strict=True))
            if diff <= DEDUP_THRESHOLD:
                frame[1].unlink(missing_ok=True)
                continue
        kept.append(frame)
    return kept


def thin(items: list, limit: int, drop=None) -> list:
    """Thin evenly down to limit, keeping the first and the last."""
    if len(items) <= limit:
        return items
    if limit <= 1:
        keep = {0}
    else:
        step = (len(items) - 1) / (limit - 1)
        keep = {round(i * step) for i in range(limit)}
    for i, item in enumerate(items):
        if i not in keep and drop:
            drop(item)
    return [x for i, x in enumerate(items) if i in keep]


SHEET_COLS, SHEET_ROWS, SHEET_CELL = 5, 4, 312   # 5 x 312 is about 1568, the image side limit


def contact_sheets(ffmpeg: str, paths: list[Path], outdir: Path) -> list[Path]:
    """Frames as a 5x4 grid per sheet, left to right, top to bottom: the whole piece at a
    glance. That is how lost screens in deduplication were noticed: invisible one frame at a
    time, obvious on a sheet."""
    sheets = []
    per = SHEET_COLS * SHEET_ROWS
    for n, i in enumerate(range(0, len(paths), per), 1):
        chunk = paths[i:i + per]
        listing = outdir / "_work" / f"sheet_{n}.txt"
        # Paths in a concat list: forward slashes, single quotes.
        listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in chunk), encoding="utf-8")
        rows = -(-len(chunk) // SHEET_COLS)
        dst = outdir / f"sheet_{n:02d}.jpg"
        r = tr._run([ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
                     "-vf", f"scale={SHEET_CELL}:-2,tile={SHEET_COLS}x{rows}:padding=4",
                     "-frames:v", "1", "-q:v", "3", str(dst)], timeout=300)
        if r.returncode == 0 and dst.is_file():
            sheets.append(dst)
        else:
            log(f"sheet {n} was not built: {(r.stderr or '').strip()[-200:]}")
    return sheets


# -- Captions ----------------------------------------------------------------------------------
def fetch_subs(url: str, lang: str, workdir: Path) -> list[dict]:
    vid = tr.extract_video_id(url)
    got = tr.tier1_transcript_api(vid, lang) if vid else None
    if not got:
        subdir = workdir / "subs"
        subdir.mkdir(exist_ok=True)
        got = tr.tier2_ytdlp_subs(url, lang, [], subdir)
    if not got:
        log("no captions: frames will have no speech (Whisper is not called for a piece)")
        return []
    log(f"captions: {got[1]}")
    return got[0]


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="Frames and pieces of a video, for looking at it")
    p.add_argument("video", help="a link or a file path")
    p.add_argument("--start", type=parse_time, help="piece start: SS, MM:SS, HH:MM:SS")
    p.add_argument("--end", type=parse_time, help="piece end")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--fps", type=float, help=f"frames per second (at most {MAX_FPS})")
    mode.add_argument("--scene", type=float, nargs="?", const=0.3, help="frames at shot changes, threshold 0..1 (default 0.3)")
    mode.add_argument("--keyframes", action="store_true", help="keyframes only")
    p.add_argument("--at", help="moments, comma-separated: 1:05,2:30")
    p.add_argument("--grep", help="regex over the captions: a frame where it is said")
    p.add_argument("--max-frames", type=int, default=MAX_BUDGET, help=f"frame ceiling (default {MAX_BUDGET})")
    p.add_argument("--width", type=int, default=512, help="frame width; 1024 for code and slides")
    p.add_argument("--no-dedup", action="store_true", help="keep near-identical frames")
    p.add_argument("--sheet", action="store_true", help="also contact sheets: 20 frames in a grid on one image")
    p.add_argument("--subs", action="store_true", help="put the speech under the frames")
    p.add_argument("--lang", default="en", help="caption language")
    p.add_argument("--clip-only", action="store_true", help="only cut the piece to mp4 with sound, no frames")
    p.add_argument("--offset", type=parse_time, default=0.0, help="for a local cut file: at what time of the original it starts")
    p.add_argument("--out-dir", help="where to put the output (default: a temp folder)")
    a = p.parse_args()

    ffmpeg = tr._find_binary("ffmpeg")
    if not ffmpeg:
        log("ffmpeg not found")
        sys.exit(EXIT_MISSING_DEPS)
    if a.start is not None and a.end is not None and a.end <= a.start:
        p.error("--end must be greater than --start")
    if a.fps is not None and not 0 < a.fps <= MAX_FPS:
        p.error(f"--fps must be within (0, {MAX_FPS}]")

    is_url = bool(re.match(r"https?://", a.video))
    local = None if is_url else Path(a.video)
    if local is not None and not local.is_file():
        p.error(f"no file: {local}")
    if a.grep and not is_url:
        p.error("--grep searches the site's captions; a local file has none")
    at_list = [parse_time(x) for x in a.at.split(",")] if a.at else []

    outdir = Path(a.out_dir) if a.out_dir else Path(tempfile.mkdtemp(prefix="frames_"))
    if (outdir / "index.md").exists():
        p.error(f"{outdir} holds a previous run: frames would mix, pick another folder")
    outdir.mkdir(parents=True, exist_ok=True)
    work = outdir / "_work"
    work.mkdir(exist_ok=True)

    subs: list[dict] = []
    if is_url and (a.subs or a.grep):
        subs = fetch_subs(a.video, a.lang, work)
    if a.grep:
        rx = re.compile(a.grep, re.IGNORECASE)
        hits = [s["start"] + AT_PAD for s in subs if rx.search(s["text"])]
        hits = [t for t in hits if (a.start is None or t >= a.start) and (a.end is None or t <= a.end)]
        log(f"--grep: {len(hits)} match(es)")
        if not hits and not at_list and a.start is None and a.end is None:
            log("--grep found nothing and there is no other frame selection")
            sys.exit(EXIT_NO_FRAMES)
        at_list += hits
    at_list = sorted(set(round(t, 1) for t in at_list))

    start, end = a.start, a.end
    only_at = bool(at_list) and a.fps is None and a.scene is None and not a.keyframes \
        and start is None and end is None and not a.clip_only
    if only_at and len(at_list) > a.max_frames:
        log(f"{len(at_list)} moments: thinning to {a.max_frames}")
        at_list = thin(at_list, a.max_frames)

    frames: list[Frame] = []      # times here are already the original's
    ordered: set[Path] = set()
    how, src, lo, hi = "", None, 0.0, 0.0

    if only_at:
        # No need to download the whole video for a few moments: a two-second piece per
        # moment, all in one yt-dlp call. On an hour-long video three moments took 34 s, and
        # the frames matched those taken straight from the stream (ffmpeg on the direct link
        # took 25-31 s for EACH frame).
        if is_url:
            pieces, title = download(a.video, [(max(0.0, t - 1), t + 1) for t in at_list], a.width, False, work)
            for f, off in pieces:
                t = min(at_list, key=lambda m: abs(max(0.0, m - 1) - off))
                frames += [(t, fp, b"") for _, fp, _ in extract_at(ffmpeg, f, [t - off], a.width, work)]
        else:
            title = local.stem
            frames = [(t + a.offset, fp, b"") for t, fp, _ in
                      extract_at(ffmpeg, local, [t - a.offset for t in at_list], a.width, work)]
        ordered = {f[1] for f in frames}
        how = f"given moments: {len(at_list)}"
        if frames:
            lo, hi = min(f[0] for f in frames), max(f[0] for f in frames)
    else:
        if is_url:
            section = [(start or 0.0, end)] if (start is not None or end is not None) else []
            pieces, title = download(a.video, section, a.width, a.clip_only, work)
            src, offset = pieces[0]
        else:
            title = local.stem
            # A cut file starts at --offset while --start/--end are times of the original,
            # so they are translated into the file by subtraction.
            if start is not None or end is not None or a.clip_only:
                src = work / "cut.mp4"
                cut_local(ffmpeg, local, (start - a.offset) if start is not None else None,
                          (end - a.offset) if end is not None else None, src)
                offset = start if start is not None else a.offset
            else:
                src, offset = local, a.offset

        duration = probe_duration(src)
        if a.clip_only:
            dst = outdir / f"clip_{slug_time(offset)}_{slug_time(offset + duration)}{src.suffix}"
            src.replace(dst)
            print(f"piece: {dst}")
            sys.exit(EXIT_SUCCESS)
        if duration <= 0:
            log("could not read the file's length (ffprobe)")
            sys.exit(EXIT_ERROR)
        lo, hi = offset, offset + duration

        input_opts: list[str] = []
        if a.keyframes:
            select, how = "select='eq(pict_type,I)'", "keyframes"
            input_opts = ["-skip_frame", "nokey"]
        elif a.scene is not None:
            select, how = f"select='gt(scene,{a.scene})'", f"shot changes, threshold {a.scene}"
        else:
            fps = a.fps or auto_fps(duration)
            select, how = f"fps={fps:.4f}", f"{fps:.2f} fps" + ("" if a.fps else " (auto)")
        got = extract(ffmpeg, src, select, input_opts, a.width, work)
        # Shot detection misses the very start: add the piece's first frame ourselves.
        if a.scene is not None and (not got or got[0][0] > 0.5):
            got = extract_at(ffmpeg, src, [0.0], a.width, work) + got
        if not a.no_dedup:
            before = len(got)
            got = dedup(got)
            if before != len(got):
                log(f"near-identical frames dropped: {before - len(got)}")
        got = thin(got, a.max_frames, drop=lambda f: f[1].unlink(missing_ok=True))
        frames = [(t + offset, fp, th) for t, fp, th in got]

        if at_list:
            inside = [t for t in at_list if lo <= t <= hi + 0.5]
            if len(inside) < len(at_list):
                log(f"moments outside the piece: {len(at_list) - len(inside)}, skipped")
            extra = [(t + offset, fp, b"") for t, fp, _ in
                     extract_at(ffmpeg, src, [t - offset for t in inside], a.width, work)]
            ordered = {f[1] for f in extra}
            frames += extra
            how += f" + given moments: {len(inside)}"

    if not frames:
        log("no frames came out")
        sys.exit(EXIT_NO_FRAMES)

    frames.sort(key=lambda f: f[0])
    final: list[tuple[float, Path, bool]] = []
    for t, path, _ in frames:
        name = outdir / f"t_{slug_time(t)}.jpg"
        if name.exists():   # an ordered moment coincided with an even frame
            path.unlink(missing_ok=True)
            continue
        path.replace(name)
        final.append((t, name, path in ordered))

    # Image tokens by Anthropic's formula: width x height / 750.
    h = 0
    ffprobe = tr._find_binary("ffprobe")
    if ffprobe:
        r = tr._run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                     "stream=height", "-of", "csv=p=0", str(final[0][1])], timeout=30)
        h = int(r.stdout.strip()) if r.stdout.strip().isdigit() else 0

    lines = [
        f"# Frames: {title or a.video}",
        "",
        f"- source: {a.video}",
        f"- piece: {fmt(lo)}-{fmt(hi)}",
        f"- frame selection: {how}",
        f"- frames: {len(final)}, {a.width}x{h}, about {len(final) * a.width * h // 750} image tokens"
        if h else f"- frames: {len(final)}",
        f"- folder: {outdir}",
    ]
    if a.sheet:
        for sheet in contact_sheets(ffmpeg, [f[1] for f in final], outdir):
            lines.append(f"- sheet: {sheet} (frames left to right, top to bottom, in the order below)")
    if src is not None and src != local:
        lines.append(f"- piece video: {src} (another frame mode on it without downloading: "
                     f"frames.py \"{src}\" --offset {fmt_frame(lo)} ...)")
    lines.append("")

    # For given moments lo..hi is not a piece but the spread of frames; each frame has its
    # own window below, so no cut here.
    in_window = subs if only_at else [s for s in subs if lo - 1 <= s["start"] <= hi]
    for i, (t, path, is_ordered) in enumerate(final):
        mark = "  (ordered)" if is_ordered else ""
        lines.append(f"## t={fmt_frame(t)}{mark}  {path}")
        if in_window:
            nxt = final[i + 1][0] if i + 1 < len(final) else hi + 0.01
            if only_at:   # frames far apart: speech only around the moment
                said = [s["text"] for s in in_window if t - AT_PAD - 4 <= s["start"] <= t + 4]
            else:
                said = [s["text"] for s in in_window if (i == 0 or t - 0.01 <= s["start"]) and s["start"] < nxt]
            said_text = " ".join(" ".join(said).split())
            if said_text:
                lines.append(f"> {said_text}")
        lines.append("")

    text = "\n".join(lines)
    (outdir / "index.md").write_text(text, encoding="utf-8")
    for leftover in list(work.glob("raw_*.jpg")) + list(work.glob("at_*.jpg")):
        leftover.unlink(missing_ok=True)
    if only_at:
        for piece in work.glob("src_*"):
            piece.unlink(missing_ok=True)
    print(text)


if __name__ == "__main__":
    main()
