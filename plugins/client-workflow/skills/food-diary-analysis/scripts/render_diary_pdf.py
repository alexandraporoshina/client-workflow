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

from PIL import Image as PilImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image as PdfImage,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


TOP_LEVEL_REQUIRED_KEYS = {"title", "period", "entries"}
TOP_LEVEL_OPTIONAL_KEYS = {"photos"}
TOP_LEVEL_KEYS = TOP_LEVEL_REQUIRED_KEYS | TOP_LEVEL_OPTIONAL_KEYS
ENTRY_KEYS = {"time", "food", "client_note"}
PHOTO_KEYS = {"path", "time"}
UNKNOWN_PHOTO_TIME = "время не указано"
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


def _validate_time(value: Any, location: str) -> str:
    time_value = _require_string(value, location)
    if re.fullmatch(r"\d{2}:\d{2}", time_value) is None:
        raise ValueError(f"{location} must use HH:MM")
    try:
        datetime.strptime(time_value, "%H:%M")
    except ValueError as error:
        raise ValueError(f"{location} must use HH:MM") from error
    return time_value


def _validate_photo(photo: Any, index: int) -> None:
    location = f"photo {index}"
    if not isinstance(photo, dict):
        raise ValueError(f"{location} must be an object")
    _require_exact_keys(photo, PHOTO_KEYS, location)

    photo_path = Path(_require_string(photo["path"], f"{location}.path"))
    if not photo_path.is_file():
        raise ValueError(f"{location}.path does not exist")

    photo_time = _require_string(photo["time"], f"{location}.time")
    if photo_time != UNKNOWN_PHOTO_TIME:
        _validate_time(photo_time, f"{location}.time")

    try:
        with PilImage.open(photo_path) as image:
            image.verify()
        ImageReader(str(photo_path)).getSize()
    except Exception as error:
        raise ValueError(f"{location}.path is not a readable image") from error


def _validate_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("top-level JSON value must be an object")
    unknown = set(payload) - TOP_LEVEL_KEYS
    if unknown:
        fields = ", ".join(sorted(unknown))
        raise ValueError(f"unsupported top-level fields: {fields}")
    missing = TOP_LEVEL_REQUIRED_KEYS - set(payload)
    if missing:
        fields = ", ".join(sorted(missing))
        raise ValueError(f"missing top-level fields: {fields}")

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

        _validate_time(entry["time"], f"{entry_location}.time")
        _require_string(entry["food"], f"{entry_location}.food")
        _require_string(entry["client_note"], f"{entry_location}.client_note")

    photos = payload.get("photos", [])
    if not isinstance(photos, list):
        raise ValueError("photos must be a list")
    for index, photo in enumerate(photos):
        _validate_photo(photo, index)

    return {**payload, "photos": photos}


def _register_fonts() -> tuple[str, str]:
    for regular_path, bold_path in FONT_CANDIDATES:
        if regular_path.is_file() and bold_path.is_file():
            pdfmetrics.registerFont(TTFont("DiaryRegular", str(regular_path)))
            pdfmetrics.registerFont(TTFont("DiaryBold", str(bold_path)))
            return "DiaryRegular", "DiaryBold"
    raise RuntimeError("no Unicode-capable font found")


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
    photo_heading_style = ParagraphStyle(
        "DiaryPhotoHeading",
        parent=styles["Heading2"],
        fontName=bold_font,
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#26352F"),
        spaceBefore=5 * mm,
        spaceAfter=3 * mm,
    )
    photo_caption_style = ParagraphStyle(
        "DiaryPhotoCaption",
        parent=cell_style,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#56635E"),
    )

    rows = [
        [
            Paragraph("Время", header_style),
            Paragraph("Еда", header_style),
            Paragraph("Заметка клиента", header_style),
        ]
    ]
    ordered_entries = sorted(payload["entries"], key=lambda entry: entry["time"])
    for entry in ordered_entries:
        rows.append(
            [
                Paragraph(escape(entry["time"]), cell_style),
                Paragraph(escape(entry["food"]), cell_style),
                Paragraph(escape(entry["client_note"]), cell_style),
            ]
        )

    table = Table(
        rows,
        colWidths=[24 * mm, 64 * mm, 90 * mm],
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
    if payload["photos"]:
        story.extend(
            [
                Paragraph("Фото дня", photo_heading_style),
                _photo_gallery(payload["photos"], photo_caption_style),
            ]
        )
    document.build(story)


def _photo_gallery(
    photos: list[dict[str, Any]], caption_style: ParagraphStyle
) -> Table:
    cells: list[list[Any]] = []
    for photo in photos:
        photo_path = Path(photo["path"])
        width, height = ImageReader(str(photo_path)).getSize()
        scale = min((80 * mm) / width, (64 * mm) / height)
        image = PdfImage(str(photo_path), width=width * scale, height=height * scale)
        image.hAlign = "CENTER"
        if photo["time"] == UNKNOWN_PHOTO_TIME:
            caption = "Время: не указано"
        else:
            caption = f"Время: {escape(photo['time'])}"
        cells.append([image, Spacer(1, 2 * mm), Paragraph(caption, caption_style)])

    rows: list[list[Any]] = []
    for index in range(0, len(cells), 2):
        row = cells[index : index + 2]
        if len(row) == 1:
            row.append("")
        rows.append(row)

    gallery = Table(rows, colWidths=[85 * mm, 85 * mm], hAlign="LEFT")
    gallery.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * mm),
            ]
        )
    )
    return gallery


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
