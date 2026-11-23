
import sys
import unittest
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "consumer")
)

from integrity import validate_content


class TestArticleIntegrity(unittest.TestCase):

    def test_valid_article(self):
        body = " ".join(
            ["This is a meaningful news article sentence."]
            * 10
        )

        result = validate_content(
            "Technology News",
            body
        )

        self.assertEqual(
            result["quality_status"],
            "accepted"
        )

    def test_short_article(self):
        result = validate_content(
            "Short News",
            "This article contains only a few words."
        )

        self.assertEqual(
            result["quality_status"],
            "flagged"
        )

    def test_access_denied(self):
        result = validate_content(
            "Access Denied",
            "Please log in to read this article."
        )

        self.assertEqual(
            result["quality_status"],
            "flagged"
        )

    def test_duplicate_fingerprint(self):
        body = (
            "Python is widely used for automation "
            "and data processing."
        )

        first = validate_content("Article A", body)
        second = validate_content("Article B", body)

        self.assertEqual(
            first["content_fingerprint"],
            second["content_fingerprint"]
        )


if __name__ == "__main__":
    unittest.main()
