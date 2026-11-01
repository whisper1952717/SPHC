# Static Pipeline Reliability

Use these common helpers instead of copying a preceding episode's whole
assembly script. Keep episode decisions in data: retained intervals, canonical
script, reviewed caption lines, semantic anchors and QA records. Do not import
code from a historical delivery folder that the user may move.

## Source Identity

Record SHA-256 for current PPTX, PDF, audio, script and reused timing artifacts.
Reuse WPS inspection only when its exact PPTX hash and exported-page hashes
still match; otherwise rerun `wps_render_audit.ps1` and compare the current PDF
to the new WPS frames. An unchanged filename/page count or a successful prior
job is not version evidence. Windows/WSL source records are resolved by the
shared helper; content and actual local file identity must both agree.

## Transcript And Local Gaps

`transcribe_word_timestamps.py` writes word timestamps and a sibling
`<stem>_coverage.json`. Exit status 2 means active audio has no recognized words
for a sustained region. The raw transcript is retained for repair, not approved
for alignment. RMS flags active sound, not proven speech: music may also be
flagged. Inspect the flagged range; do not automatically cut it.

An existing transcript can be checked without running a model:

```text
python scripts/check_transcript_coverage.py --audio audio.wav --transcript words.json --output coverage.json
```

Exclude confirmed non-speech only through a JSON list containing `start`, `end`,
`reason` and concrete `evidence`. Do not classify an unexplained ASR hole as
silence/music simply to pass. Keep the exclusions with the evidence.

For a confirmed missed phrase, use `--repair-ranges ranges.json
--existing-transcript words.json --output words_repaired.json` with the full
same audio and duration. `ranges.json` is a chronological list of source-time
`[start,end]` pairs. Repair recognition does not extend backward into the failed
welcome/music context. Only words within the repair ranges replace previous
recognition; everything else remains. The old transcript must carry a matching
`source_audio` hash. For legacy files, verify cache audio identity first and
record that migration rather than blindly attaching a new hash.

Check the opening plus the next 20–40 meaningful characters, the complete end,
all flagged ranges, and locally unmatched text. A high overall match percentage
does not clear a long missing passage. Numeric spelling discrepancies may be
normalized only with checked audio/script evidence; preserve raw recognition.

## One Edit Map

Do not alter approved audio wording or cut substantive conclusions. Under the
usual assembly workflow remove generic welcome, clearly promotional insertions
and generic farewell, keeping substantive dialogue. An explicit user start/end
or preservation instruction wins. Standalone extraction/transcription preserves
the full source by default; it is not authorization to cut an audio programme.

```text
python scripts/edit_audio.py --source original.mp3 --transcript words_repaired.json --intervals retained.json --output-dir edit_v1 --threads 8
```

`retained.json` is the sole source-time list of retained `[start,end]` pairs.
The helper produces `clean_audio.wav`, `edited_word_timestamps.json` and
`audio_edit.json`, including every edited join and independent-review range.
Cut-straddling ASR words are listed and dropped, not given invented partial-word
timings. Resolve whether each is an inaccurate ASR boundary or a bad audio cut;
verify the first/last phoneme rather than trusting timestamp precision.

Re-transcribe the first/last 5–10 seconds and each join (typically 4 seconds on
each side). Inspect clicks, tail music and breathing as applicable. Then rerun
coverage on the edited audio/transcript. After any cut change, rebuild captions,
anchors and downstream validation; never shift an already edited transcript a
second time. Edited timestamps use `--trim-offset 0`.

## Captions And Anchors

Dependencies: `opencc-python-reimplemented` and `jieba` in the environment used
for the builder; `faster-whisper` in the recognition environment. Missing
dependencies are actionable errors, not permission to revert to a tiny manual
Traditional-to-Simplified table or character slicing.

```text
python scripts/build_slideshow_timeline.py --script canonical.md --transcript edit_v1/edited_word_timestamps.json --anchors anchors.json --duration SECONDS --trim-offset 0 --output-dir render_v1 --base episode --caption-lines caption_lines.txt --coverage-report edited_coverage.json
```

The automatic splitter respects lexical boundaries and prefers punctuation;
it is a draft, not semantic acceptance. Review every caption for complete
phrases, technical terms, numbers, orphan punctuation and excessively short or
long holds. `--caption-lines` takes one reviewed cue per line. Only punctuation
and whitespace may change: normalized full text must match the canonical
script. The script itself must first exclude the same cut audio material.

The alignment check blocks long unmatched character runs, a missing opening or
ending, collapsed timing and short visual states. It does not delay a state to
meet a minimum hold: remove/reassign the page instead. Align exact spoken cues
and keep the full semantic map/review from the main skill; a passing check is
not proof that the chosen slide means what is being spoken.

`alignment_check.json` binds sources and generated SRT/ASS/timeline hashes.
Renderer validation rejects failed, incomplete, changed or unrelated artifacts,
and audio not bound through the coverage report. `--font-size` and
`--margin-bottom` are explicit subtitle controls; inspect longest actual captions
in the rendered frame, not only character counts.

## Render And Final Evidence

```text
python scripts/render_slideshow.py --project render_v1 --images slides --audio ABSOLUTE_EDITED_AUDIO_PATH --subtitles episode_校准字幕.ass --output final_v1.mp4 --threads 8
```

Each image/audio input decoder uses one thread; filter/x264 and supporting math
runtimes use the requested ceiling (default 8). Run only one heavy job at a time.
The output is explicitly limited to the aligned duration. Existing MP4s are not
overwritten. `render_receipt.json` means rendered, not final QA passed.

Complete the main skill's full decode, boundary/long-hold semantic checkpoints,
first/last and longest-caption frame inspection, audio synchronization and
required listening review. Record actual methods separately: independent ASR,
waveform/correlation, decode, visual inspection, and actual listening. Decode
and correlation cannot prove absence of audible clicks or natural phrasing.
If a required listening check cannot be performed, mark it unperformed and
report that limitation; do not label it passed or claim all QA gates passed.
Do not routinely delegate ordinary checks to the user.

Use a new filename for revisions and verify the delivered copy hash. Keep
originals and current production evidence together; do not modify accepted
videos during skill regression testing.
