"""The sample exam's guide tells testers what to expect, so it must be right.

Run:  python -m unittest tests.test_sample_exam
"""

import os
import tempfile
import unittest

from engine import grading_summary as gs, roster, rubrics, tables, workflow
from engine.errors import UserError
from tools import make_sample_exam as sample

RUBRIC_ID = {"A": "r1", "B": "r2", "C": "r3"}


def paper(exam: int, sections: bool = True, weighted: bool = False) -> dict:
    """The exam set up as the guide says, with no scans: only grades matter here.

    Exam 1 is the paper as designed; Exam 2 has marks on every question and the
    teacher chooses which essay counts.
    """
    config = {"students": [{"id": f"s{i}"} for i in range(len(sample.GRADES))],
              "rubrics": [rubrics.normalize_rubric({"id": f"r{i}", "name": name, "bands": [
                  {"levels": levels, "descriptor": words} for levels, words in bands]})
                  for i, (name, bands) in enumerate(sample.RUBRICS["en"], 1)],
              "questions": [],
              "choice_groups": [{"id": "g1", "questions": list(sample.CHOICE), "answer": 1,
                                 "pick": "best" if exam == 1 else "teacher"}],
              "sections": [dict(id=f"sec{x}", name="", weight=None, weight_typed=False)
                           for x in sample.SECTIONS] if sections else [],
              "weighted": weighted}
    for qid, d in sample.QUESTIONS.items():
        q = {"id": qid, "label": qid, "boxes": ["page1!A1"],
             "rubric_ids": [RUBRIC_ID[x] for x in d["criteria"]],
             "max": d["marks"] if exam == 1 else d["exam2"]}
        if exam == 1 and d.get("caps"):
            q["level_caps"] = {RUBRIC_ID[x]: cap for x, cap in d["caps"].items()}
        if sections:
            q["section_id"] = f"sec{d['section']}"
        config["questions"].append(q)
    gs.rebalance_shares(config)
    return config


def graded(config: dict, exam: int) -> dict:
    grades = {"grades": {}, "overall": {}}
    for i, plan in enumerate(sample.GRADES):
        sid = f"s{i}"
        for qid, grade in plan.items():
            if grade is sample.NA:
                gs.set_grade(config, grades, sid, qid, gs.NOT_ANSWERED)
            elif exam == 2:
                gs.set_grade(config, grades, sid, qid, sample.exam2_marks(grade))
            elif isinstance(grade, tuple):
                for letter, level in zip(sample.QUESTIONS[qid]["criteria"], grade):
                    gs.set_grade(config, grades, sid, qid, level, rubric_id=RUBRIC_ID[letter])
            else:
                gs.set_grade(config, grades, sid, qid, grade)
    if exam == 2:
        gs.set_choice(config, grades, f"s{sample.BOTH_ESSAYS}", "g1", [sample.EXAM2_PICK])
    return grades


class ThePaperTests(unittest.TestCase):
    def test_every_student_has_a_grade_for_every_question(self):
        for plan in sample.GRADES:
            self.assertEqual(list(plan), list(sample.QUESTIONS))
        for language in sample.LANGUAGES:
            self.assertEqual(len(sample.STUDENTS[language]), len(sample.GRADES))

    def test_grades_fit_their_question(self):
        for plan in sample.GRADES:
            for qid, grade in plan.items():
                d = sample.QUESTIONS[qid]
                if grade is sample.NA:
                    continue
                if d["marks"]:
                    self.assertIsInstance(grade, int, qid)
                    self.assertLessEqual(grade, d["marks"], qid)
                    continue
                self.assertEqual(len(grade), len(d["criteria"]), qid)
                for letter, level in zip(d["criteria"], grade):
                    self.assertLessEqual(level, (d.get("caps") or {}).get(letter, 8), qid)
                self.assertLessEqual(sample.exam2_marks(grade), d["exam2"], qid)

    def test_someone_is_at_q9s_ceiling(self):
        self.assertIn(6, [level for plan in sample.GRADES if plan["Q9"] for level in plan["Q9"]])

    def test_the_special_papers(self):
        both = sample.GRADES[sample.BOTH_ESSAYS]
        self.assertTrue(both["Q9"] and both["Q10"])
        self.assertTrue(any(plan["Q9"] is plan["Q10"] is sample.NA for plan in sample.GRADES))
        self.assertTrue(any(plan["Q7"] is sample.NA for plan in sample.GRADES))
        self.assertEqual(len(sample.GRADES) - 1, sample.LATE)


class ExpectedResultsTests(unittest.TestCase):
    def results(self, config, grades):
        return [gs.student_summary(config, grades, s["id"]) for s in config["students"]]

    def test_exam_1_marks_ignore_the_levels(self):
        config = paper(1, sections=False)
        for i, result in enumerate(self.results(config, graded(config, 1))):
            want = sample.expected_results(i)
            self.assertEqual(result["marks"]["max"], 30)
            self.assertEqual(result["marks"]["total"], want["exam1_marks"])
            self.assertEqual(str(result["marks"]["percent"]), str(want["exam1_percent"]))

    def test_exam_1_weighted_gives_section_c_no_share(self):
        config = paper(1, weighted=True)
        self.assertEqual([s["weight"] for s in config["sections"]], list(sample.EXAM1_SHARES) + [None])
        for i, result in enumerate(self.results(config, graded(config, 1))):
            self.assertEqual(str(result["marks"]["percent"]), str(sample.expected_results(i)["exam1_weighted"]))

    def test_exam_1_counts_the_better_essay(self):
        config = paper(1)
        grades = graded(config, 1)
        for i in range(len(sample.GRADES)):
            counted, _ungraded, _choices = gs.counted_questions(config, grades, f"s{i}")
            essays = [q for q in sample.CHOICE if q in counted and sample.GRADES[i][q] is not sample.NA]
            want = sample.expected_results(i)["exam1_essay"]
            self.assertEqual(essays, [want] if want else [], i)
        self.assertEqual(sample.expected_results(sample.BOTH_ESSAYS)["exam1_essay"], "Q9")

    def test_exam_1_ceilings_refuse_a_higher_level(self):
        config = paper(1)
        grades = {"grades": {}, "overall": {}}
        with self.assertRaises(UserError) as err:
            gs.set_grade(config, grades, "s0", "Q9", 7, rubric_id="r2")
        self.assertEqual(err.exception.code, "level_above_cap")
        with self.assertRaises(UserError):
            gs.set_grade(config, grades, "s0", "Q8", 5, rubric_id="r3")
        gs.set_grade(config, grades, "s0", "Q10", 8, rubric_id="r2")

    def test_exam_2_total(self):
        config = paper(2, sections=False)
        for i, result in enumerate(self.results(config, graded(config, 2))):
            want = sample.expected_results(i)
            self.assertEqual(result["marks"]["max"], 50)
            self.assertEqual(result["marks"]["total"], want["exam2_marks"], i)
            self.assertEqual(str(result["marks"]["percent"]), str(want["exam2_percent"]))

    def test_exam_2_waits_for_the_teachers_choice(self):
        config = paper(2, sections=False)
        grades = graded(config, 2)
        grades["overall"].pop(f"s{sample.BOTH_ESSAYS}", None)
        result = gs.student_summary(config, grades, f"s{sample.BOTH_ESSAYS}")
        self.assertEqual(result["pending"], ["g1"])

    def test_exam_2_weighted(self):
        config = paper(2, weighted=True)
        self.assertEqual([s["weight"] for s in config["sections"]], list(sample.EXAM2_SHARES))
        for i, result in enumerate(self.results(config, graded(config, 2))):
            self.assertEqual(str(result["marks"]["percent"]), str(sample.expected_results(i)["exam2_weighted"]), i)


class SampleFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def rows(self, path):
        with open(path, "rb") as fh:
            return tables.read_table(os.path.basename(path), fh.read())

    def test_the_rubric_file_can_be_uploaded(self):
        for language in sample.LANGUAGES:
            path = os.path.join(self.tmp.name, f"rubrics-{language}.xlsx")
            sample.make_rubrics(language, path)
            config = {}
            workflow.set_rubrics(config, rubrics.import_rubrics(self.rows(path)))
            self.assertEqual([r["name"] for r in config["rubrics"]], [name for name, _ in sample.RUBRICS[language]])
            self.assertEqual(rubrics.rubric_max(config["rubrics"][0]), 8)

    def test_the_class_list_finds_family_and_given_names(self):
        for language in sample.LANGUAGES:
            path = os.path.join(self.tmp.name, f"class-{language}.xlsx")
            sample.make_class_list(language, path)
            rows = self.rows(path)
            self.assertTrue(roster.guess_header(rows))
            self.assertEqual(roster.guess_name_columns(rows, True), [1, 2])
            self.assertEqual(len(roster.extract_names(rows, [1, 2], True)), len(sample.GRADES))

    def test_every_paper_draws_and_has_nine_pages(self):
        # drawing asserts that every printed and handwritten piece fits its space
        import random
        for language in sample.LANGUAGES:
            rng = random.Random(1)
            for student in range(len(sample.GRADES)):
                with sample.draw_paper(language, student, rng) as doc:
                    self.assertEqual(len(doc), sample.PAGES_PER_STUDENT)

    def test_the_guide_builds(self):
        for language in sample.LANGUAGES:
            path = os.path.join(self.tmp.name, f"guide-{language}.pdf")
            sample.make_guide(language, path)
            self.assertTrue(os.path.getsize(path) > 0)


if __name__ == "__main__":
    unittest.main()
