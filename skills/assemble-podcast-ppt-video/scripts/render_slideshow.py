from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--images", required=True)
    parser.add_argument("--audio", default="clean_audio.m4a")
    parser.add_argument("--subtitles", default="subtitles.ass")
    parser.add_argument("--output", required=True)
    parser.add_argument("--transition", type=float, default=0.7)
    parser.add_argument(
        "--threads",
        type=int,
        default=int(os.environ.get("PPT_VIDEO_CPU_THREADS", "8")),
        help="FFmpeg filter and H.264 encoder threads (default: 8, or PPT_VIDEO_CPU_THREADS).",
    )
    args = parser.parse_args()
    if args.threads < 1:
        parser.error("--threads must be at least 1")
    project, images = Path(args.project), Path(args.images)
    entries = json.loads((project / "slide_timeline.json").read_text(encoding="utf-8"))
    command = ["ffmpeg", "-y", "-hide_banner"]
    for entry in entries:
        command.extend(["-loop", "1", "-framerate", "30", "-t", f"{float(entry['duration']) + args.transition:.3f}", "-i", str(images / entry["file"])])
    command.extend(["-i", str(project / args.audio)])
    filters = []
    for index in range(len(entries)):
        filters.append(f"[{index}:v]fps=30,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p,settb=AVTB[v{index}]")
    current = "v0"
    for index in range(1, len(entries)):
        output = f"x{index}"
        offset = max(0.0, float(entries[index]["start"]) - args.transition)
        filters.append(f"[{current}][v{index}]xfade=transition=fade:duration={args.transition:.2f}:offset={offset:.3f}[{output}]")
        current = output
    filters.append(f"[{current}]ass='{Path(args.subtitles).as_posix()}',format=yuv420p[vout]")
    command.extend([
        "-filter_complex_threads", str(args.threads),
        "-filter_complex", ";".join(filters),
        "-map", "[vout]", "-map", f"{len(entries)}:a:0",
        "-c:v", "libx264", "-threads", str(args.threads),
        "-preset", "veryfast", "-crf", "18", "-r", "30",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        "-shortest", str(project / args.output),
    ])
    process_env = os.environ.copy()
    thread_limit = str(args.threads)
    process_env["OMP_NUM_THREADS"] = thread_limit
    process_env["OPENBLAS_NUM_THREADS"] = thread_limit
    process_env["MKL_NUM_THREADS"] = thread_limit
    subprocess.run(command, check=True, cwd=project, env=process_env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
