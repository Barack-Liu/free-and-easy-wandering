# 逍遥游 / *Free and Easy Wandering*

**Cyber Guofeng Mythos, No. 1** — a 2 minute 55 second music video generated end-to-end
on MiniMax models served through GMI Cloud.

Submitted to **The MiniMaxathon**, track **Multimodality**.

▶ **Watch it: https://youtu.be/bRb80qnxhEk**

[![cover](assets/cover.jpg)](https://youtu.be/bRb80qnxhEk)

| | |
|---|---|
| Master | 3840×2160 · 24 fps · **175.000 s** |
| Shots | 36 |
| Music | `minimax-music-3.0` — one track, 170.944 s, lyrics written for this film |
| Video | `MiniMax-H3` — 36 keyframes + 36 shots, 2K native (2560×1440) |
| Source text | Zhuangzi, *Xiaoyaoyou* (莊子·逍遙遊), ~4th century BCE, public domain |
| Subtitles | 4 layers, bilingual Chinese/English, burned in |

---

## What it is

*Xiaoyaoyou* is the opening essay of the *Zhuangzi* — the one with the giant fish Kun that
becomes the bird Peng, the cicada that laughs at it, and the argument that freedom means
depending on nothing. It is 2,400 years old and it has never had a music video.

The lyrics are a modern-Chinese narrative retelling: 449 characters, four acts, every number
and name traceable to a line in the original ("three thousand li of waves", "ninety thousand
li", "five hundred years for one spring"). The refrain is the essay's own thesis sentence —
至人无己，神人无功，圣人无名 / *no self, no merit, no name*.

The art direction is one deliberate collision: **cyberpunk** light on **Chinese classical**
form at **epic-mythic** scale. Concretely, two colours carry it — cyan for the light of
machines and data, vermilion for the fire of flesh and blood — which happen to be both a
cyberpunk duotone and the palette of bronze and lacquer.

## The interesting constraint

The contest requires core generation to run on MiniMax models served through GMI Cloud.
A survey of the GMI catalogue (319 models) turned up something that changes the architecture:

> **MiniMax has video and audio models on GMI Cloud, but no image model.**

Every image-driven video pipeline starts by generating a still — a keyframe — and animating
it. That first step was simply unavailable. So:

**Keyframes are frame 0 of a 4-second H3 text-to-video generation.**

```
kf_prompt ──► H3 t2v (duration=4, 2K, 16:9) ──► frame 0 ──► kf_S##.png
                                                              │
                                             clip_prompt ─────┤
                                                              ▼
                                         H3 i2v (first_frame_image=kf) ──► clip_S##.mp4
```

The keyframe is generated, reviewed and locked as a still. Then it becomes
`first_frame_image` for the shot that actually ships. Cost of the extra pass: **$18.72**
across 36 shots — the price of having a reviewable still at all.

That this works at all rests on H3 honouring its first frame. Measured across all 36 shots,
the mean absolute pixel difference between the locked keyframe and frame 0 of the delivered
clip has a **median of 0.97%** (gate: 8%). The still you approve is the still the shot opens on.

## Other things that fell out of the constraints

**The music decides the length.** `minimax-music-3.0` has no duration parameter — not in the
API and not in the web playground. The returned track is 170.944 s. Rather than cut the music
to fit the picture, the picture covers the **sung** region (158.792 s) and the 12.164 s
instrumental outro plays under the credits card. Total 175.000 s, inside the contest's
180-second ceiling with 5.00 s to spare. Nothing is truncated.

**Each shot is anchored to its lyric line.** Shot durations are not distributed
proportionally — every shot is pinned to the line it illustrates, and its boundary is the
next shot's first sung syllable. Distributing proportionally had the picture running up to
three shots behind the words by the third act.

**Frame-exact assembly.** Per-shot durations are allocated in the *integer frame* domain by
largest remainder, so 36 shots sum to exactly the target frame count. Rounding each shot to
the nearest second independently drifted +0.681 s across the film.

**Reading speed is a hard gate.** Four subtitle layers can be on screen at once (lyrics
CN/EN, story note, scene card, name card). The gate is applied to the *sum of all layers*,
not per layer: ≤9 Chinese characters/s and ≤20 Latin characters/s.

## Repository layout

```
prompts/
  lyrics.md            449 characters, bilingual, with per-act rhyme category
  music_payload.json   the exact minimax-music-3.0 request that produced the track
  keyframes_36.json    36 H3 text-to-video payloads (keyframe pass)
  clips_36.json        36 H3 image-to-video payloads (shot pass)
src/
  xyy_h3.py            H3 client: submit / poll / upload / frame-extract
  xyy_t1_2_song.py     music generation
  xyy_t3_2_keyframes.py  keyframe pass
  xyy_t4_1_clips.py      shot pass, with the frame-0 identity gate
  xyy_t3_1_beatmap.py    lyric-anchored shot timing
  xyy_t4_2_build_ass.py  4-layer bilingual subtitles + reading-speed gate
  xyy_t5_1_assemble.py   frame-exact assembly, subtitle burn, master output
docs/
  01-architecture.md   why keyframes come out of a video model
  02-pipeline.md       every step, in order
  03-models-and-cost.md what ran where, and what it cost
assets/
  cover.jpg            cover frame (shot 27)
  keyframes_36.jpg     all 36 keyframes
```

## Running it

```bash
export GMI_API_KEY=...        # GMI Cloud API key
export XYY_ROOT=/path/to/project
python3 src/xyy_t1_2_song.py    --gen
python3 src/xyy_t3_2_keyframes.py
python3 src/xyy_t4_1_clips.py
python3 src/xyy_t4_2_build_ass.py
python3 src/xyy_t5_1_assemble.py --master4k --locked
```

These are the scripts that made the film. Three mechanical changes were made for
publication and nothing else: local absolute paths became environment variables, the private
key ledger became `src/auth.py`, and comments referencing unrelated in-progress projects were
redacted. **No logic was rewritten** — a rewritten script is a script that never ran.

The comments are dense and mostly in Chinese, because they are a working log: each one
records a specific failure and the rule that came out of it. They are left in on purpose.

## Hard facts about H3 that cost us time

Recorded here because they are not obvious from the parameter list:

- `first_frame_image` / `last_frame_image` and `reference_images` **cannot be sent in the
  same request**. Frame-based and reference-based conditioning are mutually exclusive.
- With `first_frame_image` set, `ratio` is ignored — the aspect follows the input image. The
  16:9 frame has to be locked by the keyframe itself.
- `duration` (integer, 4–15 s) and `resolution` (`768P` / `2K`) are both required.
  `2K` returns 2560×1440 at 24 fps.
- A request for `duration=N` returns roughly **N + 0.46 s** of video. Cut against the
  measured duration, not the requested one.
- Images must go through `upload-url` → `PUT` (with `Content-Type: image/png`, exactly) →
  `public_url`. Raw base64 is rejected.
- The gateway's POST can time out **after** the job has been accepted. A timeout is not a
  failure; recover the job by matching the payload fingerprint against the request list
  instead of resubmitting.

## Credits

Written, storyboarded and produced by **Barack Liu** · August 2026
Compute platform: **GMI Cloud**
Generative AI: `minimax-music-3.0` (music), `MiniMax-H3` (video), `ffmpeg` (edit/subtitles/master)
Adapted from Zhuangzi, *Free and Easy Wandering* (public domain)

Original work created during the campaign window.
