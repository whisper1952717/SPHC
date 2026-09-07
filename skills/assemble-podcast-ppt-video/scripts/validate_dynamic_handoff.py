#!/usr/bin/env python3
"""Validate the portable PPT Master -> dynamic-video handoff."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


PLAN_SCHEMA = "ppt-master.video-motion-plan.v1"
REPORT_SCHEMA = "assemble-podcast-ppt-video.dynamic-handoff-report.v1"


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {label} JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return value


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _resolve_plan_path(raw: object, plan_path: Path, project: Path) -> Path | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    path = Path(raw)
    if path.is_absolute():
        return path.resolve()
    # New portable plans declare path_base=plan. Keep project-relative support
    # for older hand-authored plans, but never search arbitrary directories.
    candidate = (plan_path.parent / path).resolve()
    if candidate.exists():
        return candidate
    return (project / path).resolve()


def _direct_group_ids(svg_path: Path) -> set[str]:
    try:
        root = ET.parse(svg_path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise ValueError(f"cannot parse SVG {svg_path}: {exc}") from exc
    result: set[str] = set()
    for child in list(root):
        if child.tag.rsplit("}", 1)[-1] != "g":
            continue
        group_id = child.get("id")
        if group_id:
            result.add(group_id)
    return result


def validate_project(
    project_path: str | Path,
    plan_path: str | Path | None = None,
) -> dict[str, Any]:
    project = Path(project_path).resolve()
    plan_file = (
        Path(plan_path).resolve()
        if plan_path is not None
        else project / "validation" / "video_motion_plan.json"
    )
    errors: list[str] = []

    if not (project / "animations.json").is_file():
        errors.append("missing canonical animations.json")
    try:
        plan = _read_object(plan_file, "video motion plan")
    except ValueError as exc:
        return {
            "schema": REPORT_SCHEMA,
            "project": str(project),
            "plan": str(plan_file),
            "passed": False,
            "slide_count": 0,
            "object_count": 0,
            "errors": errors + [str(exc)],
        }

    if plan.get("schema") != PLAN_SCHEMA:
        errors.append(
            f"unsupported plan schema: {plan.get('schema')!r}; expected {PLAN_SCHEMA}"
        )
    if plan.get("path_base") != "plan":
        errors.append(
            "video motion plan is not portable: path_base must be 'plan'"
        )

    trace_path = _resolve_plan_path(plan.get("source_trace"), plan_file, project)
    if trace_path is None or not trace_path.is_file():
        errors.append("source conversion trace is missing or unresolved")
    elif not _inside(trace_path, project):
        errors.append(f"source conversion trace is outside the project: {trace_path}")

    slides = plan.get("slides")
    if not isinstance(slides, list) or not slides:
        errors.append("video motion plan must contain a non-empty slides list")
        slides = []

    seen_slides: set[int] = set()
    counted_objects = 0
    for index, slide in enumerate(slides, 1):
        if not isinstance(slide, dict):
            errors.append(f"slide entry {index} is not an object")
            continue
        slide_num = slide.get("slide_num")
        if not isinstance(slide_num, int) or isinstance(slide_num, bool) or slide_num <= 0:
            errors.append(f"slide entry {index} has invalid slide_num")
            continue
        if slide_num in seen_slides:
            errors.append(f"duplicate slide_num {slide_num}")
        seen_slides.add(slide_num)

        svg_path = _resolve_plan_path(slide.get("svg"), plan_file, project)
        if svg_path is None or not svg_path.is_file():
            errors.append(f"slide {slide_num} SVG is missing or unresolved")
            continue
        if not _inside(svg_path, project / "svg_output"):
            errors.append(f"slide {slide_num} SVG is outside project svg_output: {svg_path}")
            continue
        try:
            group_ids = _direct_group_ids(svg_path)
        except ValueError as exc:
            errors.append(str(exc))
            continue

        duration_ms = slide.get("duration_ms")
        if (
            not isinstance(duration_ms, int)
            or isinstance(duration_ms, bool)
            or duration_ms <= 0
        ):
            errors.append(f"slide {slide_num} has invalid duration_ms")
            duration_ms = 0

        objects = slide.get("objects", [])
        if not isinstance(objects, list):
            errors.append(f"slide {slide_num} objects must be a list")
            continue
        seen_groups: set[str] = set()
        prior_order = 0
        for object_index, item in enumerate(objects, 1):
            counted_objects += 1
            if not isinstance(item, dict):
                errors.append(
                    f"slide {slide_num} object {object_index} is not an object"
                )
                continue
            group_id = item.get("group_id")
            if not isinstance(group_id, str) or not group_id:
                errors.append(f"slide {slide_num} object {object_index} has no group_id")
            elif group_id not in group_ids:
                errors.append(
                    f"slide {slide_num} SVG is missing direct-root group '{group_id}'"
                )
            elif group_id in seen_groups:
                errors.append(f"slide {slide_num} repeats group_id '{group_id}'")
            else:
                seen_groups.add(group_id)

            order = item.get("order")
            if not isinstance(order, int) or isinstance(order, bool) or order <= prior_order:
                errors.append(
                    f"slide {slide_num} object order is not strictly increasing"
                )
            elif order != object_index:
                errors.append(
                    f"slide {slide_num} object order must be contiguous from 1"
                )
            prior_order = order if isinstance(order, int) else prior_order

            trigger = item.get("trigger")
            if trigger not in {"after-previous", "with-previous"}:
                errors.append(
                    f"slide {slide_num} group {group_id!r} has non-video trigger {trigger!r}"
                )
            start_ms = item.get("start_ms")
            object_duration = item.get("duration_ms")
            if (
                not isinstance(start_ms, int)
                or isinstance(start_ms, bool)
                or start_ms < 0
                or not isinstance(object_duration, int)
                or isinstance(object_duration, bool)
                or object_duration <= 0
            ):
                errors.append(
                    f"slide {slide_num} group {group_id!r} has invalid timing"
                )
            elif duration_ms and start_ms + object_duration > duration_ms:
                errors.append(
                    f"slide {slide_num} group {group_id!r} ends after the slide"
                )
            video = item.get("video")
            if not isinstance(video, dict) or not isinstance(video.get("family"), str):
                errors.append(
                    f"slide {slide_num} group {group_id!r} has no video effect family"
                )

    declared_slides = plan.get("slide_count")
    if declared_slides != len(slides):
        errors.append(
            f"slide_count mismatch: declared {declared_slides!r}, actual {len(slides)}"
        )
    declared_objects = plan.get("object_count")
    if declared_objects != counted_objects:
        errors.append(
            f"object_count mismatch: declared {declared_objects!r}, actual {counted_objects}"
        )

    return {
        "schema": REPORT_SCHEMA,
        "project": str(project),
        "plan": str(plan_file),
        "passed": not errors,
        "slide_count": len(slides),
        "object_count": counted_objects,
        "errors": errors,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a portable PPT Master dynamic-video handoff."
    )
    parser.add_argument("project_path", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = validate_project(args.project_path, args.plan)
    output = (
        args.output.resolve()
        if args.output
        else Path(args.project_path).resolve()
        / "validation"
        / "dynamic_handoff_report.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"slides={report['slide_count']} objects={report['object_count']} "
        f"errors={len(report['errors'])} report={output}"
    )
    if report["errors"]:
        for error in report["errors"]:
            print(f"  - {error}", file=sys.stderr)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
