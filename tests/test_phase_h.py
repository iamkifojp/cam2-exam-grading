"""Phase H: assignments, drafts, Late, partner groups, and CAM session contract."""

import json
import os
import tempfile
import time
import unicodedata
import unittest
from unittest import mock

import pymupdf as fitz

from app import create_app
from appstate import AppState
from engine import gradebook_xlsx, grading_summary, host, reports, storage, workflow
from engine.errors import UserError
from tests.helpers import make_pdf


def _rubric(rid, name, desc_top="Strong"):
    return {
        "id": rid,
        "name": name,
        "bands": [
            {"levels": "0", "descriptor": ""},
            {"levels": "1–2", "descriptor": "Limited"},
            {"levels": "3–4", "descriptor": "Adequate"},
            {"levels": "5–6", "descriptor": "Substantial"},
            {"levels": "7–8", "descriptor": desc_top},
        ],
    }


class PhaseHFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        env = mock.patch.dict(os.environ, {"CAM2_APP_DATA": os.path.join(self.root, "appdata")})
        env.start()
        self.addCleanup(env.stop)
        self.state = AppState()
        self.addCleanup(self.state.close_session)
        self.client = create_app(self.state).test_client()
        self.source = os.path.join(self.root, "submissions")
        os.makedirs(self.source)

    def post(self, url, payload=None, status=200):
        res = self.client.post(url, json=payload if payload is not None else {})
        self.assertEqual(res.status_code, status, res.get_json())
        return res.get_json()

    def create_host_task(self, folder, handoff_data, files):
        for rel, pages in files:
            path = os.path.join(self.source, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            make_pdf(path, pages=pages)
        self.post("/api/host/handoff", handoff_data)
        res = self.post("/api/session/create", {
            "exam_name": handoff_data["exam_name"],
            "paper": "A4",
            "landscape": False,
            "save_folder": folder,
            "source": {"type": "submissions", "path": self.source},
        })
        for _ in range(200):
            job = self.client.get(f"/api/job/{res['job']}").get_json()
            if job["status"] != "running":
                self.assertEqual(job["status"], "done", job.get("error"))
                return job["session"]
            time.sleep(0.02)
        self.fail("import job did not finish")


class DraftTests(PhaseHFixture):
    def test_draft_seen_no_grades_reports_and_resend(self):
        folder = os.path.join(self.root, "class", "assignments", "Essay Draft")
        handoff = {
            "format": "cam2-host",
            "version": 1,
            "task_kind": "draft",
            "exam_name": "Essay Draft",
            "class_name": "8A",
            "session_folder": folder,
            "roster": [
                {"external_id": "8A-01", "name": "Tanaka Hana"},
                {"external_id": "8A-02", "name": "Sato Ken"},
                {"external_id": "8A-03", "name": "Ito Mei"},
            ],
        }
        session_view = self.create_host_task(folder, handoff, [
            ("8A-01 essay.pdf", 2),
            ("8A-02 part1.pdf", 1),
            ("8A-02 part2.pdf", 2),
            ("8A-03 essay.pdf", 1),
        ])
        cfg = session_view["config"]
        self.assertEqual(cfg["task_kind"], "draft")
        self.assertEqual(cfg["rubrics"], [])
        self.assertEqual(cfg["questions"][0]["rubric_ids"], [])
        self.assertEqual(session_view["progress"], {"graded": 0, "total": 3, "students_done": 0, "students_total": 3})

        # Step navigation works with no marks or criteria on a draft.
        self.post("/api/step", {"step": 4})

        s1, s2, s3 = [s["id"] for s in cfg["students"]]
        # Attempting to record a grade on a draft is refused.
        err = self.post("/api/grade", {"student_id": s1, "question_id": "submission", "value": 4}, status=400)
        self.assertEqual(err["error"], "question_needs_marks_or_criterion")

        # Comment-only feedback marks student 1 as seen; note-only marks student 2 as seen.
        view = self.post("/api/overall", {"student_id": s1, "comment": "Strong opening paragraph."})["session"]
        self.assertEqual(view["progress"], {"graded": 1, "total": 3, "students_done": 1, "students_total": 3})
        view = self.post("/api/annotations", {
            "action": "add_note", "student_id": s2, "question_id": "submission",
            "page": 2, "x": 0.4, "y": 0.5, "text": "Clarify evidence.", "type": "growth",
        })["session"]
        self.assertEqual(view["progress"], {"graded": 2, "total": 3, "students_done": 2, "students_total": 3})
        self.assertEqual(view["summary"]["questions"], {})
        self.assertEqual(view["summary"]["overall"], {})
        self.assertEqual(view["summary"]["sections"], {})

        # Deleting the only note drops s2 back to unseen.
        ann_id = view["grades"]["grades"][s2]["submission"]["annotations"][0]["id"]
        view = self.post("/api/annotations", {
            "action": "delete_note", "student_id": s2, "question_id": "submission", "id": ann_id,
        })["session"]
        self.assertEqual(view["progress"]["students_done"], 1)
        # Re-add note on s2 for exports.
        self.post("/api/annotations", {
            "action": "add_note", "student_id": s2, "question_id": "submission",
            "page": 2, "x": 0.4, "y": 0.5, "text": "Clarify evidence.", "type": "growth",
        })

        # Send to CAM, reopen, edit, and re-send.
        ready1 = self.post("/api/host/ready", {"ready": True})["session"]
        self.assertTrue(ready1["config"]["host_ready_at"])
        self.post("/api/session/close")

        self.post("/api/host/handoff", handoff)
        reopened = self.post("/api/session/open", {"folder": folder})["session"]
        self.assertEqual(reopened["config"]["task_kind"], "draft")
        self.assertEqual(reopened["progress"]["students_done"], 2)
        self.post("/api/overall", {"student_id": s1, "comment": "Strong opening paragraph. Expand body."})
        ready2 = self.post("/api/host/ready", {"ready": True})["session"]
        self.assertTrue(ready2["config"]["host_ready_at"])

        # Reports & gradebook for draft: no grades/totals/stats rows, comment & notes present.
        for lang in ("en", "ja"):
            pdf_bytes = self.client.get(f"/api/report-preview/{s2}?lang={lang}").data
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                text = "".join(p.get_text() for p in doc)
                self.assertIn("Clarify evidence.", text)
                self.assertEqual(sum(len(p.get_images()) for p in doc), 1)
            book = gradebook_xlsx.build_workbook(self.state.config, self.state.grades, lang)
            ws = book.worksheets[0]
            rows = list(ws.values)
            self.assertEqual(len(rows), 4)  # header + 3 students, no stats rows
            self.assertIn("Strong opening paragraph. Expand body.", str(rows[1]))
            self.assertIn("(1) Clarify evidence.", str(rows[2]))
            book.close()


class AssignmentLatePartnerTests(PhaseHFixture):
    def _setup_two_criteria_assignment(self, extra_handoff=None):
        folder = os.path.join(self.root, "class", "assignments", "Lab Report")
        handoff = {
            "format": "cam2-host",
            "version": 1,
            "task_kind": "assignment",
            "exam_name": "Lab Report",
            "class_name": "8A",
            "session_folder": folder,
            "rubrics": [_rubric("crit_a", "Criterion A"), _rubric("crit_b", "Criterion B")],
            "roster": [
                {"external_id": "8A-01", "name": "Tanaka Hana", "late": True},
                {"external_id": "8A-02", "name": "Sato Ken"},
                {"external_id": "8A-03", "name": "Ito Mei"},
                {"external_id": "8A-04", "name": "Unmatched Paper"},
            ],
        }
        if extra_handoff:
            handoff.update(extra_handoff)
        session_view = self.create_host_task(folder, handoff, [
            ("8A-01 report.pdf", 2),
            ("8A-02 report.pdf", 2),
            ("8A-03 report.pdf", 2),
            ("mystery.pdf", 1),
        ])
        return folder, handoff, session_view

    def test_assignment_requires_criteria(self):
        folder = os.path.join(self.root, "class", "assignments", "Missing Criteria")
        handoff = {
            "format": "cam2-host", "version": 1, "task_kind": "assignment",
            "exam_name": "Missing Criteria", "class_name": "8A", "session_folder": folder,
            "rubrics": [],
            "roster": [{"external_id": "8A-01", "name": "Tanaka Hana"}],
        }
        self.create_host_task(folder, handoff, [("8A-01.pdf", 1)])
        err = self.post("/api/step", {"step": 3}, status=400)
        self.assertEqual(err["error"], "question_needs_marks_or_criterion")

    def test_late_seeded_changed_not_overwritten_and_no_page_lock(self):
        folder, handoff, view = self._setup_two_criteria_assignment({"late_ids": ["8A-03"]})
        by_ext_sid = {}
        rid_by_ext = {r["external_id"]: r["id"] for r in view["config"]["roster"]}
        for s in view["config"]["students"]:
            for ext, rid in rid_by_ext.items():
                if s["roster_id"] == rid:
                    by_ext_sid[ext] = s["id"]
        unmatched = next(s["id"] for s in view["config"]["students"] if s["roster_id"] is None)

        # Seeded from roster item `late: true` and top-level `late_ids`.
        self.assertTrue(view["grades"]["overall"][by_ext_sid["8A-01"]]["late"])
        self.assertTrue(view["grades"]["overall"][by_ext_sid["8A-03"]]["late"])
        self.assertFalse(view["grades"]["overall"].get(by_ext_sid["8A-02"], {}).get("late", False))

        # Manual match in Step 3 seeds Late for 8A-04 if marked late; test unmatched -> matched after marking 8A-04 late.
        handoff["roster"][3]["late"] = True
        self.post("/api/host/handoff", handoff)
        self.post("/api/session/close")
        reopened = self.post("/api/session/open", {"folder": folder})["session"]
        self.assertTrue(reopened["grades"]["overall"][by_ext_sid["8A-01"]]["late"])
        matched_view = self.post(f"/api/students/{unmatched}/match", {"roster_id": rid_by_ext["8A-04"]})["session"]
        self.assertTrue(matched_view["grades"]["overall"][unmatched]["late"])

        # Late flag never locks page edits before grading, and never writes into comment text.
        self.post("/api/pages/edit", {"student": by_ext_sid["8A-01"], "page": 1, "action": "turn"})
        self.assertEqual(matched_view["grades"]["overall"][unmatched].get("comment", ""), "")

        # Teacher unticks 8A-01 Late and ticks 8A-02 Late; reopening with same handoff keeps teacher decision.
        self.post("/api/overall", {"student_id": by_ext_sid["8A-01"], "late": False})
        self.post("/api/overall", {"student_id": by_ext_sid["8A-02"], "late": True})
        self.post("/api/session/close")
        self.post("/api/host/handoff", handoff)
        reopened2 = self.post("/api/session/open", {"folder": folder})["session"]
        self.assertFalse(reopened2["grades"]["overall"][by_ext_sid["8A-01"]]["late"])
        self.assertTrue(reopened2["grades"]["overall"][by_ext_sid["8A-02"]]["late"])
        self.assertEqual(reopened2["grades"]["overall"][by_ext_sid["8A-01"]].get("comment", ""), "")

    def test_partners_before_after_unlink_late_annotations_and_conflict_save(self):
        folder, handoff, view = self._setup_two_criteria_assignment()
        cfg = view["config"]
        by_name = {s["display_name"]: s["id"] for s in cfg["students"]}
        hana, ken, mei = by_name["Tanaka Hana"], by_name["Sato Ken"], by_name["Ito Mei"]

        # Reject self-link without mutating state.
        err = self.post("/api/partners/link", {"student_id": hana, "partner_id": hana}, status=400)
        self.assertEqual(err["error"], "partner_same_student")

        # 1) Link Hana & Ken before grading.
        view = self.post("/api/partners/link", {"student_id": hana, "partner_id": ken})["session"]
        self.assertEqual(len(view["config"]["partner_groups"]), 1)

        # Grade Hana on Criterion A & B -> Ken gets both; overall comment -> Ken gets it.
        self.post("/api/grade", {"student_id": hana, "question_id": "submission", "value": 6, "rubric_id": "crit_a"})
        self.post("/api/grade", {"student_id": ken, "question_id": "submission", "value": 7, "rubric_id": "crit_b"})
        view = self.post("/api/overall", {"student_id": hana, "comment": "Well structured lab."})["session"]
        self.assertEqual(view["grades"]["grades"][ken]["submission"]["levels"], {"crit_a": 6, "crit_b": 7})
        self.assertEqual(view["grades"]["overall"][ken]["comment"], "Well structured lab.")

        # Notes & highlights stay on each student's own pages; Late stays per student.
        self.post("/api/annotations", {
            "action": "add_note", "student_id": hana, "question_id": "submission",
            "page": 1, "x": 0.3, "y": 0.4, "text": "Hana graph note", "type": "strength",
        })
        view = self.post("/api/annotations", {
            "action": "add_highlight", "student_id": ken, "question_id": "submission",
            "page": 2, "x": 0.1, "y": 0.2, "w": 0.3, "h": 0.05, "colour": "blue",
        })["session"]
        self.assertEqual(len(view["grades"]["grades"][hana]["submission"].get("annotations") or []), 1)
        self.assertEqual(len(view["grades"]["grades"][ken]["submission"].get("annotations") or []), 0)
        self.assertEqual(len(view["grades"]["grades"][ken]["submission"].get("highlights") or []), 1)
        self.assertEqual(len(view["grades"]["grades"][hana]["submission"].get("highlights") or []), 0)
        self.assertTrue(view["grades"]["overall"][hana]["late"])
        self.assertFalse(view["grades"]["overall"].get(ken, {}).get("late", False))

        # 2) Mei has her own different grade & comment before joining the existing {Hana, Ken} group.
        self.post("/api/grade", {"student_id": mei, "question_id": "submission", "value": 3, "rubric_id": "crit_a"})
        self.post("/api/overall", {"student_id": mei, "comment": "Mei added data table."})
        view = self.post("/api/partners/link", {"student_id": mei, "partner_id": hana})["session"]
        # Existing group's grade stands (6, 7), and comments are combined.
        self.assertEqual(view["grades"]["grades"][mei]["submission"]["levels"], {"crit_a": 6, "crit_b": 7})
        expected_comment = "Well structured lab.\nMei added data table."
        for sid in (hana, ken, mei):
            self.assertEqual(view["grades"]["overall"][sid]["comment"], expected_comment)

        # Validation refusal (601 chars) while linked leaves neither partner mutated.
        bad = self.post("/api/overall", {"student_id": hana, "comment": "a" * 601}, status=400)
        self.assertEqual(bad["error"], "comment_too_long")
        self.assertEqual(self.state.grades["overall"][ken]["comment"], expected_comment)

        # Conflict-copy SaveError while linked keeps save_failed=True and writes once cleared.
        conflict = os.path.join(folder, "grades (1).json")
        with open(conflict, "w", encoding="utf-8") as fh:
            fh.write("{}")
        save_err = self.post("/api/overall", {"student_id": hana, "comment": "Updated group feedback."}, status=409)
        self.assertTrue(save_err["save_error"])
        self.assertTrue(self.state.save_failed)
        os.remove(conflict)
        saved_view = self.post("/api/save")["session"]
        self.assertFalse(saved_view["save_failed"])
        self.assertEqual(saved_view["grades"]["overall"][ken]["comment"], "Updated group feedback.")
        self.assertEqual(saved_view["grades"]["overall"][mei]["comment"], "Updated group feedback.")

        # 3) Unlink Mei: leaves Mei with a copy; editing Hana no longer changes Mei.
        view = self.post("/api/partners/unlink", {"student_id": mei})["session"]
        self.assertEqual(view["grades"]["grades"][mei]["submission"]["levels"], {"crit_a": 6, "crit_b": 7})
        self.assertEqual(view["grades"]["overall"][mei]["comment"], "Updated group feedback.")
        self.post("/api/grade", {"student_id": hana, "question_id": "submission", "value": 8, "rubric_id": "crit_a"})
        self.post("/api/overall", {"student_id": hana, "comment": "Hana+Ken final."})
        self.assertEqual(self.state.grades["grades"][ken]["submission"]["levels"]["crit_a"], 8)
        self.assertEqual(self.state.grades["grades"][mei]["submission"]["levels"]["crit_a"], 6)
        self.assertEqual(self.state.grades["overall"][mei]["comment"], "Updated group feedback.")

        # 4) Two students in different groups cannot link across groups.
        unmatched = next(s["id"] for s in view["config"]["students"] if s["id"] not in (hana, ken, mei))
        self.post("/api/partners/link", {"student_id": mei, "partner_id": unmatched})
        err2 = self.post("/api/partners/link", {"student_id": hana, "partner_id": mei}, status=400)
        self.assertEqual(err2["error"], "partner_already_grouped")

        # 5) Student PDF reports (with and without rubric_table) & Excel gradebook & CAM contract parity.
        hana_student = next(s for s in self.state.config["students"] if s["id"] == hana)
        for show_table in (True, False):
            workflow.set_report_options(self.state.config, {"rubric_table": show_table})
            out = os.path.join(self.root, f"hana_{show_table}.pdf")
            reports.build_student_pdf(self.state.session, self.state.config, self.state.grades, hana_student, "en", out)
            with fitz.open(out) as doc:
                text = unicodedata.normalize("NFKC", "".join(p.get_text() for p in doc))
                self.assertIn("A8", text)
                self.assertIn("B7", text)
                self.assertIn("Hana graph note", text)
                self.assertIn("Hana+Ken final.", text)
                self.assertNotIn("Final level", text)
                if show_table:
                    fills = [d.get("fill") for d in doc[0].get_drawings() if d.get("fill")]
                    self.assertTrue(any(all(abs(a - b) < 0.02 for a, b in zip(f, reports.AWARDED)) for f in fills))

        self.state.save_all()
        with open(os.path.join(folder, "cam2_session.json"), encoding="utf-8") as fh:
            disk_cfg = json.load(fh)
        with open(os.path.join(folder, "grades.json"), encoding="utf-8") as fh:
            disk_grd = json.load(fh)

        # Contract check against disk files & Excel gradebook in EN and JA.
        self.assertEqual(disk_cfg["task_kind"], "assignment")
        self.assertTrue(any(g["student_ids"] == [hana, ken] for g in disk_cfg["partner_groups"]))
        self.assertEqual(disk_grd["grades"][hana]["submission"]["levels"], {"crit_a": 8, "crit_b": 7})
        self.assertEqual(disk_grd["grades"][ken]["submission"]["levels"], {"crit_a": 8, "crit_b": 7})
        self.assertEqual(disk_grd["grades"][hana]["submission"]["annotations"][0]["text"], "Hana graph note")
        self.assertTrue(disk_grd["overall"][hana]["late"])
        self.assertEqual(disk_grd["overall"][hana]["comment"], "Hana+Ken final.")

        for lang in ("en", "ja"):
            book = gradebook_xlsx.build_workbook(disk_cfg, disk_grd, lang)
            sheet1 = list(book.worksheets[0].values)
            self.assertIn("Group 1" if lang == "en" else "グループ 1", str(sheet1))
            self.assertIn("Hana graph note", str(sheet1))
            self.assertIn("Hana+Ken final.", str(sheet1))
            self.assertIn("Yes" if lang == "en" else "はい", str(sheet1))
            book.close()

    def test_save_error_during_partner_link_keeps_flag_and_recovers(self):
        folder, _, view = self._setup_two_criteria_assignment()
        cfg = view["config"]
        hana, ken = cfg["students"][0]["id"], cfg["students"][1]["id"]
        self.post("/api/overall", {"student_id": hana, "comment": "Part A"})
        self.post("/api/overall", {"student_id": ken, "comment": "Part B"})

        conflict = os.path.join(folder, "grades (1).json")
        with open(conflict, "w", encoding="utf-8") as fh:
            fh.write("{}")
        res = self.post("/api/partners/link", {"student_id": hana, "partner_id": ken}, status=409)
        self.assertTrue(res["save_error"])
        self.assertTrue(self.state.save_failed)
        self.assertTrue(self.state.grades_failed)

        os.remove(conflict)
        recovered = self.post("/api/save")["session"]
        self.assertFalse(recovered["save_failed"])
        with open(os.path.join(folder, "grades.json"), encoding="utf-8") as fh:
            disk_grd = json.load(fh)
        self.assertEqual(disk_grd["overall"][hana]["comment"], "Part A\nPart B")
        self.assertEqual(disk_grd["overall"][ken]["comment"], "Part A\nPart B")

    def test_partner_not_answered_clear_relink_no_dup_and_long_combined(self):
        _, _, view = self._setup_two_criteria_assignment()
        hana, ken = view["config"]["students"][0]["id"], view["config"]["students"][1]["id"]
        long_a = "A" * 400
        long_b = "B" * 400
        self.post("/api/overall", {"student_id": hana, "comment": long_a})
        self.post("/api/overall", {"student_id": ken, "comment": long_b})

        # Linking preserves both 400-char comments (801 chars > 600) without dropping text.
        linked = self.post("/api/partners/link", {"student_id": hana, "partner_id": ken})["session"]
        combined = f"{long_a}\n{long_b}"
        self.assertEqual(linked["grades"]["overall"][hana]["comment"], combined)
        self.assertEqual(linked["grades"]["overall"][ken]["comment"], combined)

        # Shortening from 801 -> 700 is allowed and propagates; growing to 802 is refused.
        refused = self.post("/api/overall", {"student_id": hana, "comment": combined + "X"}, status=400)
        self.assertEqual(refused["error"], "comment_too_long")
        shortened = combined[:700]
        self.post("/api/overall", {"student_id": hana, "comment": shortened})
        self.assertEqual(self.state.grades["overall"][ken]["comment"], shortened)

        # Unlink + immediate relink does not duplicate identical comment and removes dissolved group.
        unlinked = self.post("/api/partners/unlink", {"student_id": hana})["session"]
        self.assertEqual(unlinked["config"]["partner_groups"], [])
        relinked = self.post("/api/partners/link", {"student_id": hana, "partner_id": ken})["session"]
        self.assertEqual(relinked["grades"]["overall"][hana]["comment"], shortened)

        # Not answered and Clear propagate across partners.
        self.post("/api/grade", {"student_id": hana, "question_id": "submission", "value": "not_answered"})
        self.assertEqual(self.state.grades["grades"][ken]["submission"]["levels"],
                         {"crit_a": "not_answered", "crit_b": "not_answered"})
        self.post("/api/grade", {"student_id": ken, "question_id": "submission", "value": None})
        self.assertEqual(self.state.grades["grades"][hana]["submission"]["levels"],
                         {"crit_a": None, "crit_b": None})


if __name__ == "__main__":
    unittest.main()
