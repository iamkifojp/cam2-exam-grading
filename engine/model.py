"""Shapes of the two files inside a session folder.

``cam2_session.json`` — the exam or task set-up (rarely changes once grading starts)::

    {
      "format": "cam2-session", "version": 3,
      "session_id": "<uuid>", "generation": 3, "saved_at": "...", "saved_by": "PC",
      "exam_name": "Y8 Science Midterm", "created_at": "...",
      "task_kind": "exam" | "assignment" | "draft",      # optional; absent = "exam"
      "layout": {"paper": "A4", "density": "5mm", "landscape": false},
      "mode": "marks" | "rubric" | null,                 # the starting choice only
      "rubrics":  [{"id": "r1", "name": "Criterion A",
                    "bands": [{"levels": "5–6", "descriptor": "..."}]}],
      "name_box": ["page1!A1:E2"] | [],
      "sections": [{"id": "sec1", "name": "Scientific knowledge",
                    "weight": 50, "weight_typed": false}],
      "weighted": false,
      "report_options": {"section_results": false, "overall_criteria": false,
                         "rubric_table": true, "overall_marks": true,
                         "no_images_for": ["sec1"], "all_submission_pages": false},
      "questions": [{"id": "q1", "label": "Q1", "boxes": ["page1!A4:J10"],
                     "max": 5, "rubric_ids": ["r1"], "level_caps": {"r1": 6},
                     "section_id": "sec1"}],             # level_caps optional
      "keywords": [{"label": "check calculations", "type": "growth" | "strength"}],
      "choice_groups": [{"id": "g1", "questions": ["q4", "q5", "q6"], "answer": 2,
                         "pick": "best" | "teacher"}],
      "partner_groups": [{"id": "pg1", "student_ids": ["s001", "s002"]}],   # optional
      "students": [{"id": "s001", "scan": "scans/Student_001.pdf",
                    "source": "scan0001.pdf", "pages": 4, "roster_id": null,
                    "files": [{"id": "f…", "name": "ID/submission.pdf"}],
                    "page_files": ["f…", "f…", null, "f…"]}],  # optional multi-file data
      "roster": [{"id": "n001", "name": "Tanaka Hana", "external_id": "8A-07"}],
      "host": {"name": "CAM", "class_name": "8A"},       # opened from CAM (engine/host.py)
      "host_ready_at": "..." | null,                     # results sent to the host
      "crops_of": {"q1": ["page1!A4:J10"]},              # boxes the crops were cut from
      "sliced": false,
      "resume": {"step": 1, "question_id": null, "student_id": null}
    }

``grades.json`` — written on every click while grading::

    {
      "format": "cam2-grades", "version": 3,
      "session_id": "<uuid>", "generation": 41, "saved_at": "...", "saved_by": "PC",
      "grades":  {"s001": {"q1": {"value": 4, "comment": "Good",
                                  "keywords": [], "keyword_text": "",
                                  "annotations": [{"id": "a1", "page": 1,
                                                   "x": 0.25, "y": 0.40,
                                                   "text": "...", "type": "growth"}],
                                  "highlights": [{"id": "h1", "page": 1,
                                                  "x": 0.18, "y": 0.38,
                                                  "w": 0.40, "h": 0.03,
                                                  "colour": "yellow"}]},
                           "q2": {"value": "not_answered", "comment": ""},
                           "q3": {"value": null, "comment": "",
                                  "levels": {"r2": 5, "r3": 4}}}},
      "overall": {"s001": {"comment": "", "report_total": null, "report_percent": null,
                           "final_levels": {"r1": 6},
                           "chosen": {"g1": ["q4", "q6"]},
                           "late": false}}
    }

A question grades with marks if it has a ``max``, and with rubric levels if
not; there is no separate field for it (``grading_summary.question_mode``). A
rubric question's ``level_caps`` maps criterion IDs to a highest permitted level
(a band's top); no entry means the whole rubric scale. A question with no entry
(or ``value`` null) is *ungraded*. A question assessed on several criteria
(``rubric_ids``) keeps one level per criterion in ``levels``; older sessions have
a single ``rubric_id``. Sections are optional: with none, the whole paper is one
section. A final level is typed by the teacher (never capped), and blank means
no level. ``task_kind``, ``annotations``, ``highlights``, ``partner_groups``,
``files``, and ``late`` are optional version 3 fields added across Phases C–H;
older sessions omit them or keep them empty. Ids, not labels, key everything so a
teacher can rename "Q1" without breaking crops or grades. A whole submission
uses the single item ID ``submission`` and no boxes. Each ``page_files``
entry identifies the source file for that page of the joined scan. A blank
page inserted by the teacher has no source file. ``files`` lists the source
labels in teacher-chosen order. The joined scan is the portable copy.

CAM session contract (version 3, relied on by CAM in Phase I)
------------------------------------------------------------
CAM reads ``cam2_session.json`` and ``grades.json`` directly from the session
folder (and writes no CSV; CAM never modifies CAM2's session files):

* **Handoff (``cam2-host`` v1):** ``task_kind`` (``"exam"`` | ``"assignment"`` |
  ``"draft"``), ``rubrics`` (for ``"assignment"``; preserves unique non-empty
  ``id``, ``name``, ``bands``), ``roster`` (``[{"external_id", "name",
  "late"?: bool}]`` and optional top-level ``"late_ids": [external_id, ...]``).
* **Ready signal:** ``cam2_session.json["host_ready_at"]`` (ISO timestamp or
  ``null``). CAM ingests results only when set.
* **Task kind & criteria:** ``cam2_session.json["task_kind"]`` (absent =
  ``"exam"``), ``cam2_session.json["rubrics"]``, ``questions[0]``
  (``id: "submission"``, ``rubric_ids`` empty for ``"draft"`` and criterion IDs
  for ``"assignment"``).
* **Student identity & files:** ``students[]`` joined to CAM via
  ``roster_id`` -> ``roster[].external_id``; each student carries ``files:
  [{"id", "name"}]`` in teacher-chosen order (``file_count = len(files)``,
  ``file_names = [f["name"] for f in files]``; fallback count 1 / ``[source or
  file]`` when ``files`` is absent) and ``page_files`` (per-page file ID or
  ``null`` for inserted blank pages).
* **Partner groups:** ``cam2_session.json["partner_groups"]``:
  ``[{"id": "pg...", "student_ids": ["s001", "s002"]}]`` (>= 2 students per
  group, at most 1 group per student). Grades and overall comments are stored on
  every member's own ``student_id`` in ``grades.json``; ``annotations``,
  ``highlights``, and ``late`` stay per student.
* **Assignment levels:**
  ``grades.json["grades"][sid]["submission"]["levels"][rubric_id]`` (``int``,
  ``"not_answered"``, or ``null``/absent). That level IS the student's result
  (no separate ``final_levels`` and no calculation).
* **Comment & notes (kept separate):**
  ``grades.json["overall"][sid]["comment"]`` (plain teacher comment; ``late``
  is never written into it). Numbered notes live in
  ``grades.json["grades"][sid]["submission"]["annotations"]``
  (``[{"id", "page", "x", "y", "text", "type"}]``, ordered); CAM joins note text
  with the comment when reading. ``highlights`` carry no text.
* **Late flag:** ``grades.json["overall"][sid]["late"]`` (``bool``, absent =
  ``false``).
* **Drafts:** ``task_kind == "draft"``, ``rubrics == []``, no grades; a student
  counts as seen when ``overall[sid]["comment"]`` or
  ``grades[sid]["submission"]["annotations"]`` (or question comment) is
  non-empty.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from .errors import UserError

SESSION_FORMAT = "cam2-session"
GRADES_FORMAT = "cam2-grades"
VERSION = 3

NOT_ANSWERED = "not_answered"
NAME_BOX_ID = "__name__"
SUBMISSION_ID = "submission"
DEFAULT_REPORT_OPTIONS = {"section_results": False, "overall_criteria": False,
                          "rubric_table": True, "overall_marks": True, "no_images_for": []}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_session_id() -> str:
    return uuid.uuid4().hex


def new_session(exam_name: str, session_id: str) -> dict:
    name = str(exam_name or "").strip()
    if not name:
        raise UserError("exam_name_required")
    return {
        "format": SESSION_FORMAT,
        "version": VERSION,
        "session_id": session_id,
        "generation": 0,
        "exam_name": name,
        "created_at": now_iso(),
        "layout": {"paper": "A4", "density": "5mm", "landscape": False},
        "mode": None,
        "rubrics": [],
        "name_box": [],
        "sections": [],
        "weighted": False,
        "questions": [],
        "choice_groups": [],
        "students": [],
        "roster": [],
        "sliced": False,
        "resume": {"step": 1, "question_id": None, "student_id": None},
    }


def new_grades(session_id: str) -> dict:
    return {
        "format": GRADES_FORMAT,
        "version": VERSION,
        "session_id": session_id,
        "generation": 0,
        "grades": {},
        "overall": {},
    }


def check_format(data, expected_format: str) -> dict:
    """Reject files that are not CAM2 files, or are from a newer CAM2."""
    if not isinstance(data, dict) or data.get("format") != expected_format:
        raise UserError("not_a_cam2_file", expected=expected_format)
    version = data.get("version")
    if not isinstance(version, int) or version > VERSION:
        raise UserError("file_from_newer_version", version=version)
    return data


def grades_mass(data: dict) -> int:
    """How much teacher work a grades file holds (graded cells, comments and
    final levels, none of which anything can recalculate).

    Used by the wipe guard: a save that would drop most of this is refused.
    """
    count = 0
    for per_student in (data.get("grades") or {}).values():
        for entry in (per_student or {}).values():
            if not isinstance(entry, dict):
                continue
            if entry.get("value") is not None:
                count += 1
            count += sum(1 for v in (entry.get("levels") or {}).values() if v is not None)
            if str(entry.get("comment") or "").strip():
                count += 1
            count += len(entry.get("annotations") or [])
            count += len(entry.get("highlights") or [])
    for entry in (data.get("overall") or {}).values():
        if not isinstance(entry, dict):
            continue
        if str(entry.get("comment") or "").strip():
            count += 1
        count += sum(1 for v in (entry.get("final_levels") or {}).values() if v is not None)
    return count


def upgrade_session(config: dict, grades: Optional[dict] = None) -> dict:
    """Bring a session saved by an older CAM2 up to the current version.

    A question now grades with marks if it has a ``max``, so before anything
    reads them: a rubric session's questions lose any ``max`` left from before
    the teacher chose Rubric, and a marks session's lose any criteria left the
    same way. Runs only once, because later a rubric session can gain marks.
    Final levels are now shown only with Overall criterion results on, so a
    session with any typed keeps them on.
    """
    if int(config.get("version") or 1) < 2:
        for q in config.get("questions") or []:
            if config.get("mode") == "rubric":
                q["max"] = None
            elif config.get("mode") == "marks":
                q["rubric_ids"] = []
                q.pop("rubric_id", None)
        if any(v is not None for per in ((grades or {}).get("overall") or {}).values()
               for v in ((per or {}).get("final_levels") or {}).values()):
            config["report_options"] = dict(DEFAULT_REPORT_OPTIONS, overall_criteria=True)
    config["version"] = VERSION
    return config


def task_kind(config: dict) -> str:
    return config.get("task_kind") or "exam"


def is_draft(config: dict) -> bool:
    return task_kind(config) == "draft"


def is_assignment(config: dict) -> bool:
    return task_kind(config) == "assignment"


def whole_submission(config: dict) -> bool:
    return task_kind(config) in ("assignment", "draft")
