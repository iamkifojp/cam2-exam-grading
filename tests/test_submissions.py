"""Generated submissions only: identity, attachment order, page ownership and exports."""
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

import pymupdf as fitz
from engine import gradebook_xlsx, grading_summary, host, reports, slicer, storage, submissions, workflow
from engine.errors import UserError
from tests.helpers import make_pdf, make_image


class SubmissionFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        env = mock.patch.dict(os.environ, {"CAM2_APP_DATA": os.path.join(self.root, "appdata")})
        env.start()
        self.addCleanup(env.stop)
        self.source = os.path.join(self.root, "source")
        os.makedirs(self.source)
        self.session, self.config, self.grades = storage.create_session(os.path.join(self.root, "session"), "Submission test")
        self.handoff = host.normalize({"format": "cam2-host", "version": 1, "task_kind": "assignment",
            "exam_name": "Submission test", "session_folder": self.session.folder,
            "roster": [{"external_id": "8A-01", "name": "Tanaka Hana"},
                       {"external_id": "8A-02", "name": "Sato Ken"}]})
        host.apply_roster(self.config, self.handoff)
        host.apply_task(self.config, self.handoff)

    def pdf(self, name, pages=1, size=(595, 842)):
        path = os.path.join(self.source, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return make_pdf(path, pages=pages, size=size)

    def import_work(self):
        workflow.import_scans(self.session, self.config, {"type": "submissions", "path": self.source})


class SubmissionTests(SubmissionFixture):
    def test_unique_identity_numeric_sort_and_unopened_files(self):
        self.pdf("8A-01 part10.pdf")
        self.pdf("8A-01 part2.pdf", size=(842, 595))
        self.pdf("Sato Ken/main.pdf", pages=3)
        self.pdf("unknown1.pdf")
        self.pdf("unknown2.pdf")
        with open(os.path.join(self.source, "worksheet.docx"), "w") as f:
            f.write("synthetic unsupported file")
        self.import_work()
        students = self.config["students"]
        self.assertEqual(len(students), 4)
        hana = next(s for s in students if s["roster_id"] == "n001")
        self.assertEqual([f["name"] for f in hana["files"]], ["8A-01 part2.pdf", "8A-01 part10.pdf"])
        with fitz.open(workflow.student_scan_path(self.session, hana)) as doc:
            self.assertGreater(doc[0].rect.width, doc[0].rect.height)
        self.assertEqual(self.config["not_opened"], [{"name": "worksheet.docx", "reason": "submission_unsupported"}])
        self.assertEqual(self.config["scan_warnings"]["page_counts"], [])
        self.assertFalse(os.path.exists(self.session.path(storage.CROPS_DIR)))

    def test_duplicate_names_id_disambiguates_and_conflicts_stay_separate(self):
        roster = [{"id": "a", "external_id": "id01", "name": "Same Name"},
                  {"id": "b", "external_id": "id02", "name": "Same Name"},
                  {"id": "c", "external_id": "id03", "name": "Other Name"}]
        self.assertIsNone(submissions.match_file("Same Name.pdf", "", roster))
        self.assertEqual(submissions.match_file("id01 Same Name.pdf", "", roster), "a")
        self.assertIsNone(submissions.match_file("id01 Other Name.pdf", "", roster))
        self.assertIsNone(submissions.match_file("id01.pdf", "id02", roster))
        self.assertIsNone(submissions.match_file("Name.pdf", "", roster))
        self.assertEqual(submissions.match_file("work.pdf", "Other Name", roster), "c")

    def test_attachment_reorder_page_edit_and_work_guard(self):
        self.pdf("8A-01 attachment.pdf", size=(842, 595))
        self.pdf("8A-01 work.pdf", pages=2)
        self.import_work()
        student = self.config["students"][0]
        sid = student["id"]
        attachment = student["files"][0]["id"]
        workflow.edit_file(self.session, self.config, self.grades, sid, attachment, "later")
        self.assertEqual(student["page_files"][-1], attachment)
        workflow.edit_pages(self.session, self.config, self.grades, sid, 3, "earlier")
        self.assertEqual(student["page_files"][1], attachment)
        self.assertEqual(student["roster_id"], "n001")
        workflow.edit_file(self.session, self.config, self.grades, sid, attachment, "remove")
        self.assertEqual(student["pages"], 2)
        grading_summary.add_annotation(self.config, self.grades, sid, "submission", 1, .2, .2, "Keep this work")
        before = Path(workflow.student_scan_path(self.session, student)).read_bytes()
        with self.assertRaises(UserError):
            workflow.edit_pages(self.session, self.config, self.grades, sid, 1, "turn")
        with self.assertRaises(UserError):
            workflow.edit_file(self.session, self.config, self.grades, sid, student["files"][0]["id"], "remove")
        self.assertEqual(Path(workflow.student_scan_path(self.session, student)).read_bytes(), before)

    def test_late_paper_and_attachment_to_annotated_student(self):
        self.pdf("8A-01.pdf")
        self.import_work()
        student = self.config["students"][0]
        sid = student["id"]
        grading_summary.add_annotation(self.config, self.grades, sid, "submission", 1, .2, .2, "Keep")
        late = os.path.join(self.root, "late")
        os.makedirs(late)
        make_pdf(os.path.join(late, "8A-02.pdf"), pages=25)
        added = workflow.add_papers(self.session, self.config, {"type": "submissions", "path": late}, grades_data=self.grades)
        self.assertNotEqual(added[0], sid)
        make_pdf(os.path.join(late, "8A-01 extra.pdf"))
        with self.assertRaises(UserError):
            workflow.add_papers(self.session, self.config, {"type": "submissions", "path": late}, grades_data=self.grades)
        self.assertEqual(student["pages"], 1)
        self.assertEqual(len(self.config["students"]), 2)

    def test_mixed_pages_annotations_reports_and_portability(self):
        self.pdf("8A-01 part1.pdf")
        make_image(os.path.join(self.source, "8A-01 part2.png"), size_px=(1200, 600))
        self.import_work()
        student = self.config["students"][0]
        sid = student["id"]
        path = workflow.student_scan_path(self.session, student)
        first = slicer.whole_page_geometry(path, 1)
        second = slicer.whole_page_geometry(path, 2)
        self.assertGreater(first["parts"][0]["grid"]["rows"], first["parts"][0]["grid"]["cols"])
        self.assertGreater(second["parts"][0]["grid"]["cols"], second["parts"][0]["grid"]["rows"])
        grading_summary.add_annotation(self.config, self.grades, sid, "submission", 2, .2, .2, "Photo feedback")
        grading_summary.add_highlight(self.config, self.grades, sid, "submission", 2, .2, .3, .2, .1)
        grading_summary.set_overall_comment(self.grades, sid, "Overall feedback")
        for lang in ("en", "ja"):
            out = os.path.join(self.root, lang + ".pdf")
            reports.build_student_pdf(self.session, self.config, self.grades, student, lang, out)
            with fitz.open(out) as doc:
                self.assertEqual(sum(len(p.get_images()) for p in doc), 1)
                self.assertIn("Photo feedback", "".join(p.get_text() for p in doc))
            book = gradebook_xlsx.build_workbook(self.config, self.grades, lang)
            self.assertIn("Photo feedback", str(list(book.worksheets[0].values)))
            self.assertIn("Overall feedback", str(list(book.worksheets[0].values)))
            book.close()
        workflow.set_report_options(self.config, {"all_submission_pages": True})
        reports.build_student_pdf(self.session, self.config, self.grades, student, "en", out)
        with fitz.open(out) as doc:
            self.assertEqual(sum(len(p.get_images()) for p in doc), 2)

    def test_overall_comment_locks_replacement_and_pages(self):
        self.pdf("8A-01.pdf")
        self.import_work()
        sid = self.config["students"][0]["id"]
        grading_summary.set_overall_comment(self.grades, sid, "Do not lose")
        self.assertTrue(workflow.class_has_work(self.grades))
        with self.assertRaises(UserError):
            workflow.edit_pages(self.session, self.config, self.grades, sid, 1, "turn")


class SubmissionIntegrationTests(SubmissionFixture):
    def test_portable_saved_session_and_routes(self):
        from app import create_app
        from appstate import AppState
        self.pdf("8A-01.pdf", pages=2)
        self.import_work()
        state = AppState()
        state.set_session(self.session, self.config, self.grades)
        self.addCleanup(state.close_session)
        client = create_app(state).test_client()
        sid = self.config["students"][0]["id"]
        geometry = client.get(f"/api/geometry/submission/{sid}?page=2").get_json()
        self.assertEqual(geometry["parts"][0]["page"], 2)
        self.assertEqual(client.post('/api/step', json={'step':3}).status_code, 200)
        self.assertEqual(client.post('/api/overall', json={'student_id':sid, 'comment':'Saved feedback'}).status_code, 200)
        self.assertEqual(client.post('/api/overall', json={'student_id':sid, 'comment':'x'*601}).status_code, 400)
        self.assertEqual(state.grades['overall'][sid]['comment'], 'Saved feedback')
        self.assertEqual(client.post('/api/pages/edit', json={'student':sid,'page':1,'action':'turn'}).status_code, 400)
        state.save_all()
        moved = os.path.join(self.root, '別のパソコン')
        shutil.copytree(self.session.folder, moved)
        session2, config2, grades2 = storage.open_session(moved)
        self.assertEqual(config2['task_kind'], 'assignment')
        self.assertEqual(grades2['overall'][sid]['comment'], 'Saved feedback')
        self.assertEqual(config2['students'][0]['files'], self.config['students'][0]['files'])
        self.assertEqual(slicer.page_count(workflow.student_scan_path(session2, config2['students'][0])), 2)

    def test_added_attachment_preserves_id_and_previous_scan_until_save(self):
        self.pdf('8A-01 work.pdf', pages=2)
        self.import_work()
        student = self.config['students'][0]
        workflow.edit_pages(self.session, self.config, self.grades, student['id'], 1, 'blank_before')
        old_path = workflow.student_scan_path(self.session, student)
        sid = student['id']
        late = os.path.join(self.root, 'attachment')
        os.makedirs(late)
        make_pdf(os.path.join(late, '8A-01 attachment.pdf'), size=(842,595))
        changed = workflow.add_papers(self.session, self.config, {'type':'submissions','path':late}, grades_data=self.grades)
        self.assertEqual(changed, [sid])
        self.assertEqual(len(self.config['students']), 1)
        self.assertEqual(slicer.page_count(old_path), 3)
        new = self.config['students'][0]
        self.assertEqual(new['pages'], 4)
        self.assertEqual(new['page_files'][:3], student['page_files'])
        self.assertIsNone(new['page_files'][0])
        self.assertEqual(new['files'][-1]['name'], '8A-01 attachment.pdf')
        self.assertEqual(new['roster_id'], student['roster_id'])

    def test_exam_join_and_file_changes_reslice(self):
        self.config.pop('task_kind')
        self.config['questions'] = [{'id':'q1','label':'Q1','max':5,'boxes':['page1!A1:B2']}]
        layout = slicer.Layout("A4")
        for name, colour in [("a", (255, 0, 0)), ("b", (0, 0, 255))]:
            make_pdf(os.path.join(self.source, f"8A-01 {name}.pdf"),
                     fills={1: [(layout, 0, 0, colour)]})
        self.import_work()
        workflow.slice_session(self.session, self.config)
        student = self.config["students"][0]
        stamp = self.config["sliced_at"]
        old_crop = Path(self.session.path("crops/" + slicer.crop_file("q1", slicer.student_crop_key(student), layout)))
        old_bytes = old_crop.read_bytes()
        workflow.edit_file(self.session, self.config, self.grades, student["id"], student["files"][0]["id"], "later")
        self.assertTrue(self.config["sliced"])
        self.assertNotEqual(self.config["sliced_at"], stamp)
        self.assertEqual(student["roster_id"], "n001")
        new_crop = Path(self.session.path("crops/" + slicer.crop_file("q1", slicer.student_crop_key(student), layout)))
        self.assertEqual(old_crop.read_bytes(), old_bytes)
        self.assertNotEqual(new_crop.read_bytes(), old_bytes)

    def test_report_retains_level_without_images_or_rubric_table(self):
        self.pdf('8A-01.pdf')
        workflow.set_rubrics(self.config,[{'name':'Criterion A','bands':[{'levels':'1–4','descriptor':'Clear'}]}])
        rid=self.config['rubrics'][0]['id']
        self.config['questions'][0]['rubric_ids']=[rid]
        self.import_work()
        student=self.config['students'][0]
        grading_summary.set_grade(self.config,self.grades,student['id'],'submission',3,rubric_id=rid)
        workflow.set_report_options(self.config,{'rubric_table':False})
        out=os.path.join(self.root,'report.pdf')
        reports.build_student_pdf(self.session,self.config,self.grades,student,'en',out)
        with fitz.open(out) as doc:
            text=''.join(p.get_text() for p in doc)
            self.assertIn('A3', text)
            self.assertEqual(sum(len(p.get_images()) for p in doc),0)


if __name__ == "__main__":
    unittest.main()
