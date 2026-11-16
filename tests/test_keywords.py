"""Quick comments: the per-exam list of notes to place while grading.

Run:  python -m unittest tests.test_keywords
"""

import unittest

from engine import keywords, model
from engine.errors import UserError


def exam():
    config = {"mode": "marks", "students": [{"id": "s1"}],
              "questions": [{"id": "q1", "label": "Q1", "max": 5}], "choice_groups": []}
    return config, model.new_grades("x")


class ListTests(unittest.TestCase):
    def test_default_list_has_four_items_and_follows_the_language(self):
        config, _ = exam()
        en = keywords.keyword_list(config, "en")
        self.assertEqual(len(en), 4)
        self.assertEqual(en[0], {"label": "Well explained.", "type": "strength"})
        self.assertEqual(en[1], {"label": "More explanation needed.", "type": "growth"})
        self.assertEqual(en[2], {"label": "Incomplete answer.", "type": "growth"})
        self.assertEqual(en[3], {"label": "Hard to read.", "type": "growth"})
        ja = keywords.keyword_list(config, "ja")
        self.assertEqual(len(ja), 4)
        self.assertEqual(ja[0]["type"], "strength")
        self.assertEqual(ja[3]["type"], "growth")

    def test_set_list_cleans_up_and_allows_optional_type(self):
        config, _ = exam()
        keywords.set_list(config, [
            {"label": "  clear   working ", "type": "strength"},
            {"label": "Clear working"},
            {"label": ""},
            "junk",
            {"label": "units missing", "type": "growth"},
            {"label": "plain note", "type": None},
        ])
        self.assertEqual(config["keywords"], [
            {"label": "clear working", "type": "strength"},
            {"label": "units missing", "type": "growth"},
            {"label": "plain note", "type": None},
        ])
        keywords.set_list(config, [])
        self.assertEqual(keywords.keyword_list(config, "en"), [])     # an emptied list stays empty

    def test_limits_enforce_8_items_and_120_chars_while_keeping_longer_legacy_lists(self):
        config, _ = exam()
        items8 = [{"label": f"Item {i}", "type": "growth"} for i in range(8)]
        keywords.set_list(config, items8)
        with self.assertRaises(UserError) as ctx:
            keywords.set_list(config, items8 + [{"label": "Item 9", "type": "growth"}])
        self.assertEqual(ctx.exception.code, "too_many_keywords")

        with self.assertRaises(UserError) as ctx2:
            keywords.set_list(config, [{"label": "x" * 121, "type": "growth"}])
        self.assertEqual(ctx2.exception.code, "note_too_long")

        # Legacy session with 10 items and a 150-char label: kept on read and can shorten, not grow
        legacy = [{"label": f"Old {i}", "type": "growth"} for i in range(9)] + [{"label": "z" * 150, "type": None}]
        config["keywords"] = legacy
        self.assertEqual(len(keywords.keyword_list(config, "en")), 10)
        self.assertEqual(len(keywords.keyword_list(config, "en")[-1]["label"]), 150)

        # Keeping the 10 items or shortening to 9 works; growing to 11 is refused
        keywords.set_list(config, legacy)
        keywords.set_list(config, legacy[:9])
        with self.assertRaises(UserError) as ctx3:
            keywords.set_list(config, legacy[:9] + [{"label": "New 10", "type": None}])
        self.assertEqual(ctx3.exception.code, "too_many_keywords")


if __name__ == "__main__":
    unittest.main()
