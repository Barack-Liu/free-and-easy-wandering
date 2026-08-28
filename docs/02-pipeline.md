# Pipeline

Ten steps. Six of them stop for human sign-off; the rest run unattended.

| # | Step | Model / tool | Human gate |
|---|---|---|---|
| 1 | Lyrics from the source essay | — | ✅ approve text |
| 2 | Three songs in three distinct styles, pick one | `minimax-music-3.0` | ✅ pick |
| 3 | Protagonist stills | `MiniMax-H3` (frame 0) | ✅ pick |
| 4 | 36-shot storyboard, art-direction gates | — | — |
| 5 | 36 keyframes | `MiniMax-H3` t2v → frame 0 | ✅ approve stills |
| 6 | Lyric timecodes | ASR + pinyin alignment | — |
| 7 | Lyric-anchored shot timing | — | — |
| 8 | 36 shots | `MiniMax-H3` i2v | — |
| 9 | 4-layer bilingual subtitles | libass | — |
| 10 | Assembly, credits, master | ffmpeg | ✅ approve cut, ✅ pick cover |

## Lyric timecodes

The music model returns audio with no word timings. To place 29 lyric lines we:

1. transcribe with two independent ASR passes (Whisper large-v3 and medium — a single pass
   agreeing with itself proves nothing);
2. convert both the transcript and the known-correct lyrics to pinyin and align
   monotonically. Character-level alignment on sung Chinese is unreliable; **pinyin-level
   alignment is not**, because the singer's vowels survive even when the characters are
   misheard;
3. take the line start times from the alignment.

Where the two passes disagree by more than a threshold, the higher-coverage pass wins and the
disagreement is logged rather than silently resolved.

## Shot timing

Shot durations are **not** distributed proportionally over the track. Each shot is mapped to
the lyric line it illustrates, and its boundary is the first sung syllable of the next
shot's line. Proportional distribution accumulated error until, by act three, the words were
up to three shots ahead of the picture.

Durations are then converted to **integer frames** and allocated by the largest-remainder
method so that the 36 shots sum to exactly `round(sung_region × 24)` frames. Rounding each
shot independently to the nearest second drifts +0.681 s over 36 cuts, which is enough to
break the "picture length = music length" self-check and to eat the contest's time margin.

## Subtitles

Four simultaneous layers, all bilingual:

| Layer | Position | Content |
|---|---|---|
| Lyrics | bottom centre | sung line, Chinese over English |
| Story note | top centre | what the lyric does *not* say — ancient units, proper names, what the argument is |
| Name card | under the character | who this is; positioned at the character's measured horizontal position |
| Scene card | top left | where this is |

Two rules that are easy to get wrong:

- The story note **never restates the lyric**. If a line needs no gloss, the layer is empty.
- The reading-speed limit applies to the **sum of all layers on screen**, not to each layer
  separately: ≤9 Chinese characters/s, ≤20 Latin characters/s. A layer that individually
  passes can still make the frame unreadable.

Name cards are clamped to their own shot's time window; an earlier version let the
reading-speed resolver extend a card past the cut, and the card appeared over the next
character.

## Assembly

The subtitle file is authored once at PlayRes 1920×1080. libass renders relatively, so the
same `.ass` burns identically at 2560×1440 and at 3840×2160 — the 4K master and the review
cut are typographically identical by construction, not by re-checking.

The 4K master is built by upscaling the **unsubtitled** picture and re-burning the subtitle
file at 4K — not by scaling up a picture that already has text baked in.

Intermediates are cached on a **content fingerprint of their inputs**, propagated down the
chain. A cache keyed on "does the file exist and is it readable" will happily reuse a
subtitle burn from before you edited the subtitles.
