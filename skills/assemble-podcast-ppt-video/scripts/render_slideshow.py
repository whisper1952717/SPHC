from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess

from pipeline_common import bound_to, file_record, validate_slide_timing, verify_records


def build_command(project, images, entries, audio, subtitles, output, transition, threads):
    if threads < 1 or transition <= 0:
        raise ValueError('Positive thread/transition settings required')
    duration = float(entries[-1]['end'])
    validate_slide_timing([float(e['start']) for e in entries], duration)
    for i, e in enumerate(entries):
        if abs(float(e['end'])-float(e['start'])-float(e['duration'])) > .002:
            raise ValueError('Inconsistent slide duration')
        if i and abs(float(e['start'])-float(entries[i-1]['end'])) > .002:
            raise ValueError('Slide timeline has a gap/overlap')
    if transition > min(float(e['duration']) for e in entries):
        raise ValueError('Transition is longer than a visual state')
    command = ['ffmpeg', '-n', '-hide_banner']
    for e in entries:
        command += ['-threads', '1', '-loop', '1', '-framerate', '30', '-t', f"{float(e['duration'])+transition:.3f}", '-i', str(images/e['file'])]
    command += ['-threads', '1', '-i', str(project/audio)]
    filters = [f'[{i}:v]fps=30,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p,settb=AVTB[v{i}]' for i in range(len(entries))]
    current = 'v0'
    for i in range(1, len(entries)):
        next_label = f'x{i}'
        filters.append(f'[{current}][v{i}]xfade=transition=fade:duration={transition:.3f}:offset={max(0,float(entries[i]["start"])-transition):.3f}[{next_label}]')
        current = next_label
    # Stage ASS under a controlled relative name, avoiding filtergraph metacharacters.
    if any(c in subtitles for c in "':;[]"):
        raise ValueError('Use a short relative subtitle filename inside the project')
    filters.append(f"[{current}]ass='{Path(subtitles).as_posix()}',format=yuv420p[vout]")
    command += ['-filter_complex_threads', str(threads), '-filter_complex', ';'.join(filters), '-map', '[vout]', '-map', f'{len(entries)}:a:0', '-c:v', 'libx264', '-threads', str(threads), '-preset', 'veryfast', '-crf', '18', '-r', '30', '-c:a', 'aac', '-b:a', '192k', '-t', f'{duration:.3f}', '-movflags', '+faststart', str(output)]
    return command


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--project', required=True)
    p.add_argument('--images', required=True)
    p.add_argument('--audio', default='clean_audio.m4a')
    p.add_argument('--subtitles', default='subtitles.ass')
    p.add_argument('--output', required=True)
    p.add_argument('--transition', type=float, default=.7)
    p.add_argument('--threads', type=int, default=int(os.environ.get('PPT_VIDEO_CPU_THREADS','8')))
    p.add_argument('--validation-report', default='alignment_check.json')
    args = p.parse_args()
    project = Path(args.project).resolve()
    output = (project/args.output).resolve()
    if output.exists():
        raise ValueError('Output exists; choose a new version instead of overwriting an accepted MP4')
    report = json.loads((project/args.validation_report).read_text(encoding='utf-8'))
    if not report.get('passed') or not report.get('outputs'):
        raise ValueError('Alignment validation is incomplete or failed')
    verify_records(report['sources']+report['outputs'])
    for artifact in (project/'slide_timeline.json',project/args.subtitles):
        if not bound_to(artifact,report['outputs']):
            raise ValueError(f'Unvalidated artifact: {artifact}')
    rows = json.loads((project/'slide_timeline.json').read_text(encoding='utf-8'))
    if not bound_to(project/args.audio,report['sources']):
        raise ValueError('Render audio is not bound to transcript coverage validation')
    command = build_command(project,Path(args.images).resolve(),rows,args.audio,args.subtitles,output,args.transition,args.threads)
    sources = [file_record(project/args.audio)]+[file_record(Path(args.images)/e['file']) for e in rows]
    audio = json.loads(subprocess.run(['ffprobe','-v','error','-show_format','-of','json',str(project/args.audio)],check=True,capture_output=True).stdout)
    if abs(float(audio['format']['duration'])-float(rows[-1]['end'])) > 1/30:
        raise ValueError('Audio duration differs from aligned timeline')
    env = os.environ.copy()
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
        env[key] = str(args.threads)
    (project/'render_command.json').write_text(json.dumps(command,indent=2),encoding='utf-8')
    subprocess.run(command,check=True,cwd=project,env=env)
    verify_records(sources+report['sources']+report['outputs'])
    (project/'render_receipt.json').write_text(json.dumps({'sources':sources,'output':file_record(output),'status':'rendered_not_final_qa'},indent=2),encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
