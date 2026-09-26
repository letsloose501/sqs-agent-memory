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
"""Gets the text out of a video by climbing three tiers until one works.

    1. youtube-transcript-api   YouTube's ready captions. Instant, free.
    2. yt-dlp --write-auto-subs the same captions by another route (+ browser cookies).
                                Gets around some blocks; works beyond YouTube.
    3. Groq Whisper             downloads the audio and transcribes it. Works even when
                                there are no captions at all.

Output: Markdown with frontmatter, including `transcript_source`, which shows which tier
worked and how far the text can be trusted.

Run with `uv run transcript.py ...`: the dependencies above are installed automatically.

The Groq key is read (in this order) from:
    the GROQ_API_KEY environment variable
    ~/.config/agent-memory/.env
    a .env next to this script

Exit codes:
    0 success
    1 runtime error
    2 missing dependencies
    4 all three tiers failed
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_MISSING_DEPS = 2
EXIT_NO_TRANSCRIPT = 4

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODEL = "whisper-large-v3"
# The free tier accepts files up to 25 MB. 16 kHz mono 32 kbit/s is about 14 MB per hour,
# so cut into 20-minute chunks: about 4.8 MB each, with a wide margin.
CHUNK_SECONDS = 1200


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# -- Finding binaries ---------------------------------------------------------------
def _find_binary(name: str) -> str | None:
    """Look for a binary on PATH, then where winget and choco put it.

    A freshly winget-installed ffmpeg does not appear on the PATH of already running
    processes, so which() alone is not enough.
    """
    found = shutil.which(name)
    if found:
        return found
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / f"{name}.exe",
        Path("C:/ProgramData/chocolatey/bin") / f"{name}.exe",
    ]
    packages = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if packages.is_dir():
        candidates.extend(packages.glob(f"*FFmpeg*/**/bin/{name}.exe"))
    for path in candidates:
        if path and Path(path).is_file():
            return str(path)
    # Last resort: the binary shipped in the imageio-ffmpeg package (under its own name;
    # it has no ffprobe, which is not needed).
    if name == "ffmpeg":
        try:
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
            if Path(exe).is_file():
                return exe
        except Exception:  # noqa: BLE001
            pass
    return None


def _yt_dlp_cmd() -> list[str] | None:
    """yt-dlp as a binary or as a Python module, whichever exists."""
    try:
        import yt_dlp  # noqa: F401
        return [sys.executable, "-m", "yt_dlp"]
    except ImportError:
        exe = shutil.which("yt-dlp")
        return [exe] if exe else None


def _run(cmd: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def _cookie_args(cookies_browser: str | None, cookies_file: str | None) -> list[str]:
    if cookies_file:
        return ["--cookies", cookies_file]
    if cookies_browser:
        return ["--cookies-from-browser", cookies_browser]
    return []


# -- Groq key ------------------------------------------------------------------------
def read_groq_key() -> str | None:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if key:
        return key
    for env_file in (Path.home() / ".config" / "agent-memory" / ".env",
                     Path(__file__).resolve().parent / ".env"):
        if not env_file.is_file():
            continue
        try:
            for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line.startswith("GROQ_API_KEY"):
                    value = line.partition("=")[2].strip().strip('"').strip("'")
                    if value:
                        return value
        except OSError:
            continue
    return None


# -- Common ----------------------------------------------------------------------------
def extract_video_id(url_or_id: str) -> str | None:
    """The YouTube video ID, or None: then it is not YouTube and tier 1 drops out."""
    patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/live/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})",
        r"^([a-zA-Z0-9_-]{11})$",
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    return None


def format_timestamp(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def format_duration(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m}m {s}s" if h else f"{m}m {s}s"


def yaml_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def safe_filename(text: str) -> str:
    """Video title to file name. Non-Latin letters stay; forbidden characters become ' - '."""
    text = re.sub(r'[<>:"/\\|?*]+', " - ", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text[:120] or "Untitled"


# -- Tier 1: youtube-transcript-api -------------------------------------------------------
def tier1_transcript_api(video_id: str, lang: str) -> tuple[list[dict], str] | None:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        log("  [1] youtube-transcript-api is not installed: skipping")
        return None
    try:
        listing = YouTubeTranscriptApi().list(video_id)
        try:
            found = listing.find_transcript([lang, "en"])
        except Exception:  # noqa: BLE001
            found = listing.find_generated_transcript([lang, "en"])
        fetched = found.fetch()
    except Exception as e:  # noqa: BLE001
        log(f"  [1] failed: {type(e).__name__}: {str(e).splitlines()[0][:160]}")
        return None
    segments = [{"start": float(s.start), "text": s.text.strip()} for s in fetched if s.text.strip()]
    if not segments:
        return None
    kind = "auto" if found.is_generated else "manual"
    return segments, f"youtube-transcript-api ({found.language_code}, {kind})"


# -- Tier 2: captions through yt-dlp ------------------------------------------------------
def parse_vtt(path: Path) -> list[dict]:
    """Parse VTT into segments, dropping the rolling repeats of auto-captions.

    In YouTube auto-captions every block repeats the previous line and appends a new one.
    Without cleaning, the text triples.
    """
    raw = path.read_text(encoding="utf-8", errors="ignore")
    segments: list[dict] = []
    last_line = None
    time_re = re.compile(r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->")
    current_start = None
    for block in re.split(r"\n\s*\n", raw):
        block = block.strip()
        if not block or block.startswith(("WEBVTT", "NOTE", "STYLE", "Kind:", "Language:")):
            continue
        text_lines = []
        for line in block.splitlines():
            match = time_re.search(line)
            if match:
                h, m, s, ms = map(int, match.groups())
                current_start = h * 3600 + m * 60 + s + ms / 1000
                continue
            if re.fullmatch(r"\d+", line.strip()):  # SRT sequence number
                continue
            text_lines.append(line)
        if current_start is None:
            continue
        for line in text_lines:
            line = re.sub(r"<[^>]+>", "", line)
            line = re.sub(r"&nbsp;?", " ", line)
            line = (line.replace("&amp;", "&").replace("&lt;", "<")
                        .replace("&gt;", ">").replace("&#39;", "'").replace("&quot;", '"'))
            line = re.sub(r"\s+", " ", line).strip()
            if not line or line == last_line:
                continue
            segments.append({"start": current_start, "text": line})
            last_line = line
    return segments


def tier2_ytdlp_subs(url: str, lang: str, cookies: list[str], workdir: Path) -> tuple[list[dict], str] | None:
    cmd = _yt_dlp_cmd()
    if not cmd:
        log("  [2] yt-dlp not found: skipping")
        return None
    args = cmd + ["--skip-download", "--write-subs", "--write-auto-subs",
                  "--sub-langs", f"{lang}.*,{lang},en.*,en", "--sub-format", "vtt/srt/best",
                  "--no-warnings", "--no-playlist", "-o", str(workdir / "%(id)s.%(ext)s"), url] + cookies
    try:
        result = _run(args)
    except subprocess.TimeoutExpired:
        log("  [2] yt-dlp timed out")
        return None
    subtitle_files = sorted(list(workdir.glob("*.vtt")) + list(workdir.glob("*.srt")))
    if not subtitle_files:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        log(f"  [2] no captions: {detail[-1][:180] if detail else 'yt-dlp returned nothing'}")
        return None

    def rank(p: Path) -> tuple[int, str]:  # the requested language, then English, then any
        name = p.name.lower()
        return (0 if f".{lang}" in name else 1 if ".en" in name else 2, name)

    chosen = sorted(subtitle_files, key=rank)[0]
    segments = parse_vtt(chosen)
    if not segments:
        log("  [2] the caption file is empty after parsing")
        return None
    lang_tag = re.sub(r"^.*?\.([a-zA-Z-]+)\.(vtt|srt)$", r"\1", chosen.name)
    return segments, f"yt-dlp captions ({lang_tag})"


# -- Tier 3: audio + Groq Whisper -----------------------------------------------------------
def download_audio(url: str, cookies: list[str], workdir: Path) -> Path | None:
    cmd = _yt_dlp_cmd()
    if not cmd:
        log("  [3] yt-dlp not found: skipping")
        return None
    # Candidates are tried ONE AT A TIME, each in its own yt-dlp call: YouTube often answers
    # 403 Forbidden to selector expressions (`bestaudio`, chains with `/`), while the same
    # format requested by its single number downloads fine. Each new call also does a fresh
    # extract, which doubles as a retry when the 403 came from throttling.
    # 139 is m4a at 49 kbit/s: plenty for Whisper, which squeezes to 16 kHz mono anyway.
    # The last two candidates are for sites without YouTube's format numbers.
    candidates = ["139", "140", "bestaudio[ext=m4a]", "bestaudio/best"]
    last_error = "no output"
    for attempt, fmt in enumerate(candidates, 1):
        args = cmd + ["-f", fmt, "--no-playlist", "--no-warnings",
                      "-o", str(workdir / "audio.%(ext)s"), url] + cookies
        try:
            result = _run(args, timeout=1800)
        except subprocess.TimeoutExpired:
            log("  [3] audio download timed out")
            return None
        files = [p for p in workdir.glob("audio.*") if p.suffix.lower() != ".part"]
        if files:
            return files[0]
        detail = (result.stderr or "").strip().splitlines()
        last_error = detail[-1][:180] if detail else "no output"
        log(f"  [3] format {fmt} failed ({last_error}): trying the next one")
        if attempt < len(candidates):
            time.sleep(3)
    log(f"  [3] the audio did not download: {last_error}")
    return None


def prepare_chunks(audio: Path, ffmpeg: str, workdir: Path) -> list[Path]:
    """16 kHz mono 32 kbit/s, cut into CHUNK_SECONDS pieces, as Groq recommends."""
    compact = workdir / "compact.mp3"
    result = _run([ffmpeg, "-y", "-i", str(audio), "-vn", "-ac", "1", "-ar", "16000",
                   "-c:a", "libmp3lame", "-b:a", "32k", str(compact)], timeout=1800)
    if not compact.is_file():
        log(f"  [3] ffmpeg could not re-encode: {(result.stderr or '')[-300:]}")
        return []
    chunk_dir = workdir / "chunks"
    chunk_dir.mkdir(exist_ok=True)
    _run([ffmpeg, "-y", "-i", str(compact), "-f", "segment", "-segment_time", str(CHUNK_SECONDS),
          "-c", "copy", str(chunk_dir / "chunk_%03d.mp3")], timeout=1800)
    return sorted(chunk_dir.glob("chunk_*.mp3")) or [compact]


def groq_transcribe_chunk(path: Path, key: str, lang: str) -> list[dict] | None:
    import requests

    for attempt in range(3):
        try:
            with path.open("rb") as fh:
                response = requests.post(
                    GROQ_URL,
                    headers={"Authorization": f"Bearer {key}"},
                    files={"file": (path.name, fh, "audio/mpeg")},
                    data={"model": GROQ_MODEL, "response_format": "verbose_json",
                          "timestamp_granularities[]": "segment", "language": lang, "temperature": "0"},
                    timeout=600,
                )
        except Exception as e:  # noqa: BLE001
            log(f"  [3] network error ({type(e).__name__}), attempt {attempt + 1}/3")
            time.sleep(5 * (attempt + 1))
            continue
        if response.status_code == 429:
            wait = int(float(response.headers.get("retry-after", 30))) + 2
            if wait > 300:
                log(f"  [3] hit Groq's daily limit, would wait {wait} s: stopping")
                return None
            log(f"  [3] rate limited, waiting {wait} s")
            time.sleep(wait)
            continue
        if response.status_code == 401:
            log("  [3] Groq rejected the key (401). Check GROQ_API_KEY")
            return None
        if not response.ok:
            log(f"  [3] Groq returned {response.status_code}: {response.text[:200]}")
            time.sleep(5)
            continue
        payload = response.json()
        segments = payload.get("segments")
        if segments:
            return [{"start": float(s.get("start", 0)), "text": (s.get("text") or "").strip()}
                    for s in segments if (s.get("text") or "").strip()]
        text = (payload.get("text") or "").strip()
        return [{"start": 0.0, "text": text}] if text else []
    return None


def tier3_groq(url: str, lang: str, cookies: list[str], workdir: Path) -> tuple[list[dict], str] | None:
    key = read_groq_key()
    if not key:
        log("  [3] no GROQ_API_KEY: skipping")
        return None
    ffmpeg = _find_binary("ffmpeg")
    if not ffmpeg:
        log("  [3] ffmpeg not found: skipping")
        return None
    log("  [3] downloading audio...")
    audio = download_audio(url, cookies, workdir)
    if not audio:
        return None
    log("  [3] preparing audio for Whisper...")
    chunks = prepare_chunks(audio, ffmpeg, workdir)
    if not chunks:
        return None
    segments: list[dict] = []
    failed = 0
    for index, chunk in enumerate(chunks):
        log(f"  [3] transcribing chunk {index + 1}/{len(chunks)}...")
        part = groq_transcribe_chunk(chunk, key, lang)
        if part is None:
            failed += 1
            continue
        offset = index * CHUNK_SECONDS
        segments.extend({"start": s["start"] + offset, "text": s["text"]} for s in part)
    if not segments:
        return None
    label = f"Groq {GROQ_MODEL}"
    if failed:
        label += f" - PARTIAL, {failed} of {len(chunks)} chunks not transcribed"
    return segments, label


# -- Metadata --------------------------------------------------------------------------------
def fetch_metadata(url: str, cookies: list[str]) -> dict:
    empty = {"title": "", "channel": "", "description": "", "duration": 0, "upload_date": "", "chapters": []}
    cmd = _yt_dlp_cmd()
    if not cmd:
        return empty
    try:
        result = _run(cmd + ["--skip-download", "--dump-json", "--no-warnings", "--no-playlist", url] + cookies,
                      timeout=120)
        if result.returncode != 0:
            return empty
        data = json.loads(result.stdout.splitlines()[0])
    except Exception:  # noqa: BLE001
        return empty
    raw_date = data.get("upload_date") or ""
    return {
        "title": data.get("title") or "",
        "channel": data.get("channel") or data.get("uploader") or "",
        "description": data.get("description") or "",
        "duration": int(data.get("duration") or 0),
        "upload_date": f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}" if len(raw_date) == 8 else raw_date,
        "chapters": data.get("chapters") or [],
    }


# -- Markdown ----------------------------------------------------------------------------------
def build_markdown(url: str, video_id: str, meta: dict, segments: list[dict],
                   source: str, lang: str, timestamps: bool) -> str:
    title = meta["title"] or "Untitled"
    channel = meta["channel"] or "Unknown"
    if timestamps:
        body = "\n".join(f"[{format_timestamp(s['start'])}] {s['text']}" for s in segments)
    else:
        body = "\n".join(s["text"] for s in segments)
    extra_fm, rows = "", ""
    if meta["duration"]:
        extra_fm += f'\nduration: "{format_duration(meta["duration"])}"'
        rows += f"\n| Duration | {format_duration(meta['duration'])} |"
    if meta["upload_date"]:
        extra_fm += f'\nupload_date: "{meta["upload_date"]}"'
        rows += f"\n| Published | {meta['upload_date']} |"
    description_block = ""
    if meta["description"] or meta["chapters"]:
        parts = ["\n## Video description\n"]
        if meta["description"]:
            parts.append(re.sub(r"^-{3,}$", "\\---", meta["description"], flags=re.MULTILINE))
        if meta["chapters"]:
            parts.append("\n### Chapters\n")
            parts += [f"- `{format_timestamp(c.get('start_time', 0))}` {c.get('title', '')}" for c in meta["chapters"]]
        description_block = "\n".join(parts)
    return f"""---
title: "{yaml_escape(title)}"
channel: "{yaml_escape(channel)}"
url: "{url}"
video_id: "{video_id or ''}"
fetched: "{date.today().isoformat()}"
language: "{lang}"
transcript_source: "{yaml_escape(source)}"{extra_fm}
tags:
  - yt-transcript
---

# {title}

## Video data

| Field | Value |
|------|----------|
| URL | {url} |
| Channel | {channel.replace('|', chr(92) + '|')} |{rows}
| Fetched | {date.today().isoformat()} |
| Text source | {source.replace('|', chr(92) + '|')} |
{description_block}

## Transcript

{body}
"""


# -- Environment check ---------------------------------------------------------------------------
def print_check() -> int:
    """Which tiers are ready. It does not call Groq, so it cannot tell a dead key from a
    live one: a rejected key shows up only on a real tier-3 run (401)."""
    log("Text extraction tiers:")
    try:
        import youtube_transcript_api  # noqa: F401
        log("  [1] youtube-transcript-api: ready")
    except ImportError:
        log("  [1] youtube-transcript-api: MISSING (run the script with `uv run`)")
    log("  [2] yt-dlp: ready" if _yt_dlp_cmd() else "  [2] yt-dlp: MISSING (run the script with `uv run`)")
    ffmpeg = _find_binary("ffmpeg")
    key = read_groq_key()
    if ffmpeg and key:
        log("  [3] Groq Whisper: ready (key present, not validated)")
    else:
        missing = []
        if not ffmpeg:
            missing.append("ffmpeg")
        if not key:
            missing.append("GROQ_API_KEY (free key at console.groq.com/keys)")
        log(f"  [3] Groq Whisper: MISSING {', '.join(missing)}")
    return EXIT_SUCCESS


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(
        description="Get the text out of a video: captions, then yt-dlp, then Groq Whisper",
        epilog="Exit codes: 0 success, 1 error, 2 missing dependencies, 4 no text extracted",
    )
    parser.add_argument("video", nargs="?", help="video URL or YouTube ID")
    parser.add_argument("--lang", "-l", default="en", help="language code (default en)")
    parser.add_argument("--output", "-o", help="where to save the .md")
    parser.add_argument("--out-dir", help="folder to save into; the file is named after the video title")
    parser.add_argument("--timestamps", "-t", action="store_true", help="time codes in the text")
    parser.add_argument("--stdout", action="store_true", help="print to stdout, do not save")
    parser.add_argument("--max-tier", type=int, default=3, choices=[1, 2, 3], help="highest tier to try (default 3)")
    parser.add_argument("--min-tier", type=int, default=1, choices=[1, 2, 3], help="tier to start from")
    parser.add_argument("--cookies-from-browser", dest="cookies_browser", default=None,
                        help="chrome | firefox | edge: use the browser's cookies against blocks")
    parser.add_argument("--cookies", dest="cookies_file", default=None,
                        help="a Netscape cookies.txt file exported from the browser")
    parser.add_argument("--check", action="store_true", help="check which tiers are ready, then exit")
    args = parser.parse_args()

    if args.check:
        sys.exit(print_check())
    if not args.video:
        parser.error("a video URL is required")
    try:
        import requests  # noqa: F401
    except ImportError:
        log("Missing package requests: run the script with `uv run`")
        sys.exit(EXIT_MISSING_DEPS)

    url = args.video
    video_id = extract_video_id(url)
    if video_id and not url.startswith("http"):
        url = f"https://www.youtube.com/watch?v={video_id}"
    cookies = _cookie_args(args.cookies_browser, args.cookies_file)
    log(f"Video: {url}")
    workdir = Path(tempfile.mkdtemp(prefix="transcript_"))
    result = None
    try:
        ladder = []
        if video_id:
            ladder.append((1, "YouTube's ready captions", lambda: tier1_transcript_api(video_id, args.lang)))
        else:
            log("  [1] not YouTube: tier skipped")
        ladder.append((2, "captions through yt-dlp", lambda: tier2_ytdlp_subs(url, args.lang, cookies, workdir)))
        ladder.append((3, "audio to Groq Whisper", lambda: tier3_groq(url, args.lang, cookies, workdir)))
        for number, name, run_tier in ladder:
            if number < args.min_tier or number > args.max_tier:
                continue
            log(f"Tier {number}: {name}")
            try:
                result = run_tier()
            except Exception as e:  # noqa: BLE001
                log(f"  [{number}] crashed: {type(e).__name__}: {str(e)[:200]}")
                result = None
            if result:
                log(f"  [{number}] worked: {len(result[0])} segments")
                break
        if not result:
            log("\nNo tier produced text.")
            log("Try: --min-tier 3, --cookies <file>, another --lang, or --check")
            sys.exit(EXIT_NO_TRANSCRIPT)

        segments, source = result
        meta = fetch_metadata(url, cookies)
        content = build_markdown(url, video_id or "", meta, segments, source, args.lang, args.timestamps)
        if args.stdout:
            print(content)
            sys.exit(EXIT_SUCCESS)
        if args.output:
            out_path = Path(args.output)
        else:
            base = Path(args.out_dir).expanduser() if args.out_dir else Path.cwd()
            out_path = base / f"{safe_filename(meta['title'] or video_id or 'video')}.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        log("")
        log(f"Saved:  {out_path}")
        log(f"Source: {source}")
        if meta["duration"]:
            log(f"Length: {format_duration(meta['duration'])}")
        sys.exit(EXIT_SUCCESS)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
