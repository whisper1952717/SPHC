from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

from faster_whisper import WhisperModel
from faster_whisper.audio import decode_audio


def main() -> int:
    parser = argparse.ArgumentParser(description="Create resilient word timestamps with faster-whisper.")
    parser.add_argument("--audio", required=True, help="Use an ASCII-safe path when running under WSL.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default="/mnt/c/Users/AdminLF/.cache/faster_whisper_ascii/base")
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--language", default="zh")
    parser.add_argument("--window", type=float, default=30.0)
    parser.add_argument("--overlap", type=float, default=2.0)
    parser.add_argument(
        "--cpu-threads",
        type=int,
        default=int(os.environ.get("PPT_VIDEO_CPU_THREADS", "8")),
        help="CPU threads used by faster-whisper (default: 8, or PPT_VIDEO_CPU_THREADS).",
    )
    args = parser.parse_args()
    if args.cpu_threads < 1:
        parser.error("--cpu-threads must be at least 1")

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
    for start in range(0, math.ceil(args.duration), int(args.window)):
        next_start = min(args.duration, start + args.window)
        clip_start = max(0.0, start - args.overlap)
        clip_end = min(args.duration, next_start + args.overlap)
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
    output = Path(args.output)
    output.write_text(
        json.dumps(
            {"language": info.language, "duration": round(args.duration, 3), "segments": rows},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"duration": round(args.duration, 3), "segments": len(rows), "output": str(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
