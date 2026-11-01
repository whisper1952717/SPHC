"""Shared timing, coverage and source-identity checks; no media side effects."""
from __future__ import annotations

import hashlib
import math
import os
import re
from pathlib import Path


def local_path(path):
    value=str(path)
    if os.name=='nt' and re.match(r'^/mnt/[a-zA-Z]/',value):
        value=value[5].upper()+':/'+value[7:]
    elif os.name!='nt' and re.match(r'^[a-zA-Z]:[/\\]',value):
        value='/mnt/'+value[0].lower()+'/'+value[3:].replace('\\','/')
    return Path(value)


def file_record(path):
    path = local_path(path).resolve()
    with path.open('rb') as handle:
        hasher=hashlib.sha256()
        for block in iter(lambda:handle.read(1024*1024),b''):
            hasher.update(block)
        digest=hasher.hexdigest()
    return {'path': str(path), 'sha256': digest}


def verify_records(records):
    for record in records:
        if file_record(record['path'])['sha256'] != record['sha256']:
            raise ValueError(f"Stale source/output: {record['path']}")


def bound_to(path, records):
    current=file_record(path)
    return any(local_path(r['path']).resolve()==local_path(current['path']).resolve() and r['sha256']==current['sha256'] for r in records)


def validate_intervals(intervals, duration):
    if not intervals or not math.isfinite(duration) or duration <= 0:
        raise ValueError('Finite positive source duration and retained intervals are required')
    previous = 0.0
    for start, end in intervals:
        if not all(math.isfinite(x) for x in (start,end)) or start < previous or start < 0 or end <= start or end > duration + .00001:
            raise ValueError(f'Invalid/overlapping retained interval: {[start,end]}')
        previous = end


def edited_duration(intervals):
    return sum(end-start for start,end in intervals)


def join_points(intervals):
    result, offset = [], 0.0
    for start,end in intervals[:-1]:
        offset += end-start
        result.append(round(offset,6))
    return result


def source_to_edited(time, intervals):
    offset = 0.0
    for start,end in intervals:
        if start <= time <= end:
            return offset + time-start
        offset += end-start
    raise ValueError(f'Timestamp {time} falls in removed audio')


def retime_transcript(transcript, intervals):
    """Drop cut-straddling words rather than fabricating partial-word timestamps."""
    result, offset, straddling = [], 0.0, []
    for start,end in intervals:
        for segment in transcript['segments']:
            words = []
            for word in segment.get('words',[]):
                a,b = word['start'],word['end']
                if b <= start or a >= end:
                    continue
                if a < start-.00001 or b > end+.00001:
                    straddling.append(dict(word))
                    continue
                words.append(dict(word,start=round(a-start+offset,6),end=round(b-start+offset,6)))
            if words:
                result.append({'start':words[0]['start'],'end':words[-1]['end'], 'text':''.join(w['word'] for w in words),'words':words})
        offset += end-start
    return {'language':transcript.get('language','zh'),'duration':round(offset,6),'segments':result,'cut_straddling_words':straddling}


def alignment_health(length, matches, max_unmatched_run=20, min_coverage=.9):
    missing, start = [], None
    for i in range(length+1):
        if i < length and i not in matches:
            if start is None:
                start=i
        elif start is not None:
            missing.append({'start_char':start,'end_char':i,'characters':i-start})
            start=None
    coverage=len(matches)/max(1,length)
    flags=[r for r in missing if r['characters']>=max_unmatched_run or (r['start_char']==0 and r['characters']>=6) or (r['end_char']==length and r['characters']>=6)]
    return {'passed':length>0 and coverage>=min_coverage and not flags,'coverage':round(coverage,6),'unmatched_runs':missing,'blocking_runs':flags}


def coverage_health(samples, sample_rate, segments, min_gap=2.0, ignored_ranges=()):
    """Flag active sound without recognized words, not assert that sound is speech."""
    step=max(1,round(sample_rate*.02))
    energy=[]
    for i in range(0,len(samples),step):
        frame=samples[i:i+step]
        energy.append(math.sqrt(sum(float(x)*float(x) for x in frame)/max(1,len(frame))))
    peak=max(energy,default=0)
    threshold=max(.002,peak*.015)
    covered=[False]*len(energy)
    for s in segments:
        for w in s.get('words',[]):
            lo=max(0,int((w['start']-.12)/.02))
            hi=min(len(energy),math.ceil((w['end']+.12)/.02))
            for i in range(lo,hi):
                covered[i]=True
    for r in ignored_ranges:
        if not r.get('reason') or not r.get('evidence') or r['start']<0 or r['end']<=r['start'] or r['end']>len(samples)/sample_rate+.02:
            raise ValueError('Non-speech exclusions require valid bounds, reason and evidence')
        for i in range(max(0,int(r['start']/.02)),min(len(energy),math.ceil(r['end']/.02))):
            covered[i]=True
    active=[i for i,e in enumerate(energy) if e>=threshold and not covered[i]]
    groups=[]
    for i in active:
        if groups and (i-groups[-1][-1])*.02<=.4:
            groups[-1].append(i)
        else:
            groups.append([i])
    flags=[{'start':round(g[0]*.02,3),'end':round((g[-1]+1)*.02,3),'active_seconds':round(len(g)*.02,3)} for g in groups if (g[-1]-g[0]+1)*.02>=min_gap and len(g)*.02>=1]
    return {'passed':not flags,'uncovered_active_ranges':flags,'energy_threshold':threshold,'method':'20ms RMS + word intervals; active sound is not proof of speech','non_speech_exclusions':list(ignored_ranges)}


def validate_slide_timing(starts, duration):
    if not starts or starts[0]!=0 or not math.isfinite(duration) or duration<=0 or not all(math.isfinite(s) for s in starts):
        raise ValueError('Timeline must start at zero and have positive duration')
    for i,start in enumerate(starts):
        end=starts[i+1] if i+1<len(starts) else duration
        if end-start < (6 if i==0 else 4.5)-.001:
            raise ValueError(f'State {i+1} is too short; remove/reassign the page, do not delay its spoken cue')
