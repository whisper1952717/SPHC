# Dynamic Reveal Video Route

Read this reference when narration must reveal or emphasize individual parts of
a slide. The video behavior is the acceptance target. Native PowerPoint
animation may be retained as an additional deliverable, but it never substitutes
for verified motion in the rendered video.

**REQUIRED SUB-SKILL:** Use `hyperframes` before creating, editing, validating,
or rendering the composition. Let its current entry point select and load the
owning workflow and domain skills. For long narrated presentation videos this
will normally be a custom/general-video composition rather than an interactive
deck.

## 1. Canonical Motion Handoff

Use PPT Master's resolved artifacts, not an inferred delay list:

1. `svg_output/*.svg` — final visible states and direct-root semantic groups.
2. `animations.json` — canonical object intent, effects, order, and lifecycle.
3. The final SVG-to-PPTX conversion trace — resolved targets and timing after
   narration synchronization when narration governs reveals.
4. `validation/video_motion_plan.json` — renderer-neutral video families and
   locked identity/order/direction/timing.

Validate the canonical sidecar before generating the trace:

```bash
python3 <ppt-master-skill>/scripts/animation_config.py validate <ppt-project>
```

Generate the motion plan from the resolved conversion trace, never directly
from raw `animations.json` or `narration_animations.json`:

```bash
python3 <ppt-master-skill>/scripts/video_motion_plan.py \
  <ppt-project>/validation/<final>.trace.json \
  -o <ppt-project>/validation/video_motion_plan.json \
  --style adaptive --force
```

The written plan uses paths relative to the plan file. Run the portable handoff
validator before copying assets into HyperFrames:

```bash
python3 <this-skill>/scripts/validate_dynamic_handoff.py <ppt-project>
```

Do not continue on a missing SVG, stale absolute path, missing direct-root group,
non-video trigger, or timing that extends beyond its slide.

## 2. Bind Motion to the Finished Recording

Word-level ASR supplies time; the approved script supplies text; SVG group
semantics decide which object owns each spoken beat.

For one continuous recording:

- derive exact slide boundaries from semantic slide anchors;
- derive each independently narrated group's cue from its first explanatory
  phrase, not merely from group order;
- create page-local working SRT/audio segments when PPT Master's narration sync
  needs them, while preserving the cleaned continuous recording as the final
  audio master;
- map groups in `narration_timing.json`, derive
  `narration_animations.json`, and only then generate the final conversion
  trace and video motion plan.

An entrance should start at or slightly before the first word that requires the
object. It must not appear after its explanation. Keep already introduced
content visible unless its canonical lifecycle explicitly exits or replaces it.
Do not retime the finished motion plan by eye; repair the semantic cue mapping
and regenerate the trace and plan.

## 3. HyperFrames Realization

- Resolve `source_trace` and every slide `svg` relative to the motion-plan file.
- Preserve `group_id`, object order, source effect, semantic direction, and
  timing anchor. Only the plan's declared optimizer parameters may be refined.
- Mount each SVG so direct-root `<g id>` groups remain individually targetable.
- Treat cumulative slide durations as the global clock and object `start_ms` as
  slide-local time.
- Reject `on-click`; rendered video must use click-free timing.
- Use seek-safe HyperFrames keyframes. GSAP is allowed only through the current
  HyperFrames GSAP/keyframe guidance and must reproduce the same state when the
  renderer seeks directly to any frame. Do not rely on a fire-once browser
  timeline or wall-clock callbacks.
- Report an unsupported video effect family. Never silently reduce every effect
  to a generic fade or delay-only reveal.

## 4. Dynamic Acceptance

For every object event, inspect frames immediately before its start, during its
motion, and after completion:

- before: withheld content is genuinely absent or in its declared initial state;
- during: motion does not cover or reduce the readability of existing copy;
- after: the complete semantic unit is visible and stable;
- timing: the reveal lands with the spoken phrase within the approved tolerance;
- seeking: a frame rendered directly matches the same frame reached through
  sequential playback.

Also inspect every slide boundary and a full contact sheet. A technically valid
motion plan does not prove that the visual communicates the intended second
expression.

## 5. Revision Safety

Before a visual repair, copy the current `svg_output/` to the project's backup
area. Modify only affected pages and preserve stable group IDs unless the
semantic unit itself changes. After any SVG edit or regrouping, rerun in order:

1. PPT Master's static final SVG quality checker;
2. `rendered_svg_layout_check.py`;
3. `animation_config.py validate`;
4. conversion trace and `video_motion_plan.json` generation;
5. `validate_dynamic_handoff.py`;
6. HyperFrames check, snapshots, and final render.

Keep the prior PPTX and MP4. Publish a versioned replacement rather than
overwriting the last accepted artifacts.
