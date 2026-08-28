import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SiteContractTests(unittest.TestCase):
    def test_home_uses_only_formal_pages_and_full_text(self):
        source = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("where: 'archive_page', true", source)
        self.assertIn("archive_page.content | strip_html | strip_newlines", source)
        self.assertNotIn("/producthunt/2026/08/2026-08-25.html", source)

    def test_partial_product_hunt_page_is_not_published(self):
        source = (ROOT / "producthunt/2026/08/2026-08-25.md").read_text(encoding="utf-8")
        self.assertIn("archive_page: false", source)
        self.assertIn("published: false", source)

    def test_current_formal_dailies_link_evidence(self):
        for relative in (
            "hackernews/2026/08/2026-08-28.md",
            "twitter/2026/08/2026-08-27.md",
            "reddit/2026/08/2026-08-27.md",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("archive_page: true", source, relative)
            self.assertIn("溯源", source, relative)
            self.assertIn(".json", source, relative)


if __name__ == "__main__":
    unittest.main()
