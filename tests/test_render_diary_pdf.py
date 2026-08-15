import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from pypdf import PdfReader


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RENDERER = (
    REPOSITORY_ROOT
    / "plugins"
    / "client-workflow"
    / "skills"
    / "food-diary-analysis"
    / "scripts"
    / "render_diary_pdf.py"
)


class RenderDiaryPdfTest(unittest.TestCase):
    def test_renders_neutral_timeline_and_marks_unknown_nutrition(self):
        payload = {
            "title": "День <b>питания</b> для обсуждения",
            "period": "<b>14 августа 2026</b>",
            "entries": [
                {
                    "time": "13:40",
                    "food": "суп <b>с хлебом</b>",
                    "client_note": "<b>ела спокойно</b>",
                    "nutrition": {
                        "status": "estimated",
                        "kcal": 420,
                        "protein_g": 18,
                        "fat_g": 14,
                        "carbs_g": 55,
                        "assumptions": "<b>порция около 350 г</b>",
                    },
                },
                {
                    "time": "08:10",
                    "food": "тост с сыром",
                    "client_note": "торопилась",
                    "nutrition": {"status": "insufficient_data"},
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "diary.json"
            output_path = tmp_path / "diary.pdf"
            input_path.write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )

            result = subprocess.run(
                [sys.executable, str(RENDERER), str(input_path), str(output_path)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            text = "\n".join(page.extract_text() or "" for page in PdfReader(output_path).pages)
            normalized_text = " ".join(text.split())
            self.assertIn("08:10", text)
            self.assertIn("13:40", text)
            self.assertLess(text.index("08:10"), text.index("13:40"))
            self.assertIn("тост с сыром", text)
            self.assertIn("торопилась", text)
            self.assertIn("КБЖУ не рассчитаны", text)
            self.assertIn("<b>питания</b>", normalized_text)
            self.assertIn("<b>14 августа 2026</b>", normalized_text)
            self.assertIn("суп <b>с хлебом</b>", normalized_text)
            self.assertIn("<b>ела спокойно</b>", normalized_text)
            self.assertIn("<b>порция около 350 г</b>", normalized_text)

    def test_rejects_non_padded_time_without_creating_pdf(self):
        payload = {
            "title": "День питания для обсуждения",
            "period": "14 августа 2026",
            "entries": [
                {
                    "time": "8:10",
                    "food": "тост с сыром",
                    "client_note": "торопилась",
                    "nutrition": {"status": "insufficient_data"},
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "diary.json"
            output_path = tmp_path / "diary.pdf"
            input_path.write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )

            result = subprocess.run(
                [sys.executable, str(RENDERER), str(input_path), str(output_path)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("entry 0.time must use HH:MM", result.stderr)
            self.assertFalse(output_path.exists())

    def test_rejects_internal_analysis_field(self):
        payload = {
            "title": "День питания для обсуждения",
            "period": "14 августа 2026",
            "entries": [],
            "internal_analysis": "профессиональная гипотеза",
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            input_path = tmp_path / "diary.json"
            output_path = tmp_path / "diary.pdf"
            input_path.write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )

            result = subprocess.run(
                [sys.executable, str(RENDERER), str(input_path), str(output_path)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsupported top-level fields", result.stderr)
            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
