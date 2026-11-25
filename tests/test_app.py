import hashlib
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app import app, normalize_html, stitch_images


class StitchImagesTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        directory = Path(self.temp_dir.name)
        self.first_path = directory / "first.png"
        self.second_path = directory / "second.png"
        Image.new("RGB", (40, 20), "red").save(self.first_path)
        Image.new("RGB", (20, 40), "blue").save(self.second_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_horizontal_stitch_uses_common_height(self):
        result, first, second = stitch_images(
            self.first_path, self.second_path, "horizontal"
        )
        self.assertEqual(first.size, (40, 20))
        self.assertEqual(second.size, (10, 20))
        self.assertEqual(result.size, (50, 20))
        self.assertEqual(result.getpixel((0, 0)), (255, 0, 0))
        self.assertEqual(result.getpixel((49, 0)), (0, 0, 255))

    def test_vertical_stitch_uses_common_width(self):
        result, first, second = stitch_images(
            self.first_path, self.second_path, "vertical"
        )
        self.assertEqual(first.size, (20, 10))
        self.assertEqual(second.size, (20, 40))
        self.assertEqual(result.size, (20, 50))
        self.assertEqual(result.getpixel((0, 0)), (255, 0, 0))
        self.assertEqual(result.getpixel((0, 49)), (0, 0, 255))

    def test_unknown_direction_is_rejected(self):
        with self.assertRaises(ValueError):
            stitch_images(self.first_path, self.second_path, "diagonal")


class VerificationEndpointTestCase(unittest.TestCase):
    def test_verify_hash_matches_normalized_response_body(self):
        client = app.test_client()
        response = client.get("/verify")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        expected_hash = hashlib.sha256(
            normalize_html(body).encode("utf-8")
        ).hexdigest()
        self.assertRegex(response.headers["X-Verify-Hash"], r"^[0-9a-f]{64}$")
        self.assertEqual(response.headers["X-Verify-Hash"], expected_hash)
        self.assertIn("TUSUR-CHERMENIN-20261123-F6FD0817", body)


if __name__ == "__main__":
    unittest.main()
