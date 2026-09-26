# Step W in detail: modes of frames.py

Read this when SKILL.md step W said "look" and you are choosing the command. The script's
docstring is the reference for every flag; this file is about which one fits the task.
`<scripts>` is the scripts folder named in SKILL.md.

## Which mode

| Task | Flags (`uv run "<scripts>/frames.py" <URL> ...`) |
|---|---|
| "what is on screen at 12:30" | `--at 12:30` (a comma list works; downloads 2 s per moment) |
| frames where the speaker points at the screen | `--grep` with a regex, command below the table |
| a piece frame by frame, with speech | `--start 12:30 --end 13:10 --subs` |
| a long piece at a glance | `--start 10:00 --end 20:00 --sheet` (5x4 frames per sheet) |
| a clip, editing, cuts | `--start ... --end ... --scene` (a frame on every cut) |
| code, small text, slides | add `--width 1024` (720p source, about 4x the tokens) |
| just cut a piece for the user to watch | `--start 5:00 --end 5:20 --clip-only` (mp4 or webm with sound) |
| a local file | the path instead of the URL; a cut piece needs `--offset` (the script prints the command) |

The regex sits outside the table on purpose: inside a markdown cell `|` must be escaped as `\|`,
and a copied `\|` is a literal pipe in a Python regex, so the search would find nothing.

```bash
uv run "<scripts>/frames.py" <URL> --grep "slide|on screen|code|chart|table" --max-frames 8
```

All times are the original video's, in the flags and in frame names (`t_12-30.5.jpg`). Output
goes to a temp folder (`frames_*`, or `--out-dir`) with `index.md`: every frame path with its time
and, with `--subs`, what was said until the next frame. The downloaded piece stays in `_work/` and
can be rerun in another mode without downloading; `index.md` prints the exact command. A folder
that already holds an `index.md` is refused, so frames of two runs never mix.

## Aim first, then zoom in

On a long video: a sheet or `--grep` first, then `--start/--end` densely on the minute that
matters. Do not run a whole hour at 2 fps: the budget caps any run at 100 frames (30 s: 30
frames, 1 min: 40, 3 min: 60, 10 min: 80, more: 100), and over an hour they spread one per 36 s.

`--at` and `--grep` without `--start/--end` download two seconds around each moment, all in one
yt-dlp call, not the whole video. On a 69-minute video: 3 moments took 34 s, 6 moments 191 s.
Taking the frame straight from the stream URL with ffmpeg also works but cost 25-31 s per frame,
so the script does not do it.

## Choose `--grep` words by the video

Filler words ("you see", "this one", "look") are used figuratively all the time: on a one-hour
video they gave 30 hits, mostly frames of the speaker with no link to the phrase. Nouns for things
on screen ("slide", "code", "table", the tool's name) hit more precisely. `--grep` needs captions
(transcript tiers 1 and 2); there is no Whisper fallback for it.

## Duplicates are dropped by the maximum, not the mean

Near-identical frames are removed automatically (`--no-dedup` keeps them). The test is **the
largest change in any cell** of a 32x18 grey thumbnail (<= 6 of 255 is a duplicate), not the mean
change of a 16x16 one as in claude-video, where the idea came from. On dark motion graphics the
mean dropped 36 frames of 40 together with three different screens, because small text on a dark
background barely moves the mean; the maximum kept 22 with every screen in place, checked against
a sheet of all 40.

If a sheet shows a missing screen, rerun with `--no-dedup` and report it: the threshold then needs
a new case, not a silent workaround.

## Sound tracks

`--clip-only` downloads video plus audio. Videos with YouTube auto-dubbing have no plain `140`/`251`
audio format, only `140-0`, `140-1` and so on; the script asks for `ba`, which picks the track
marked "original (default)".
