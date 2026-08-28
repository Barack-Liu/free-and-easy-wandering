# Models and cost

Everything that generates picture or sound in this film ran on MiniMax models through GMI Cloud.

| Stage | Model | Calls | Cost |
|---|---|---|---|
| Music | `minimax-music-3.0` | 24 takes across 4 styles | included in the campaign's free tier |
| Keyframes | `MiniMax-H3` (t2v, 4 s, 2K) | 36 | **$18.72** |
| Shots | `MiniMax-H3` (i2v, 2K) | 36 | **$27.69** |
| | | **total video** | **$46.41** |

H3 is billed per second of generated video and is not part of the free tier; the music model is.

### Music takes by style

| Style prompt | Takes |
|---|---|
| `guofeng-rock` | 12 |
| `cyber-electronic` | 6 |
| `guofeng-rap` | 4 |
| `epic-orchestral` | 2 |

Four styles were written as genuinely different arrangements — not parameter tweaks of one
idea. Three finalists were presented for selection and the guofeng hip-hop arrangement was
chosen. The rap flow was itself a response to a constraint: `minimax-music-3.0` exposes no
duration control anywhere, and a dense syllabic delivery is the one lever on the *lyric* side
that shortens the sung region.

### Disclosure: the delivered track is edited

The selected take is **204.87 s**. The delivered master is **170.944 s**.

The difference is entirely **purely instrumental** material — the introduction, the three
interludes and the outro were shortened, beat-quantised and cross-faded. No sung material was
removed; this was verified by aligning ASR output against the written lyrics and confirming
full coverage. Instrumental sections were only ever **shortened** — nothing was lengthened,
looped or inserted, and the model output was not time-stretched.

## Supporting tools (not generation)

- `ffmpeg` / `ffprobe` — cutting, concatenation, subtitle burn-in, upscale, mux
- `libass` — subtitle rendering
- Whisper (large-v3, medium) — lyric timecode alignment only; it never touches the delivered audio
- `pypinyin` — pinyin conversion for the alignment

## Measured output specs

| | |
|---|---|
| H3 `resolution: "2K"` returns | 2560x1440 / 24fps (H3 '2K') |
| Delivered master | 3840x2160 / 24fps / 175.000s |
| Music track | 170.944 s, played to the end, never truncated |
| Picture (sung region) | 158.78 s; the instrumental outro runs under the credits |
| Keyframe → clip frame-0 difference | median **0.97%** (reject gate 8%) |

A request for `duration=N` returns about N + 0.46 s. All cutting is done against the
ffprobe-measured duration, never the requested one.
