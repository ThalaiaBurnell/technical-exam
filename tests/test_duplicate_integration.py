
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "consumer")
)

from consumer import process_article

class TestDuplicateIntegration(unittest.TestCase):

    @patch("consumer.scrape_article")
    def test_duplicate_content(self, mock_scrape):
        mock_scrape.return_value = (
            "Sample Technology Article",
            " ".join(["This is a sample article about technology."] * 10)
        )

        collection = MagicMock()

        collection.find_one.return_value = {"id": "001"}

        task = {
            "id": "TEST-002",
            "url": "https://example.com/article",
            "source": "Test Source",
            "category": "technology",
            "priority": "medium"
        }

        process_article(task, collection)

        saved = collection.update_one.call_args.args[1]["$set"]

        self.assertEqual(
            saved["integrity"]["quality_status"],
            "flagged"
        )

        self.assertEqual(
            saved["integrity"]["duplicate_of"],
            "001"
        )

        self.assertEqual(
            saved["status"],
            "success"
        )


if __name__ == "__main__":
    unittest.main()
