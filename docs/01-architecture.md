# Why the keyframes come out of a video model

## The finding

The contest rule is one sentence:

> Core generation has to run on MiniMax models served through GMI Cloud.

Before writing any code we pulled the GMI Cloud model catalogue and filtered it. Of 319
models, the MiniMax family on GMI covers **video** (`MiniMax-H3`) and **audio**
(`minimax-music-3.0`, Speech). There is **no MiniMax text-to-image or image-to-image model**
on the platform.

That is not a small gap. Every image-conditioned video pipeline has the same spine:

```
text ──► image model ──► still ──► video model ──► shot
```

The still is where a human reviews composition, casting, costume and colour *before* paying
for motion. Remove the image model and you either give that review up, or you find the still
somewhere else.

## What we did instead

We took it out of the video model.

```
kf_prompt ──► H3 text-to-video ──► 4 s clip ──► frame 0 ──► keyframe (2560×1440)
```

A 4-second generation at `2K` costs $0.52. Frame 0 of it is a still image at full delivery
resolution. Thirty-six of them cost **$18.72** — that is the entire price of getting a
reviewable still into a pipeline that has no image model.

The keyframe is then reviewed and **locked**. The shot that ships is a second H3 call:

```
clip_prompt + first_frame_image=<locked keyframe> ──► H3 image-to-video ──► shot
```

## Does the shot actually start on the approved frame?

This architecture is only honest if H3 respects the first frame. It is measurable, so we
measure it rather than assume it: for every shot, extract frame 0 of the delivered clip and
compute the mean absolute pixel difference against the locked keyframe.

Across 36 shots the **median is 0.97%**, and the gate that would reject a clip is 8%. The
still the director approved is the still the shot opens on.

This check runs inside the generation script, not as a report afterwards — a clip that fails
it is not written to the output path at all.

## What this buys, and what it costs

**Buys:** a real human review gate on 36 stills before spending $27.69 on motion; a stable
identity anchor for the two recurring characters across a film with no character-reference
model available; a locked 16:9 frame (with `first_frame_image` set, H3 ignores `ratio` — the
aspect comes from the image).

**Costs:** 40% on top of the video bill, and one extra generation round-trip per shot.

For a pipeline whose alternative was "no still at all", that is a good trade.
