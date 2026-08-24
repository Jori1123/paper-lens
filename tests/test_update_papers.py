import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "update_papers.py"
SPEC = importlib.util.spec_from_file_location("update_papers", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class UpdatePapersTest(unittest.TestCase):
    def test_reconstruct_abstract_orders_inverted_index(self):
        index = {"world": [1], "Hello": [0], "again": [2]}
        self.assertEqual(MODULE.reconstruct_abstract(index), "Hello world again")
        self.assertEqual(MODULE.reconstruct_abstract(None), "")

    def test_popularity_is_bounded_and_rewards_citations(self):
        low = MODULE.popularity(2, 2025, 2026)
        high = MODULE.popularity(10000, 2025, 2026)
        self.assertGreater(high, low)
        self.assertGreaterEqual(low, 0)
        self.assertLessEqual(high, 100)

    def test_merge_preserves_translation_and_refreshes_metrics(self):
        existing = [{
            "id": "seed",
            "doi": "10.1000/example",
            "title": "Old",
            "title_zh": "人工译名",
            "abstract_zh": "人工摘要",
            "citations": 2,
            "year": 2024,
        }]
        incoming = [{
            "id": "openalex-W1",
            "doi": "https://doi.org/10.1000/EXAMPLE",
            "title": "Current",
            "title_zh": "",
            "abstract_zh": "",
            "citations": 20,
            "year": 2024,
        }]
        merged = MODULE.merge_papers(existing, incoming)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["title"], "Current")
        self.assertEqual(merged[0]["title_zh"], "人工译名")
        self.assertEqual(merged[0]["abstract_zh"], "人工摘要")
        self.assertEqual(merged[0]["citations"], 20)

    def test_work_conversion(self):
        work = {
            "id": "https://openalex.org/W123",
            "doi": "https://doi.org/10.1000/test",
            "display_name": "A Paper",
            "publication_year": 2025,
            "authorships": [{"author": {"display_name": "Ada"}}],
            "primary_location": {"source": {"display_name": "Journal"}},
            "best_oa_location": {"landing_page_url": "https://example.test/paper"},
            "open_access": {"is_oa": True},
            "cited_by_count": 10,
            "abstract_inverted_index": {"A": [0], "test": [1]},
            "primary_topic": {"field": {"display_name": "Artificial Intelligence"}},
            "topics": [{"display_name": "Robotics"}],
        }
        paper = MODULE.work_to_paper(work, 2026)
        self.assertEqual(paper["id"], "openalex-W123")
        self.assertEqual(paper["field"], "人工智能")
        self.assertEqual(paper["abstract"], "A test")
        self.assertTrue(paper["open_access"])


if __name__ == "__main__":
    unittest.main()
