from __future__ import annotations

import argparse
import json
import re
from bisect import bisect_left
from difflib import SequenceMatcher
from pathlib import Path
from pipeline_common import alignment_health, bound_to, file_record, validate_slide_timing, verify_records


def simplified(text: str) -> str:
    from opencc import OpenCC
    if not hasattr(simplified, 'converter'):
        simplified.converter = OpenCC('t2s')
    return simplified.converter.convert(text)


TRADITIONAL = str.maketrans({"這": "这", "給": "给", "選": "选", "個": "个", "們": "们", "為": "为", "與": "与", "說": "说", "對": "对", "長": "长"})
PROTECTED_PAIRS = {
    "客户", "战略", "走向", "不同", "市场", "项目", "未来", "成为", "企业", "增长", "销售", "管理", "产品", "公司", "收入", "能力",
    "价值", "合作", "服务", "交付", "团队", "组织", "行业", "需求", "资源", "方向", "质量", "方法", "订单", "采购", "关系", "决策",
    "系统", "流程", "目标", "问题", "结果", "机会", "标准", "信用", "兴趣", "意向", "优先级", "共识", "行动", "方案", "成交", "值得",
}


def normalized(text: str) -> str:
    return "".join(re.findall(r"[\u4e00-\u9fff0-9a-z]", simplified(text).lower()))


def ass_time(seconds: float) -> str:
    total = int(round(seconds * 100))
    hours, total = divmod(total, 360000)
    minutes, total = divmod(total, 6000)
    seconds, centiseconds = divmod(total, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def srt_time(seconds: float) -> str:
    total = int(round(seconds * 1000))
    hours, total = divmod(total, 3600000)
    minutes, total = divmod(total, 60000)
    seconds, milliseconds = divmod(total, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def script_body(path: Path) -> str:
    source = path.read_text(encoding="utf-8-sig")
    parts = re.split(r"(?m)^---\s*$", source)
    source = parts[2] if len(parts) >= 3 else source
    lines = []
    for line in source.splitlines():
        line = line.strip()
        if not line or line.startswith(">") or line.startswith("#"):
            continue
        line = re.sub(r"^(?:说话人\d+|speaker\s*\d+|大壹|咪仔)[：:]\s*", "", line, flags=re.IGNORECASE)
        lines.append(line)
    return simplified("".join(lines))


def split_captions(text: str, max_chars: int = 20) -> list[str]:
    import jieba
    if max_chars < 4:
        raise ValueError('Caption width must allow complete words')
    text=re.sub(r'\s+','',simplified(text))
    jieba.add_word('关键信息')
    boundaries=set()
    offset=0
    for word in jieba.cut(text):
        offset+=len(word)
        boundaries.add(offset)
    result=[]
    offset=0
    while text:
        if len(text)<=max_chars:
            cut=len(text)
        else:
            sentence=re.search(r'[。！？；][”’」』]?',text[:max_chars+1])
            soft=[m.end() for m in re.finditer(r'[，、：]',text[:max_chars+1]) if m.end()>=max_chars//3]
            if sentence:
                cut=sentence.end()
            elif soft:
                cut=soft[-1]
            else:
                candidates=[b-offset for b in boundaries if offset<b<=offset+max_chars]
                cut=max(candidates) if candidates else min(b-offset for b in boundaries if b>offset)
        while cut<len(text) and text[cut] in '，。！？；：、”’」』':
            cut+=1
        result.append(text[:cut])
        text=text[cut:]
        offset+=cut
    return result


def reviewed_captions(text, rows):
    rows=[simplified(x.strip()) for x in rows if x.strip()]
    if normalized(''.join(rows))!=normalized(text):
        raise ValueError('Reviewed caption lines must preserve the canonical script')
    if any(row[0] in '，。！？；：、' for row in rows):
        raise ValueError('A caption cannot start with trailing punctuation')
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", required=True)
    parser.add_argument("--transcript", required=True)
    parser.add_argument("--anchors", required=True)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--trim-offset", type=float, required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument('--caption-lines', help='Reviewed UTF-8 captions, one line per cue; punctuation-only edits')
    parser.add_argument('--max-chars', type=int, default=25)
    parser.add_argument('--max-unmatched-run', type=int, default=20)
    parser.add_argument('--min-coverage', type=float, default=.9)
    parser.add_argument('--coverage-report', help='Passed source-bound transcript coverage report')
    parser.add_argument('--font-size', type=int, default=48)
    parser.add_argument('--margin-bottom', type=int, default=6)
    args = parser.parse_args()

    body = script_body(Path(args.script))
    captions = reviewed_captions(body,Path(args.caption_lines).read_text(encoding='utf-8-sig').splitlines()) if args.caption_lines else split_captions(body,args.max_chars)
    transcript = json.loads(Path(args.transcript).read_text(encoding="utf-8"))
    if transcript.get('time_basis')=='edited' and args.trim_offset!=0:
        raise ValueError('Edited timestamps must use --trim-offset 0')
    if args.coverage_report:
        coverage=json.loads(Path(args.coverage_report).read_text(encoding='utf-8'))
        if not coverage['passed']:
            raise ValueError('Transcript coverage has unresolved active-audio gaps')
        verify_records(coverage['sources'])
        if not bound_to(args.transcript,coverage['sources']):
            raise ValueError('Coverage report is for a different transcript')
    asr_chars, asr_times = [], []
    for segment in transcript["segments"]:
        for word in segment.get("words", []):
            text = normalized(word["word"])
            if not text:
                continue
            start, end = float(word["start"]), float(word["end"])
            width = (end - start) / len(text)
            for index, char in enumerate(text):
                asr_chars.append(char)
                asr_times.append((start + width * index, start + width * (index + 1)))

    caption_parts = [normalized(caption) for caption in captions]
    canonical = "".join(caption_parts)
    ranges, cursor = [], 0
    for part in caption_parts:
        ranges.append((cursor, cursor + len(part)))
        cursor += len(part)
    matches: dict[int, tuple[float, float]] = {}
    for block in SequenceMatcher(a=canonical, b="".join(asr_chars), autojunk=False).get_matching_blocks():
        for offset in range(block.size):
            matches[block.a + offset] = asr_times[block.b + offset]
    positions = sorted(matches)
    if not positions:
        raise RuntimeError("The podcast script could not be aligned to the audio")
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    check_path=output/'alignment_check.json'
    health=alignment_health(len(canonical),matches,args.max_unmatched_run,args.min_coverage)
    sources=[file_record(p) for p in (args.script,args.transcript,args.anchors)]
    if args.caption_lines:
        sources.append(file_record(args.caption_lines))
    if args.coverage_report:
        sources.append(file_record(args.coverage_report))
        sources.extend(coverage['sources'])
    check_path.write_text(json.dumps(dict(health,sources=sources,outputs=[]),ensure_ascii=False,indent=2),encoding='utf-8')
    if not health['passed']:
        raise ValueError('Local/global alignment failed; inspect alignment_check.json and re-transcribe missing regions')

    def raw_time(position: int, end: bool = False) -> float:
        if position in matches:
            return matches[position][1 if end else 0]
        point = bisect_left(positions, position)
        left = positions[point - 1] if point else None
        right = positions[point] if point < len(positions) else None
        if left is None:
            return matches[right][0]
        if right is None:
            return matches[left][1]
        a, b = matches[left][1], matches[right][0]
        return a + (b - a) * (position - left) / max(1, right - left)

    def video_time(position: int, end: bool = False) -> float:
        return max(0.0, min(args.duration, raw_time(position, end) - args.trim_offset))

    subtitle_rows = []
    for caption, (start_index, end_index) in zip(captions, ranges):
        covered = [index for index in range(start_index, end_index) if index in matches]
        start = video_time(covered[0] if covered else start_index)
        end = video_time(covered[-1] if covered else max(start_index, end_index - 1), end=True)
        subtitle_rows.append({"text": caption, "start": round(start, 3), "end": round(max(start + 0.25, end), 3), "match_ratio": round(len(covered) / max(1, end_index - start_index), 3)})
    for index in range(len(subtitle_rows) - 1):
        subtitle_rows[index]["end"] = round(min(subtitle_rows[index]["end"], subtitle_rows[index + 1]["start"]), 3)
        if subtitle_rows[index]["end"] <= subtitle_rows[index]["start"]:
            raise ValueError('Caption timing collapsed or overlaps; repair alignment rather than extend through the next cue')
    if any(row['end']<=row['start'] or row['end']>args.duration+.001 for row in subtitle_rows):
        raise ValueError('Caption timing is outside edited audio')

    anchors = json.loads(Path(args.anchors).read_text(encoding="utf-8"))
    if len(anchors) == 0:
        raise RuntimeError("At least one slide anchor is required")
    anchor_positions, search_from = [], 0
    for anchor in anchors:
        target = normalized(anchor["anchor"])
        position = canonical.find(target, search_from)
        if position < 0:
            raise RuntimeError(f"Unresolved slide anchor: {anchor['anchor']}")
        anchor_positions.append(position)
        search_from = position + 1
    starts = [video_time(position) for position in anchor_positions]
    starts[0] = 0.0
    validate_slide_timing(starts,args.duration)
    if starts[-1] >= args.duration:
        raise RuntimeError("Slide timeline exceeds the edited audio duration")
    slides = []
    for index, (anchor, start) in enumerate(zip(anchors, starts), 1):
        end = starts[index] if index < len(starts) else args.duration
        slide_number = int(anchor.get("slide", index))
        slides.append({"slide": slide_number, "file": f"slide-{slide_number:02d}.png", "start": round(start, 3), "end": round(end, 3), "duration": round(end - start, 3), "anchor": anchor["anchor"]})

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    srt = output / f"{args.base}_校准字幕.srt"
    ass = output / f"{args.base}_校准字幕.ass"
    timeline = output / "slide_timeline.json"
    audit = output / f"{args.base}_视频时间轴.json"
    with srt.open("w", encoding="utf-8") as handle:
        for number, row in enumerate(subtitle_rows, 1):
            handle.write(f"{number}\n{srt_time(row['start'])} --> {srt_time(row['end'])}\n{row['text']}\n\n")
    header = """[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\nStyle: Subtitle,Noto Sans SC,76,&H00FFFFFF,&H000000FF,&H00141414,&H96000000,1,0,0,0,100,100,0,0,1,3.2,0.8,2,80,80,70,1\n\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"""
    with ass.open("w", encoding="utf-8") as handle:
        header=header.replace('Noto Sans SC,76,',f'Noto Sans SC,{args.font_size},').replace(',2,80,80,70,1',f',2,80,80,{args.margin_bottom},1')
        handle.write(header)
        for row in subtitle_rows:
            text = row["text"].replace("\\", "\\\\").replace("{", "").replace("}", "")
            handle.write(f"Dialogue: 0,{ass_time(row['start'])},{ass_time(row['end'])},Subtitle,,0,0,0,,{text}\n")
    timeline.write_text(json.dumps(slides, ensure_ascii=False, indent=2), encoding="utf-8")
    audit.write_text(json.dumps({"duration": args.duration, "subtitle_match_coverage": round(len(matches) / max(1, len(canonical)), 4), "subtitles": subtitle_rows, "slides": slides}, ensure_ascii=False, indent=2), encoding="utf-8")
    health.update(sources=sources,outputs=[file_record(p) for p in (srt,ass,timeline,audit)])
    check_path.write_text(json.dumps(health,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({"captions": len(subtitle_rows), "slides": len(slides), "coverage": round(len(matches) / max(1, len(canonical)), 4)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
