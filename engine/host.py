"""Running CAM2 from another app (a *host*, such as CAM).

The host starts CAM2 with ``launcher.py --host <handoff.json>``. The handoff
names one exam and where its session lives, and brings the class list::

    {"format": "cam2-host", "version": 1, "host": "CAM",
     "exam_name": "Y8 Science Midterm", "class_name": "8A",
     "session_folder": "D:/OneDrive/CAM/8A/exams/Y8 Science Midterm",
     "roster": [{"external_id": "8A-07", "name": "Tanaka Hana"}]}

CAM2 then opens that session (or starts it in that folder), uses the host's
class list for matching names and keeps each entry's ``external_id``, so the
host can file results without matching names again. When grading is done the
teacher clicks *Send to CAM*, which stamps ``host_ready_at`` in
``cam2_session.json``; the host only reads the session folder.

An optional ``task_kind`` selects ``exam`` (default), ``assignment`` or
``draft`` when creating the session. For an assignment the handoff can
include ``rubrics`` in the same form as CAM2 rubric setup. Roster entries may
carry an optional ``late: true`` flag (or the handoff may list ``late_ids`` of
``external_id``s) to seed Late ticks for matched students without overwriting
any teacher decision. The task kind is kept when that session opens again.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from . import model, workflow
from .errors import UserError

FORMAT = "cam2-host"
VERSION = 1
MAX_ROSTER = 500


def normalize(data) -> dict:
    """Check a handoff and keep only what CAM2 uses."""
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise UserError("host_handoff_invalid")
    version = data.get("version")
    if not isinstance(version, int) or version > VERSION:
        raise UserError("file_from_newer_version", version=version)
    exam = " ".join(str(data.get("exam_name") or "").split())[:80]
    folder = str(data.get("session_folder") or "").strip()
    if not exam or not folder or not os.path.isabs(folder):
        raise UserError("host_handoff_invalid")
    late_ids = {str(x).strip() for x in (data.get("late_ids") or []) if str(x or "").strip()}
    roster, seen = [], set()
    for entry in data.get("roster") or []:
        if not isinstance(entry, dict):
            continue
        ext = str(entry.get("external_id") or "").strip()
        name = " ".join(str(entry.get("name") or "").split())[:100]
        if ext and name and ext not in seen:
            seen.add(ext)
            item = {"external_id": ext, "name": name}
            if bool(entry.get("late")) or ext in late_ids:
                item["late"] = True
            roster.append(item)
    kind = data.get("task_kind", "exam")
    if kind not in ("exam", "assignment", "draft"):
        raise UserError("host_handoff_invalid")
    return {"task_kind": kind, "rubrics": data.get("rubrics") or [], "host": " ".join(str(data.get("host") or "CAM").split())[:40] or "CAM",
            "exam_name": exam,
            "class_name": " ".join(str(data.get("class_name") or "").split())[:80],
            "session_folder": os.path.normpath(folder),
            "roster": roster[:MAX_ROSTER]}


def load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        raise UserError("host_handoff_invalid")
    return normalize(data)


def same_folder(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def is_host_session(handoff: Optional[dict], folder: str) -> bool:
    return bool(handoff) and same_folder(handoff["session_folder"], folder)


def apply_roster(config: dict, handoff: dict) -> dict:
    """Use the host's class list. An entry keeps its id while its
    ``external_id`` stays, so papers stay matched when a name is corrected."""
    by_ext = {r.get("external_id"): r["id"] for r in config.get("roster") or [] if r.get("external_id")}
    used = set(by_ext.values())
    entries, n = [], 0
    for person in handoff["roster"]:
        rid = by_ext.get(person["external_id"])
        if rid is None:
            n += 1
            while f"n{n:03d}" in used:
                n += 1
            rid = f"n{n:03d}"
            used.add(rid)
        item = {"id": rid, "name": person["name"], "external_id": person["external_id"]}
        if person.get("late"):
            item["late"] = True
        entries.append(item)
    workflow.set_roster(config, entries, keep_existing=True)
    config["host"] = {"name": handoff["host"], "class_name": handoff["class_name"]}
    return config


def apply_late_defaults(config: dict, grades_data: Optional[dict]) -> bool:
    """Seed ``late = True`` for students whose host roster entry is marked late.

    Only populates students without an explicit ``late`` key yet, so a teacher
    clearing CAM's Late flag persists across reopens. Returns True if changed.
    """
    if grades_data is None:
        return False
    late_rids = {r["id"] for r in config.get("roster") or [] if r.get("late")}
    if not late_rids:
        return False
    changed = False
    for s in config.get("students") or []:
        if s.get("roster_id") in late_rids:
            entry = grades_data.setdefault("overall", {}).setdefault(s["id"], {})
            if "late" not in entry:
                entry["late"] = True
                changed = True
    return changed


def set_ready(config: dict, ready: bool) -> dict:
    """Grading finished (or not): the host reads results only when stamped."""
    config["host_ready_at"] = model.now_iso() if ready else None
    return config


def apply_task(config, handoff):
    """Set task kind only when a CAM session is first created."""
    config["task_kind"] = handoff.get("task_kind", "exam")
    if model.whole_submission(config):
        criteria = handoff.get("rubrics") if model.is_assignment(config) else None
        workflow.set_rubrics(config, criteria or [])
        config["questions"] = [{"id": model.SUBMISSION_ID, "label": config["exam_name"],
                                "boxes": [], "max": None,
                                "rubric_ids": [r["id"] for r in config["rubrics"]]}]
        config["mode"] = None if model.is_draft(config) else "rubric"
