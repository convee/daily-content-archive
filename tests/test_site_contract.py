import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SiteContractTests(unittest.TestCase):
    def test_home_separates_formal_pages_and_evidence_snapshots(self):
        source = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("where: 'archive_page', true", source)
        self.assertIn("where: 'evidence_page', true", source)
        self.assertIn("entry_page.content | strip_html | strip_newlines", source)
        self.assertIn("{% if entry_page.archive_page %}日报{% else %}快照{% endif %}", source)

    def test_product_hunt_snapshot_is_visible_but_not_formal(self):
        source = (ROOT / "producthunt/2026/08/2026-08-25.md").read_text(encoding="utf-8")
        self.assertIn("archive_page: false", source)
        self.assertIn("evidence_page: true", source)
        self.assertNotIn("Cloudflare", source)

    def test_each_partial_platform_has_multiple_visible_history_entries(self):
        for platform in ("twitter", "reddit", "producthunt"):
            pages = list((ROOT / platform / "2026" / "08").glob("*.md"))
            visible = [page for page in pages if "archive_page: true" in page.read_text(encoding="utf-8") or "evidence_page: true" in page.read_text(encoding="utf-8")]
            self.assertGreaterEqual(len(visible), 2, platform)

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
