---
name: video-transcribe-and-caption
description: Transcribe a video that has no captions (X/Twitter, YouTube, any yt-dlp URL or local file) with local Whisper, write an SRT, and burn captions into a new MP4. Use when asked to 'get the transcript', 'extract what they say', 'add subtitles', 'caption this video', or 'this video has no captions'.
---

# Skill: video-transcribe-and-caption

## Purpose

Turn speech in a video into text without any cloud service: download with
yt-dlp, transcribe locally with faster-whisper, emit an SRT, and optionally
burn the captions in with ffmpeg so they show in every player.

## Steps

### 1. Check tools

```bash
which yt-dlp ffmpeg uv; nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null
```

`uvx yt-dlp` and `uv run --with faster-whisper` avoid installing anything.
Only the ffmpeg `subtitles` filter needs a real ffmpeg build with libass
(`ffmpeg -filters | grep subtitles`); the bundled binary from
`imageio-ffmpeg` may lack it.

### 2. Download

```bash
uvx yt-dlp -f "best[ext=mp4]" -o "video.%(ext)s" --no-playlist "<url>"
uvx yt-dlp --skip-download -j "<url>" | jq '{title, uploader, upload_date, description}'
```

### 3. Transcribe to SRT

```python
# srt.py — run with: uv run --with faster-whisper python srt.py
from faster_whisper import WhisperModel

def ts(t):
    h, r = divmod(t, 3600); m, s = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(s % 1 * 1000):03d}"

model = WhisperModel("large-v3", device="cpu", compute_type="int8")  # device="cuda" if a GPU exists
segments, info = model.transcribe("video.mp4", vad_filter=True, beam_size=5)
with open("video.srt", "w") as f:
    for i, s in enumerate(segments, 1):
        f.write(f"{i}\n{ts(s.start)} --> {ts(s.end)}\n{s.text.strip()}\n\n")
```

Model choice:

- `small` is fast but garbles multi-voice audio, jokes and jargon. Fine for a
  first look, not for captions.
- `large-v3` is the one to ship. It is a ~3 GB first download into
  `~/.cache/huggingface/hub/`; on a slow link that alone can take 30+
  minutes. Say so and ask before starting it; `medium` is half the size.
- Run long transcriptions in the background and report progress honestly:
  check whether the `.incomplete` blob in the HF cache is still growing
  (downloading) or the process is at high CPU (transcribing).

### 4. Fix misheard lines

Whisper still mishears names and domain words. Re-transcribe only the bad
stretch with vocabulary hints instead of rerunning the whole file:

```bash
ffmpeg -loglevel error -y -ss 53 -to 64 -i video.mp4 -vn -ac 1 -ar 16000 clip.wav
```

```python
segments, _ = model.transcribe("clip.wav", beam_size=5,
    initial_prompt="Short list of expected words: product names, jargon, emoji names.")
```

Then edit those SRT entries by hand (keep the timestamps). Pulling a frame
(`ffmpeg -ss 58 -i video.mp4 -frames:v 1 f.jpg`) helps when on-screen text
disambiguates the audio. Tell the user which lines are still low-confidence
rather than presenting a guess as fact.

### 5. Burn captions

```bash
ffmpeg -hide_banner -loglevel error -y -i video.mp4 \
  -vf "subtitles=video.srt:force_style='FontSize=20,Outline=1,MarginV=30'" \
  -c:v libx264 -preset fast -crf 20 -c:a copy video_cc.mp4
```

Keep the SRT next to the output so a single line can be fixed and re-rendered
in under a minute. For soft (toggleable) subtitles instead, mux with
`-c copy -c:s mov_text`.

## Deliverables

Original video, captioned video, `.srt`, and the plain transcript. Mention
the cached model size so the user can delete it.

## Common mistakes

- Shipping `small`-model output as captions.
- Starting a multi-GB model download without asking.
- Rerunning the full transcription to fix three lines.
- Using an ffmpeg without libass and getting "No such filter: subtitles".
