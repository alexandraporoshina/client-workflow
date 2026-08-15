#!/usr/bin/env python3
"""Render a strictly neutral food-diary JSON payload as a PDF."""

from __future__ import annotations

import argparse
from datetime import datetime
from html import escape
import json
from pathlib import Path
import re
import sys
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


TOP_LEVEL_KEYS = {"title", "period", "entries"}
ENTRY_KEYS = {"time", "food", "client_note", "nutrition"}
INSUFFICIENT_NUTRITION_KEYS = {"status"}
ESTIMATED_NUTRITION_KEYS = {
    "status",
    "kcal",
    "protein_g",
    "fat_g",
    "carbs_g",
    "assumptions",
}
FONT_CANDIDATES = (
    (
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ),
    (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ),
)


def _require_exact_keys(
    value: dict[str, Any], allowed: set[str], location: str
) -> None:
    unknown = set(value) - allowed
    if unknown:
        fields = ", ".join(sorted(unknown))
        raise ValueError(f"unsupported {location} fields: {fields}")

    missing = allowed - set(value)
    if missing:
        fields = ", ".join(sorted(missing))
        raise ValueError(f"missing {location} fields: {fields}")


def _require_string(value: Any, location: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{location} must be a string")
    return value


def _require_number(value: Any, location: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{location} must be a number")
    return value


def _validate_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("top-level JSON value must be an object")
    _require_exact_keys(payload, TOP_LEVEL_KEYS, "top-level")

    _require_string(payload["title"], "title")
    _require_string(payload["period"], "period")
    entries = payload["entries"]
    if not isinstance(entries, list):
        raise ValueError("entries must be a list")

    for index, entry in enumerate(entries):
        entry_location = f"entry {index}"
        if not isinstance(entry, dict):
            raise ValueError(f"{entry_location} must be an object")
        _require_exact_keys(entry, ENTRY_KEYS, "entry")

        time_value = _require_string(entry["time"], f"{entry_location}.time")
        if re.fullmatch(r"\d{2}:\d{2}", time_value) is None:
            raise ValueError(f"{entry_location}.time must use HH:MM")
        try:
            datetime.strptime(time_value, "%H:%M")
        except ValueError as error:
            raise ValueError(f"{entry_location}.time must use HH:MM") from error
        _require_string(entry["food"], f"{entry_location}.food")
        _require_string(entry["client_note"], f"{entry_location}.client_note")

        nutrition = entry["nutrition"]
        if not isinstance(nutrition, dict):
            raise ValueError(f"{entry_location}.nutrition must be an object")
        status = nutrition.get("status")
        if status == "insufficient_data":
            _require_exact_keys(
                nutrition, INSUFFICIENT_NUTRITION_KEYS, "nutrition"
            )
        elif status == "estimated":
            _require_exact_keys(nutrition, ESTIMATED_NUTRITION_KEYS, "nutrition")
            for key in ("kcal", "protein_g", "fat_g", "carbs_g"):
                _require_number(nutrition[key], f"{entry_location}.nutrition.{key}")
            _require_string(
                nutrition["assumptions"],
                f"{entry_location}.nutrition.assumptions",
            )
        else:
            raise ValueError(
                f"{entry_location}.nutrition.status must be "
                "insufficient_data or estimated"
            )

    return payload


def _register_fonts() -> tuple[str, str]:
    for regular_path, bold_path in FONT_CANDIDATES:
        if regular_path.is_file() and bold_path.is_file():
            pdfmetrics.registerFont(TTFont("DiaryRegular", str(regular_path)))
            pdfmetrics.registerFont(TTFont("DiaryBold", str(bold_path)))
            return "DiaryRegular", "DiaryBold"
    raise RuntimeError("no Unicode-capable font found")


def _format_number(value: int | float) -> str:
    return f"{value:g}"


def _nutrition_text(nutrition: dict[str, Any]) -> str:
    if nutrition["status"] == "insufficient_data":
        return "КБЖУ не рассчитаны"
    return (
        f"КБЖУ: {_format_number(nutrition['kcal'])} ккал; "
        f"Б {_format_number(nutrition['protein_g'])} г; "
        f"Ж {_format_number(nutrition['fat_g'])} г; "
        f"У {_format_number(nutrition['carbs_g'])} г"
        f"<br/>Допущения: {escape(nutrition['assumptions'])}"
    )


def _render(payload: dict[str, Any], output_path: Path) -> None:
    regular_font, bold_font = _register_fonts()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=payload["title"],
        author="",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DiaryTitle",
        parent=styles["Title"],
        fontName=bold_font,
        fontSize=16,
        leading=20,
        alignment=TA_LEFT,
        textColor=colors.HexColor("#26352F"),
        spaceAfter=4 * mm,
    )
    period_style = ParagraphStyle(
        "DiaryPeriod",
        parent=styles["Normal"],
        fontName=regular_font,
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#56635E"),
        spaceAfter=5 * mm,
    )
    cell_style = ParagraphStyle(
        "DiaryCell",
        parent=styles["Normal"],
        fontName=regular_font,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#1E2723"),
    )
    header_style = ParagraphStyle(
        "DiaryHeader",
        parent=cell_style,
        fontName=bold_font,
        textColor=colors.HexColor("#26352F"),
    )

    rows = [
        [
            Paragraph("Время", header_style),
            Paragraph("Еда", header_style),
            Paragraph("Заметка клиента", header_style),
            Paragraph("КБЖУ", header_style),
        ]
    ]
    ordered_entries = sorted(payload["entries"], key=lambda entry: entry["time"])
    for entry in ordered_entries:
        rows.append(
            [
                Paragraph(escape(entry["time"]), cell_style),
                Paragraph(escape(entry["food"]), cell_style),
                Paragraph(escape(entry["client_note"]), cell_style),
                Paragraph(_nutrition_text(entry["nutrition"]), cell_style),
            ]
        )

    table = Table(
        rows,
        colWidths=[24 * mm, 50 * mm, 48 * mm, 56 * mm],
        repeatRows=1,
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E7EFEA")),
                ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#B9C8C0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    story = [
        Paragraph(escape(payload["title"]), title_style),
        Paragraph(escape(payload["period"]), period_style),
        Spacer(1, 1 * mm),
        table,
    ]
    document.build(story)


def main() -> int:
    parser = argparse.ArgumentParser(
        usage="render_diary_pdf.py INPUT_JSON OUTPUT_PDF"
    )
    parser.add_argument("input_json", type=Path)
    parser.add_argument("output_pdf", type=Path)
    args = parser.parse_args()

    try:
        payload = json.loads(args.input_json.read_text(encoding="utf-8"))
        validated_payload = _validate_payload(payload)
        _render(validated_payload, args.output_pdf)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
