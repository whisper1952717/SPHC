from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from pipeline_common import coverage_health, file_record, validate_intervals, verify_records


def main() -> int:
    parser = argparse.ArgumentParser(description="Create resilient word timestamps with faster-whisper.")
    parser.add_argument("--audio", required=True, help="Use an ASCII-safe path when running under WSL.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default="/mnt/c/Users/AdminLF/.cache/faster_whisper_ascii/base")
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--language", default="zh")
    parser.add_argument("--window", type=float, default=30.0)
    parser.add_argument("--overlap", type=float, default=2.0)
    parser.add_argument('--repair-ranges', help='JSON source-time intervals to re-transcribe')
    parser.add_argument('--existing-transcript', help='Same-audio transcript to merge repairs into')
    parser.add_argument('--non-speech-ranges', help='Reviewed exclusions with start/end/reason/evidence')
    parser.add_argument(
        "--cpu-threads",
        type=int,
        default=int(os.environ.get("PPT_VIDEO_CPU_THREADS", "8")),
        help="CPU threads used by faster-whisper (default: 8, or PPT_VIDEO_CPU_THREADS).",
    )
    args = parser.parse_args()
    if args.cpu_threads < 1:
        parser.error("--cpu-threads must be at least 1")
    if args.window < 1 or not args.window.is_integer() or args.overlap < 0 or not math.isfinite(args.duration) or args.duration <= 0:
        parser.error('Use positive duration/integer window and nonnegative overlap')
    if bool(args.repair_ranges) != bool(args.existing_transcript):
        parser.error('Repair ranges and existing transcript must be supplied together')
    output=Path(args.output)
    if output.exists():
        raise ValueError('Transcript output exists; preserve it and use a new version')
    source_record=file_record(args.audio)
    existing=None
    if args.existing_transcript:
        existing=json.loads(Path(args.existing_transcript).read_text(encoding='utf-8-sig'))
        if existing.get('source_audio',{}).get('sha256')!=source_record['sha256']:
            raise ValueError('Repair transcript is not bound to this audio; verify legacy cache identity first')

    thread_limit = str(args.cpu_threads)
    os.environ["OMP_NUM_THREADS"] = thread_limit
    os.environ["OPENBLAS_NUM_THREADS"] = thread_limit
    os.environ["MKL_NUM_THREADS"] = thread_limit

    from faster_whisper import WhisperModel
    from faster_whisper.audio import decode_audio

    model = WhisperModel(
        args.model,
        device="cpu",
        compute_type="int8",
        cpu_threads=args.cpu_threads,
        num_workers=1,
    )
    rows = []
    info = None
    sample_rate = 16000
    decoded_audio = decode_audio(args.audio, sampling_rate=sample_rate)
    if abs(len(decoded_audio)/sample_rate-args.duration)>.15:
        raise ValueError('Supplied duration differs from decoded audio')
    if args.repair_ranges:
        windows=json.loads(Path(args.repair_ranges).read_text(encoding='utf-8-sig'))
        validate_intervals(windows,args.duration)
    else:
        windows=[(start,min(args.duration,start+args.window)) for start in range(0,math.ceil(args.duration),int(args.window))]
    for start,next_start in windows:
        # Repairs intentionally exclude the preceding greeting/music rather than
        # reintroducing the failed context through overlap.
        clip_start = start if args.repair_ranges else max(0.0,start-args.overlap)
        clip_end = next_start if args.repair_ranges else min(args.duration,next_start+args.overlap)
        if clip_start >= clip_end:
            continue
        clip_audio = decoded_audio[int(clip_start * sample_rate) : int(clip_end * sample_rate)]
        segments, info = model.transcribe(
            clip_audio,
            language=args.language,
            beam_size=5,
            vad_filter=False,
            no_speech_threshold=0.95,
            condition_on_previous_text=False,
            word_timestamps=True,
        )
        for segment in segments:
            # Keep words by their own timestamps. A segment can begin before a
            # window boundary and continue well into the next interval; dropping
            # the whole segment would create a large transcript gap.
            kept_words = []
            for word in segment.words or []:
                global_start = word.start + clip_start
                global_end = word.end + clip_start
                if global_start + 0.01 < start or global_start >= next_start:
                    continue
                kept_words.append(
                    {
                        "start": global_start,
                        "end": global_end,
                        "word": word.word,
                        "probability": word.probability,
                    }
                )
            if not kept_words:
                continue
            rows.append(
                {
                    "start": round(kept_words[0]["start"], 3),
                    "end": round(kept_words[-1]["end"], 3),
                    "text": "".join(word["word"] for word in kept_words).strip(),
                    "words": [
                        {
                            "start": round(word["start"], 3),
                            "end": round(word["end"], 3),
                            "word": word["word"].strip(),
                            "probability": round(word["probability"], 4),
                        }
                        for word in kept_words
                        if word["word"].strip()
                    ],
                }
            )

    if info is None:
        raise RuntimeError("No audio segments were processed")
    if args.existing_transcript:
        kept=[]
        for s in existing['segments']:
            words=[w for w in s.get('words',[]) if not any(w['end']>a and w['start']<b for a,b in windows)]
            if words:
                kept.append({'start':words[0]['start'],'end':words[-1]['end'],'text':''.join(w['word'] for w in words),'words':words})
        rows=sorted(kept+rows,key=lambda s:s['start'])
    output.parent.mkdir(parents=True,exist_ok=True)
    verify_records([source_record])
    output.write_text(
        json.dumps(
            {"language": info.language, "duration": round(args.duration, 3), "segments": rows, 'source_audio':source_record},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"duration": round(args.duration, 3), "segments": len(rows), "output": str(output)}))
    ignored=json.loads(Path(args.non_speech_ranges).read_text(encoding='utf-8-sig')) if args.non_speech_ranges else []
    health=coverage_health(decoded_audio,sample_rate,rows,ignored_ranges=ignored)
    health['sources']=[source_record,file_record(output)]
    if args.non_speech_ranges:
        health['sources'].append(file_record(args.non_speech_ranges))
    output.with_name(output.stem+'_coverage.json').write_text(json.dumps(health,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'coverage_passed':health['passed'],'uncovered_active_ranges':health['uncovered_active_ranges']}))
    return 0 if health['passed'] else 2


if __name__ == "__main__":
    raise SystemExit(main())
