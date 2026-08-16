import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from pypdf import PdfReader
from PIL import Image


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
    def run_renderer(self, payload, tmp_path):
        input_path = tmp_path / "diary.json"
        output_path = tmp_path / "diary.pdf"
        input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(RENDERER), str(input_path), str(output_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        return result, output_path

    @staticmethod
    def extracted_text(output_path):
        return "\n".join(page.extract_text() or "" for page in PdfReader(output_path).pages)

    def test_renders_neutral_client_timeline_without_nutrition(self):
        payload = {
            "title": "День <b>питания</b> для обсуждения",
            "period": "<b>14 августа 2026</b>",
            "entries": [
                {
                    "time": "13:40",
                    "food": "суп <b>с хлебом</b>",
                    "client_note": "<b>ела спокойно</b>",
                },
                {
                    "time": "08:10",
                    "food": "тост с сыром",
                    "client_note": "торопилась",
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            result, output_path = self.run_renderer(payload, tmp_path)

            self.assertEqual(result.returncode, 0, result.stderr)
            text = self.extracted_text(output_path)
            normalized_text = " ".join(text.split())
            self.assertIn("08:10", text)
            self.assertIn("13:40", text)
            self.assertLess(text.index("08:10"), text.index("13:40"))
            self.assertIn("тост с сыром", text)
            self.assertIn("торопилась", text)
            self.assertNotIn("КБЖУ", text)
            self.assertNotIn("Допущения", text)
            self.assertIn("<b>питания</b>", normalized_text)
            self.assertIn("<b>14 августа 2026</b>", normalized_text)
            self.assertIn("суп <b>с хлебом</b>", normalized_text)
            self.assertIn("<b>ела спокойно</b>", normalized_text)

    def test_rejects_non_padded_time_without_creating_pdf(self):
        payload = {
            "title": "День питания для обсуждения",
            "period": "14 августа 2026",
            "entries": [
                {
                    "time": "8:10",
                    "food": "тост с сыром",
                    "client_note": "торопилась",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            result, output_path = self.run_renderer(payload, tmp_path)

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
            result, output_path = self.run_renderer(payload, tmp_path)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsupported top-level fields", result.stderr)
            self.assertFalse(output_path.exists())

    def test_renders_explicit_diary_photo_with_its_time(self):
        payload = {
            "title": "День питания для обсуждения",
            "period": "14 августа 2026",
            "entries": [],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            photo_path = tmp_path / "breakfast.png"
            Image.new("RGB", (40, 60), "#d5ad7f").save(photo_path)
            payload["photos"] = [{"path": str(photo_path), "time": "07:30"}]

            result, output_path = self.run_renderer(payload, tmp_path)

            self.assertEqual(result.returncode, 0, result.stderr)
            text = self.extracted_text(output_path)
            self.assertIn("Фото дня", text)
            self.assertIn("07:30", text)
            self.assertNotIn("КБЖУ", text)

    def test_rejects_nutrition_from_client_pdf_without_creating_pdf(self):
        payload = {
            "title": "День питания для обсуждения",
            "period": "14 августа 2026",
            "entries": [
                {
                    "time": "08:10",
                    "food": "тост с сыром",
                    "client_note": "торопилась",
                    "nutrition": {"status": "estimated"},
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            result, output_path = self.run_renderer(payload, tmp_path)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsupported entry fields: nutrition", result.stderr)
            self.assertFalse(output_path.exists())

    def test_rejects_missing_explicit_diary_photo_without_creating_pdf(self):
        payload = {
            "title": "День питания для обсуждения",
            "period": "14 августа 2026",
            "entries": [],
            "photos": [{"path": "missing.jpg", "time": "время не указано"}],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            result, output_path = self.run_renderer(payload, tmp_path)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("photo 0.path does not exist", result.stderr)
            self.assertFalse(output_path.exists())

    def test_rejects_corrupt_explicit_diary_photo_before_creating_pdf(self):
        payload = {
            "title": "День питания для обсуждения",
            "period": "14 августа 2026",
            "entries": [],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            photo_path = tmp_path / "corrupt.png"
            photo_path.write_bytes(
                base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
                    "AAAADUlEQVQIHWP4z8DwHwAFgAI/ScL3QgAAAABJRU5ErkJggg=="
                )
            )
            payload["photos"] = [{"path": str(photo_path), "time": "07:30"}]

            result, output_path = self.run_renderer(payload, tmp_path)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("photo 0.path is not a readable image", result.stderr)
            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
