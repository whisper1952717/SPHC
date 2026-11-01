"""Audit local ASR holes against active audio; flags require review, not auto-cutting."""
import argparse
from array import array
import json
from pathlib import Path
import subprocess

from pipeline_common import coverage_health, file_record


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--audio',required=True)
    p.add_argument('--transcript',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--non-speech-ranges',help='JSON reviewed exclusions: start/end/reason/evidence')
    args=p.parse_args()
    pcm=subprocess.run(['ffmpeg','-v','error','-threads','1','-i',args.audio,'-vn','-filter_threads','8','-ac','1','-ar','16000','-f','f32le','pipe:1'],check=True,capture_output=True)
    samples=array('f');samples.frombytes(pcm.stdout)
    transcript=json.loads(Path(args.transcript).read_text(encoding='utf-8-sig'))
    ignored=json.loads(Path(args.non_speech_ranges).read_text(encoding='utf-8-sig')) if args.non_speech_ranges else []
    report=coverage_health(samples,16000,transcript['segments'],ignored_ranges=ignored)
    report['sources']=[file_record(args.audio),file_record(args.transcript)]
    if args.non_speech_ranges:
        report['sources'].append(file_record(args.non_speech_ranges))
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
    return 0 if report['passed'] else 2


if __name__=='__main__':
    raise SystemExit(main())
