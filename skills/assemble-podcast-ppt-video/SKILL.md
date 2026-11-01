---
name: assemble-podcast-ppt-video
description: Use when assembling a checked Chinese narrated presentation video from PPTX/PDF/SVG, audio, and script, especially when narration-first semantic slide selection, out-of-order page mapping, word-level subtitles, progressive object reveals, HyperFrames motion, or a static FFmpeg fallback are required.
---

# PPT Audio Video Assembly

Create the finished video without asking the user to inspect intermediate
files. The approved script is the text authority, word-level ASR is the timing
authority, and semantic slide/group anchors decide what is visible. The final
video owns motion acceptance; native PPTX animation is optional additional
value.

## Non-Negotiable Priority

Optimize in this order:

1. the visible page or object must match the meaning being spoken now;
2. the visual must appear at the right spoken cue and remain readable;
3. preserve the original PPT page order only when the first two requirements
   remain equally well satisfied.

PPT page order is a soft preference, not a timeline constraint. Search the
whole deck for the best semantic match for each narration block. Skip pages the
audio does not meaningfully cover, move a later page earlier, return to an
earlier page, or reuse a page when that is what the narration requires. Never
insert a page merely to display every slide. When several pages are equally
valid for the same speech, prefer the original order and avoid unnecessary
jumps.

## Select One Render Route

| Observable requirement | Route |
|---|---|
| Only whole-page changes are needed; no object must wait for its spoken cue | **Static** — rendered slide frames + FFmpeg |
| Any request such as “讲到这一部分时再出现”, progressive reveal, timed emphasis, or object-level synchronization | **Dynamic** — semantic SVG groups + resolved PPT Master motion plan + HyperFrames |

A dynamic request may not silently fall back to static frames or generic page
crossfades. Read [references/dynamic-video.md](references/dynamic-video.md) and
follow it before creating or rendering the composition.

## Required Inputs

Work from one project/delivery directory. Prefer:

- final `.pptx`;
- matching final `.pdf`, exported from that PPTX;
- audio (`.mp3`, `.m4a`, or `.wav`);
- approved podcast script (`.md` or `.txt`);
- for Dynamic: the complete PPT Master project containing `svg_output/`,
  `animations.json`, the final conversion trace, and
  `validation/video_motion_plan.json`.

The PDF is the preferred static-frame source. The PPTX validates page count,
version, aspect ratio, fonts, notes, and optional native animation. If PDF and
PPTX page counts differ, identify the final PPTX and regenerate derived assets.
Never overwrite source PPTX, PDF, audio, script, or an accepted MP4.

## Production Gates

Complete each gate before the next. Do not transfer routine inspection to the
user.

### 1. Preflight

- Record audio duration, slide/page counts, canvas, available fonts, and exact
  source versions.
- Confirm PDF and SVG/PPTX assets belong to the same final deck.
- Static: render numbered slides at 1920×1080 or higher without distortion.
- Dynamic: validate `animations.json`, the portable motion handoff, and every
  referenced direct-root `<g id>` before HyperFrames work.
- Inspect the cover and representative dense/diagram pages for font fidelity.

Use PowerPoint/WPS export or a matching PowerPoint-exported PDF for final static
frames. Do not use LibreOffice unless the target application is unavailable and
a visual comparison passes.

### 2. Find the Real Content Start

Never cut by a fixed timestamp or silence alone.

1. Remove metadata, speaker labels, podcast title cards, generic greetings, and
   outro text from the script view used for matching.
2. Derive the target opening from the cover and first meaningful script sentence.
3. Transcribe with word timestamps using `faster-whisper`; use
   `scripts/transcribe_word_timestamps.py` for overlapping windows.
4. Require a continuous match containing the opening plus the next 20–40
   meaningful characters; reject a title-only match in an intro.
5. Cut at the verified first content phoneme, apply only a 5–10 ms click-safe
   fade, and re-transcribe the first 5–10 seconds.

Check local active-audio/word coverage before alignment, including after an
intro and at recognition-window boundaries. A high global match rate must not
hide a missed paragraph. Re-transcribe a confirmed hole with a speech-only
range; keep raw recognition and evidence. Do not interpolate an entire missing
passage. Use one retained-interval map for all cuts, regenerate dependent timing,
and independently check every join as well as the first and last content.

If music overlaps the required first phoneme, use a dedicated cleanup pass.
Never leave the music tail or remove the first syllable silently.

### 3. Build Correct Subtitles

- Use the approved script as final simplified-Chinese subtitle text. ASR supplies
  timings only.
- Use `scripts/build_slideshow_timeline.py` for canonical-script alignment,
  captions, and the slide timeline.
- Record match coverage; interpolate only unmatched character timings.
- Split on sentences or natural complete phrases. Never split a Chinese word to
  satisfy width.
- Use full Simplified-Chinese conversion, not a small character replacement
  table. Review all captions after lexical splitting; reviewed cue overrides
  must preserve the canonical script's normalized full text.
- Render one white line with dark outline/shadow inside safe margins. Prefer
  `Noto Sans SC` when no reference style overrides it.
- Keep editable `.srt`, `.ass`, and timing JSON beside production artifacts.

### 4. Match Visual States to Meaning

- Build a semantic anchor for every slide from its claim, diagram, formula, or
  section label.
- Segment the aligned narration into semantic blocks before assigning pages.
  For each block, choose the strongest matching anchor from the entire deck;
  do not default to the next page number.
- For every narration block, select a page whose prominent visible content can
  be justified sentence by sentence from the concurrent narration. Record
  `spoken meaning`, `visible claim`, `visible supporting details`, and `match
  level` in the semantic map. Judge the title, main claim, examples, labels,
  checklist items, actions, and conclusion that a viewer can actually see. A
  shared chapter, keyword, or topic is not sufficient evidence.

  | Match level | Test | Result |
  |---|---|---|
  | Exact | The visible claim, example, action, or conclusion is being spoken now | Pass |
  | Direct summary | The page compresses the current narration without introducing new teaching content | Pass |
  | Section-related | The page shares the topic but prominently shows specific content not currently spoken or directly supported | Fail |
  | Unrelated or late | The page belongs elsewhere or appears after its meaning has passed | Fail |

- Match narration and slide granularity. When the PPT expands a broad spoken
  point into branches, examples, tools, diagnostics, or action steps that the
  audio does not cover, keep or return to a broader overview page, reuse the
  strongest valid page, or skip the detailed page. Never show a specific page
  merely because it belongs to the same section or because it has not appeared
  yet.
- Treat these density mismatches as automatic warnings that require a different
  page unless the concurrent narration directly supports every prominent item:
  the audio gives one broad sentence while the page shows several branches;
  the audio lists categories while the page drills into one category; the
  audio explains `why` while the page introduces an unspoken `how`; or the
  audio states a result while the page shows an unspoken case.
- Treat the resulting narration-to-visual map as the source of truth. PPT order
  resolves ties only; it must never override a stronger semantic match.
- A page may be skipped, reordered, revisited, or held across several narration
  blocks. An unspoken checklist, tool, example, or expansion page is optional
  and must not be inserted for deck completeness.
- Start slides from aligned meaning, never equal duration or character ratios.
- Keep the cover at least 6 seconds and ordinary slides at least 4.5 seconds,
  unless an approved faster pacing contract explicitly replaces these defaults.
  These hold times are subordinate to semantic correctness: if inserting a
  detailed page would make it appear late, remain after its narration has moved
  on, or delay the next semantically correct page, skip it or assign the whole
  narration block to a broader valid page. Never preserve a page by shifting
  its boundary away from the spoken cue.
- Show a formula, diagram, table, or semantic group before or exactly when its
  explanation begins, never afterward.
- Dynamic: map every independently narrated direct-root group to its spoken cue;
  group order alone is not semantic timing.
- Review for quick flashes, late evidence, and topic mismatch before rendering.
- Before rendering, audit from the first content sentence through the end, not
  only user-reported timestamps, selected chapters, or suspected middle pages.
  At every visual-state start, record the first and last concurrent subtitle or
  meaning. For long holds, add regular internal checkpoints. Each checkpoint
  records the concurrent narration meaning, expected slide/group, and actual
  slide/group. The page must remain valid for the entire hold, not merely at its
  anchor phrase. Any mismatch fails the timeline even when the page numbers are
  sequential.
- Reject any state for which a reviewer could reasonably ask, "Why is this
  specific page on screen now?" Sequential order, topical relatedness, visual
  variety, page-count coverage, and avoiding slide reuse are not evidence of
  synchronization.

### 5. Render

**Static:** use `scripts/render_slideshow.py` with FFmpeg, 1920×1080, 30 fps,
H.264/AAC, ASS subtitles, and the approved semantic slide timeline. Default page
transition is a 0.7-second crossfade.

For Static production or revision, read
[references/static-pipeline.md](references/static-pipeline.md). Use its common
coverage, edit-map, caption and source-binding helpers rather than cloning an
old episode pipeline. An old subtitle/cache/WPS report requires exact source
identity; current filenames and page counts alone do not justify reuse.

**Dynamic:** follow [references/dynamic-video.md](references/dynamic-video.md).
HyperFrames consumes the portable resolved motion plan and semantic SVG groups;
the cleaned continuous recording remains the final audio master. GSAP may be
used only through seek-safe HyperFrames guidance.

### Resource Stability

- Default CPU-heavy work to 8 threads and one worker. This applies to
  `faster-whisper`, FFmpeg filter graphs, and `libx264`; do not automatically
  consume every logical CPU.
- `transcribe_word_timestamps.py --cpu-threads N` and
  `render_slideshow.py --threads N` may override the default when the machine
  has been verified stable. `PPT_VIDEO_CPU_THREADS` sets the shared default.
- Keep `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, and `MKL_NUM_THREADS` aligned
  with the chosen limit when those runtimes are present.
- A WHEA machine-check, cache-hierarchy error, freeze, or reboot is a hardware
  stability failure. Stop the heavy job, retain the 8-thread ceiling, and do
  not retry with unrestricted threads.

### 6. Required Final QA

- Verify duration and audio/video streams; output duration must equal cleaned
  audio within one frame.
- Inspect frames at 1 second, every chapter/slide boundary, every formula/table/
  diagram anchor, representative long captions, and 3–5 seconds before the end.
- Listen to the first second, first 10 seconds, all major boundaries, repaired
  audio regions, and final 5 seconds.
- Confirm the opening contains only the chosen content sentence, subtitles are
  complete and safe, visuals match concurrent speech, and no unwanted outro
  remains.
- Record actual QA methods separately. ASR, decode and waveform/correlation
  checks are not listening review. If required listening cannot be performed,
  mark it unperformed and disclose that limitation instead of claiming all QA
  gates passed.
- Run the semantic checkpoint audit across the full video, not only user-reported
  timestamps or the first pages. Explicitly catch systematic one-page offsets,
  pages shown before their subject is introduced, and pages held after the
  narration has moved on. A successful sequential page run is not evidence of
  synchronization.
- Dynamic: inspect before/during/after frames for every object reveal and verify
  random seeking reproduces sequential playback.
- When WPS is the fidelity target, read
  [references/wps-final-qa.md](references/wps-final-qa.md), run its recursive
  audit, and inspect the full rendered deck.

Any failed check returns to the owning audio edit, semantic map, SVG, animation
sidecar, or renderer. Re-render before delivery.

## Revision Safety

Back up `svg_output/` before visual repair. Touch only affected pages, preserve
page order/content and stable animation group IDs, and keep the previous PPTX.
After an SVG or group edit, rerun PPT Master's static and Chromium-rendered SVG
gates, animation validation, conversion trace, motion plan, and dynamic handoff
validation before rendering again.

## Exceptions

Stop only when no reliable decision is possible, such as incompatible final
PPTX/PDF versions, materially different script/audio, an ambiguous opening, or
irreducible music/speech overlap. Do not ask the user to perform ordinary QA.

## Delivery

- Save one final MP4 in the source delivery directory with a descriptive,
  versioned filename.
- Keep the final PPTX, complete PPT Master production directory, final audio,
  script, subtitles, semantic timelines, motion plan, HyperFrames project, and
  validation reports together in the delivery folder or clearly named
  subfolders.
- State the output path, final duration, verified opening sentence, selected
  Static/Dynamic route, and that the applicable QA gates passed.
