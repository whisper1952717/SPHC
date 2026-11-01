"""Render one retained-interval map and regenerate dependent word timestamps."""
import argparse
import json
from pathlib import Path
import subprocess

from pipeline_common import edited_duration, file_record, join_points, retime_transcript, validate_intervals, verify_records


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',required=True)
    p.add_argument('--transcript',required=True)
    p.add_argument('--intervals',required=True,help='JSON list of retained source-time [start,end] pairs')
    p.add_argument('--output-dir',required=True)
    p.add_argument('--threads',type=int,default=8)
    args=p.parse_args()
    if args.threads<1:
        p.error('Thread count must be positive')
    root=Path(args.output_dir);root.mkdir(parents=True,exist_ok=True)
    audio=root/'clean_audio.wav';words=root/'edited_word_timestamps.json';manifest=root/'audio_edit.json'
    if any(x.exists() for x in (audio,words,manifest)):
        raise ValueError('Edit outputs exist; use a new working/version directory')
    sources=[file_record(p) for p in (args.source,args.transcript,args.intervals)]
    info=json.loads(subprocess.run(['ffprobe','-v','error','-show_format','-of','json',args.source],check=True,capture_output=True).stdout)
    duration=float(info['format']['duration'])
    intervals=json.loads(Path(args.intervals).read_text(encoding='utf-8-sig'))
    validate_intervals(intervals,duration)
    transcript=json.loads(Path(args.transcript).read_text(encoding='utf-8-sig'))
    if transcript.get('source_audio',{}).get('sha256')!=sources[0]['sha256']:
        raise ValueError('Transcript must be bound to this audio; verify/migrate legacy provenance first')
    if transcript.get('time_basis')=='edited':
        raise ValueError('Transcript already retimed; do not apply the edit map twice')
    mapped=retime_transcript(transcript,intervals)
    filters=[]
    for i,(start,end) in enumerate(intervals):
        filters.append(f'[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.008,afade=t=out:st={max(0,end-start-.008)}:d=0.008[a{i}]')
    filters.append(''.join(f'[a{i}]' for i in range(len(intervals)))+f'concat=n={len(intervals)}:v=0:a=1[out]')
    subprocess.run(['ffmpeg','-n','-v','error','-threads','1','-i',args.source,'-filter_complex_threads',str(args.threads),'-filter_complex',';'.join(filters),'-map','[out]','-ar','48000','-ac','2',str(audio)],check=True)
    joins=join_points(intervals)
    total=edited_duration(intervals)
    mapped.update(time_basis='edited',source_audio=file_record(audio),original_audio=sources[0],retained_intervals=intervals)
    words.write_text(json.dumps(mapped,ensure_ascii=False,indent=2),encoding='utf-8')
    checks=[{'kind':'opening','start':0,'end':min(10,total)},{'kind':'ending','start':max(0,total-10),'end':total}]+[{'kind':f'join_{i+1}','start':max(0,t-4),'end':min(total,t+4)} for i,t in enumerate(joins)]
    verify_records(sources)
    manifest.write_text(json.dumps({'sources':sources,'outputs':[file_record(audio),file_record(words)],'retained_intervals':intervals,'duration':round(total,6),'joins':joins,'required_review_ranges':checks,'cut_straddling_words':mapped['cut_straddling_words'],'review_status':'pending_independent_ASR_and_audio_checks'},ensure_ascii=False,indent=2),encoding='utf-8')
    print(manifest)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
