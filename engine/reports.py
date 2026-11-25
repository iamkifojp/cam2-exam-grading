"""One PDF report per student, in English or Japanese.

Each report has, in this order:
  * a header: exam name, date and student name;
  * the results: the overall marks and percentage, with one row per section
    above them if Section results is on;
  * the rubric tables, once and only for criteria this exam uses, each beside a
    box with the final level the teacher decided, the criterion's marks and its
    grades. The final level's band is shaded;
  * the overall comment;
  * the questions, grouped by section: the label, the answer image and, beside
    it (never on top of the student's writing), the grade, followed only by the
    teacher's comment. With images off for a section, a grid of grades instead.

What the teacher filled in prints, and what is blank does not. The results shown
are the *reported* ones: a teacher's override replaces the calculated total or
percentage here (and only here; see grading_summary).

Layout is drawn with PyMuPDF. Text goes through ``insert_htmlbox`` so long
Japanese or English text wraps properly; Japanese uses MuPDF's built-in CJK
font, and fonts are subset before saving, so a report stays small enough to
email (tens of kB plus the answer images). Tables are drawn cell by cell,
because MuPDF's HTML ignores table column widths.
"""

from __future__ import annotations

import html
import io
import os
import re
import tempfile
from datetime import date
from typing import Callable, List, Optional

import pymupdf as fitz
from PIL import Image

from . import grading_summary, i18n, model, rubrics, slicer, storage
from .errors import UserError

PAGE = fitz.paper_rect("a4")
MARGIN = 42
CONTENT_W = PAGE.width - 2 * MARGIN
FOOTER_H = 24
IMAGE_MAX_H = 330           # points; taller answers are scaled down
LABEL_W = 44                # question label column, left of the answer
GRADE_W = 76                # grade column, right of the answer
IMAGE_MAX_W = CONTENT_W - LABEL_W - GRADE_W
IMAGE_MAX_PX = 1400         # answer images are resized to this width before embedding
JPEG_QUALITY = 82
GAP = 10
PAD = 3                     # inside a table cell
SIDE_W = 92                 # the box beside a rubric table
LEVELS_W = 44               # the levels column of a rubric table
GRID_COLUMNS = 5            # grades per row when a section has no images
GRID_ROW_H = 20
PAGE_ROOM = PAGE.height - 2 * MARGIN - FOOTER_H

INK = (0.106, 0.133, 0.188)
MUTED = (0.42, 0.45, 0.52)
FRAME = (0.80, 0.82, 0.86)
AWARDED = (0.87, 0.95, 0.90)
HEADING = (0.93, 0.94, 0.96)

CSS = """
* { font-family: sans-serif; color: #1b2230; font-size: 10pt; line-height: 1.4; }
h1 { font-size: 17pt; margin: 0; }
h2 { font-size: 13pt; margin: 0; }
.big { font-size: 15pt; font-weight: bold; }
.muted { color: #6b7385; font-size: 9pt; }
.label { color: #6b7385; font-size: 8.5pt; }
.note-tag { font-size: 8.5pt; font-weight: bold; }
.note-tag.strength { color: #14734a; }
.note-tag.growth { color: #9a5200; }
p { margin: 0 0 3pt 0; }
"""
GRADE_CSS = CSS + """
.grade { font-size: 18pt; font-weight: bold; color: #14734a; line-height: 1.1; }
.of { font-size: 10pt; color: #6b7385; }
"""
TABLE_CSS = CSS + " * { font-size: 9.5pt; line-height: 1.3; } p { margin: 0; }"


def _e(text) -> str:
    return html.escape(str(text if text is not None else ""))


class _Writer:
    """A cursor that flows blocks down A4 pages, starting new pages as needed."""

    def __init__(self, doc, footer: str):
        self.doc = doc
        self.footer = footer
        self.page = None
        self.y = 0.0
        self.new_page()

    @property
    def bottom(self) -> float:
        return PAGE.height - MARGIN - FOOTER_H

    def new_page(self):
        self.page = self.doc.new_page(width=PAGE.width, height=PAGE.height)
        self.y = MARGIN

    def html(self, text: str, width: float = CONTENT_W, x: float = MARGIN, gap: float = GAP) -> float:
        """Write wrapped HTML at the cursor; returns the height used."""
        for attempt in range(2):
            rect = fitz.Rect(x, self.y, x + width, self.bottom)
            spare, _ = self.page.insert_htmlbox(rect, text, css=CSS, scale_low=1)
            if spare >= 0:
                used = rect.height - spare
                self.y += used + gap
                return used
            if attempt == 0 and self.y > MARGIN + 1:
                self.new_page()                       # try again on a fresh page
        # Longer than a whole page: let it shrink to fit one.
        rect = fitz.Rect(x, self.y, x + width, self.bottom)
        self.page.insert_htmlbox(rect, text, css=CSS, scale_low=0)
        self.y = self.bottom + gap
        return rect.height

    def at(self, rect: fitz.Rect, text: str, css: str = CSS, shrink: bool = False):
        """Write HTML in a fixed box beside the flow; the cursor does not move."""
        self.page.insert_htmlbox(rect, text, css=css, scale_low=0 if shrink else 1)

    def ensure(self, height: float):
        if self.y + height > self.bottom and self.y > MARGIN + 1:
            self.new_page()

    def finish(self):
        total = self.doc.page_count
        for i, page in enumerate(self.doc, 1):
            rect = fitz.Rect(MARGIN, PAGE.height - MARGIN - 12, PAGE.width - MARGIN, PAGE.height - MARGIN + 6)
            page.insert_htmlbox(rect, f"<p class='muted'>{_e(self.footer)} · {i} / {total}</p>",
                                css=CSS + " p { text-align: right; }")


# --- Images --------------------------------------------------------------------------

def _encode_jpeg(im: Image.Image):
    """(jpeg bytes, width px, height px) of a PIL image, resized for embedding."""
    rgb = im.convert("RGB") if im.mode != "RGB" else im
    resized = None
    try:
        target = rgb
        if rgb.width > IMAGE_MAX_PX:
            ratio = IMAGE_MAX_PX / rgb.width
            resized = rgb.resize((IMAGE_MAX_PX, max(1, int(rgb.height * ratio))), Image.LANCZOS)
            target = resized
        with io.BytesIO() as buf:
            target.save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True)
            return buf.getvalue(), target.width, target.height
    finally:
        if resized is not None:
            resized.close()
        if rgb is not im:
            rgb.close()


def _jpeg(path: str):
    """(jpeg bytes, width px, height px) of an image, resized for embedding."""
    with Image.open(path) as im:
        return _encode_jpeg(im)


def _fit(w_px: int, h_px: int, max_w: float, max_h: float):
    scale = min(max_w / w_px, max_h / h_px)
    return w_px * scale, h_px * scale


# --- Tables --------------------------------------------------------------------------

def _height_of(text: str, width: float, css: str = TABLE_CSS) -> float:
    with fitz.open() as scratch:
        page = scratch.new_page(width=width + 20, height=PAGE.height * 2)
        spare, _ = page.insert_htmlbox(fitz.Rect(0, 0, width, PAGE.height * 2), text, css=css, scale_low=1)
    return PAGE.height * 2 - spare


def _cell(w: _Writer, x: float, width: float, height: float, text: str, fill=None) -> None:
    w.page.draw_rect(fitz.Rect(x, w.y, x + width, w.y + height), color=FRAME, fill=fill, width=0.6)
    w.at(fitz.Rect(x + PAD, w.y + PAD, x + width - PAD, w.y + height), text, css=TABLE_CSS, shrink=True)


def _row_height(row: List[str], widths: List[float]) -> float:
    tallest = max(_height_of(text, widths[j] - 2 * PAD) for j, text in enumerate(row))
    return min(tallest + 2 * PAD, PAGE_ROOM)      # a row longer than a page shrinks to fit one


def _table(w: _Writer, widths: List[float], rows: List[List[str]], fills: Optional[list] = None) -> None:
    for i, row in enumerate(rows):
        height = _row_height(row, widths)
        w.ensure(height)
        x = MARGIN
        for j, text in enumerate(row):
            _cell(w, x, widths[j], height, text, fills[i] if fills else None)
            x += widths[j]
        w.y += height


# --- Words -----------------------------------------------------------------------------

def _value_text(value, out_of, language: str) -> str:
    if value is None:
        return i18n.t("report.not_graded", language)
    if value == model.NOT_ANSWERED:
        return i18n.t("grade.not_answered", language)
    return f"{value} / {out_of}"


def _grades(config: dict, grades: dict, student_id: str, question: dict) -> List[tuple]:
    """(rubric or None, value, out of) for each grade a question has."""
    values = grading_summary.question_values(config, grades, student_id, question)
    if None in values:
        return [(None, values[None], question.get("max"))]
    by_id = {r["id"]: r for r in config.get("rubrics") or []}
    return [(by_id[rid], value, rubrics.rubric_max(by_id[rid])) for rid, value in values.items()]


def _criterion_short(rubric: dict) -> str:
    """The criterion in a grade: its last letter when its name ends in a single
    letter (``Criterion B`` or ``基準B`` gives ``B``), otherwise its whole name."""
    name = str(rubric["name"]).strip()
    letter = re.search(r"(?:^|[^A-Za-z])([A-Za-z])$", name)
    return letter.group(1) if letter else name


def _level_text(rubric: dict, value, language: str) -> str:
    """One level with its criterion: ``B5``, ``Knowledge 5`` or ``B Not answered``."""
    short = _criterion_short(rubric)
    if isinstance(value, int):
        return f"{short}{value}" if len(short) == 1 else f"{short} {value}"
    return f"{short} {_value_text(value, None, language)}"


def _nothing_given(parts: List[tuple]) -> bool:
    """Every grade is blank, or every one is *Not answered*: said once, with no criterion."""
    return bool(parts) and (all(value == model.NOT_ANSWERED for _, value, _ in parts)
                            or all(value is None for _, value, _ in parts))


def _grade_text(parts: List[tuple], language: str) -> str:
    """One question's grade in a line: ``6 / 10``, or ``B5 C5``."""
    if _nothing_given(parts):
        return _value_text(parts[0][1], None, language)
    return " ".join(_value_text(value, top, language) if rubric is None
                    else _level_text(rubric, value, language) for rubric, value, top in parts)


def _grade_html(parts: List[tuple], language: str) -> str:
    """The grade beside an answer: marks over the maximum, or each level with its criterion."""
    if _nothing_given(parts):
        return f"<p class='muted'>{_e(_value_text(parts[0][1], None, language))}</p>"
    out = []
    for rubric, value, top in parts:
        if rubric is None:
            if isinstance(value, int):
                out.append(f"<p class='grade'>{_e(value)}<span class='of'> / {_e(top)}</span></p>")
            else:
                out.append(f"<p class='muted'>{_e(_value_text(value, top, language))}</p>")
        elif isinstance(value, int):
            out.append(f"<p class='grade'>{_e(_level_text(rubric, value, language))}</p>")
        else:
            out.append(f"<p class='muted'>{_e(_level_text(rubric, value, language))}</p>")
    return "".join(out)


def _format_date(day: date, language: str) -> str:
    return f"{day.year}年{day.month}月{day.day}日" if language == "ja" else day.strftime("%d %B %Y").lstrip("0")


def _marks_text(total, maximum, percent) -> str:
    return f"{total:g} / {maximum:g} · {percent:.1f}%"


def _section_name(config: dict, section: dict, language: str) -> str:
    position = [s["id"] for s in config.get("sections") or []].index(section["id"]) + 1
    return section["name"] or i18n.t("step2.sections.default_name", language, n=position)


# --- Results ---------------------------------------------------------------------------

def _overall_label(config: dict, summary: dict, language: str) -> str:
    """Rubric levels are never added to marks, so on a mixed paper the overall
    line says what it covers."""
    t = lambda key, **kw: i18n.t(key, language, **kw)     # noqa: E731
    stored = config.get("sections") or []
    with_marks = [s for s in summary["sections"] if s["max"]]
    if stored and len(with_marks) < len(summary["sections"]):
        return t("report.overall_of", what=", ".join(_section_name(config, s, language) for s in with_marks))
    if not stored and any(grading_summary.question_mode(config, q) == "rubric" for q in config.get("questions") or []):
        return t("report.overall_of", what=t("report.marks_questions"))
    return t("report.overall")


def _section_result(config: dict, grades: dict, student: dict, section: dict, row: dict,
                    not_counted, language: str) -> str:
    """A section's result: its marks, and its rubric grades as given. Never a
    total of the grades."""
    pieces = [_e(_marks_text(row["total"], row["max"], row["percent"]))] if row["max"] else []
    for q in section["questions"]:
        if grading_summary.question_mode(config, q) == "rubric" and not not_counted(q["id"]):
            text = _grade_text(_grades(config, grades, student["id"], q), language)
            pieces.append(f"{_e(q['label'])} <b>{_e(text)}</b>")
    return " &nbsp;·&nbsp; ".join(pieces)


def _results(w: _Writer, config: dict, grades: dict, student: dict, summary: dict, options: dict,
             not_counted, language: str) -> None:
    t = lambda key, **kw: i18n.t(key, language, **kw)     # noqa: E731
    marks = summary["marks"]
    weighted = marks["weighted"]
    overall = None
    if marks["max"] and options["overall_marks"]:
        overall = (f"{marks['report_percent']:.1f}%" if weighted
                   else _marks_text(marks["report_total"], marks["max"], marks["report_percent"]))
    label = _overall_label(config, summary, language)
    if not (options["section_results"] and config.get("sections")):
        if overall:
            w.html(f"<p class='label'>{_e(label)}</p><p class='big'>{_e(overall)}</p>", gap=GAP * 1.5)
        return

    widths = [176, CONTENT_W - 266, 90] if weighted else [176, CONTENT_W - 176]
    head = [t("report.section"), t("report.result")] + ([t("report.weighted_marks")] if weighted else [])
    rows = [[f"<p class='label'>{_e(text)}</p>" for text in head]]
    fills = [HEADING]
    for section, row in zip(grading_summary.sections(config), summary["sections"]):
        cells = [f"<p><b>{_e(_section_name(config, section, language))}</b></p>",
                 f"<p>{_section_result(config, grades, student, section, row, not_counted, language)}</p>"]
        if weighted:
            cells.append(f"<p>{row['weighted_marks']:.1f} / {row['share']}</p>" if row["max"] else "<p></p>")
        rows.append(cells)
        fills.append(None)
    if overall:
        cells = [f"<p><b>{_e(label)}</b></p>", f"<p><b>{_e(overall)}</b></p>"]
        if weighted:
            cells.append(f"<p><b>{marks['report_percent']:.1f} / 100</b></p>")
        rows.append(cells)
        fills.append(HEADING)
    w.ensure(60)
    w.html(f"<h2>{_e(t('report.results'))}</h2>", gap=4)
    _table(w, widths, rows, fills)
    w.y += GAP * 1.5


# --- Rubrics ---------------------------------------------------------------------------

def _criterion_side(rubric: dict, result: dict, weighted: bool, language: str) -> str:
    """One criterion's results: the final level if the teacher decided one, its
    marks and its grades. Empty when there is nothing to say yet."""
    t = lambda key, **kw: i18n.t(key, language, **kw)     # noqa: E731
    side = ""
    if result["final"] is not None:
        side += (f"<p class='label'>{_e(t('report.final_level'))}</p><p class='grade'>{_e(result['final'])}"
                 f"<span class='of'> / {rubrics.rubric_max(rubric)}</span></p>")
    criterion_marks = result["marks"]
    if criterion_marks and criterion_marks["percent"] is not None:
        shown = (f"{criterion_marks['percent']:.1f}%" if weighted else
                 _marks_text(criterion_marks["total"], criterion_marks["max"], criterion_marks["percent"]))
        side += f"<p class='label'>{_e(t('report.marks'))}: <b>{_e(shown)}</b></p>"
    if result["grades"]:
        given = ", ".join(_level_text(rubric, g["level"], language) for g in result["grades"])
        side += f"<p class='label'>{_e(t('report.grades'))}: <b>{_e(given)}</b></p>"
    return side


def _side_box(w: _Writer, side: str, top: float, x: float, width: float, height: float) -> None:
    box = fitz.Rect(x, top, x + width, top + height)
    w.page.draw_rect(box, color=FRAME, width=0.6)
    w.at(fitz.Rect(box.x0 + PAD, box.y0 + PAD, box.x1 - PAD, box.y1), side, css=GRADE_CSS, shrink=True)


def _criterion_block(w: _Writer, rubric: dict, side: str, show_table: bool, final) -> None:
    """A criterion's rubric table with its results beside it. A table too long to
    keep together on one page has the results above it instead."""
    has_words = show_table and any(str(b.get("descriptor") or "").strip() for b in rubric.get("bands") or [])
    awarded = lambda band: final is not None and band["min"] <= final <= band["max"]  # noqa: E731
    bands = sorted((b for b in rubric.get("bands") or []
                    if str(b.get("descriptor") or "").strip() or awarded(b)), key=lambda b: -b["min"]) if has_words else []
    if not bands and not side:
        return
    rows = [[f"<p><b>{_e(b['levels'])}</b></p>", f"<p>{_e(b.get('descriptor') or '')}</p>"] for b in bands]
    fills = [AWARDED if awarded(b) else None for b in bands]
    title = f"<h2>{_e(rubric['name'])}</h2>"
    title_h = _height_of(title, CONTENT_W, CSS) + 3

    def heights(table_w):
        return [_row_height(row, [LEVELS_W, table_w - LEVELS_W]) for row in rows]

    side_h = _height_of(side, SIDE_W - 6 - 2 * PAD, GRADE_CSS) + 2 * PAD if side else 0
    beside = bool(side and rows)
    block_h = max(sum(heights(CONTENT_W - SIDE_W)), side_h)
    if beside and title_h + block_h > PAGE_ROOM:
        beside = False
    if beside:
        w.ensure(title_h + block_h)
    elif rows:
        w.ensure(title_h + heights(CONTENT_W)[0])
    else:
        w.ensure(title_h + _height_of(side, CONTENT_W - 2 * PAD, GRADE_CSS) + 2 * PAD)
    w.html(title, gap=3)
    if side and not beside:
        height = _height_of(side, CONTENT_W - 2 * PAD, GRADE_CSS) + 2 * PAD
        _side_box(w, side, w.y, MARGIN, CONTENT_W, height)
        w.y += height + 4
    top = w.y
    table_w = CONTENT_W - SIDE_W if beside else CONTENT_W
    if rows:
        _table(w, [LEVELS_W, table_w - LEVELS_W], rows, fills)
    if beside:
        height = max(w.y - top, side_h)
        _side_box(w, side, top, MARGIN + table_w + 6, SIDE_W - 6, height)
        w.y = top + height
    w.y += GAP


# --- Questions -------------------------------------------------------------------------

_HIGHLIGHT_FILLS = {
    "yellow": ((1.0, 0.92, 0.23), 0.35),
    "blue": ((0.38, 0.72, 1.0), 0.32),
    "pink": ((1.0, 0.48, 0.72), 0.32),
}
_STAMP_FILLS = {
    "strength": (0.08, 0.45, 0.29),
    "growth": (0.80, 0.45, 0.0),
    None: (0.14, 0.35, 0.84),
}


def _question_note_items(config: dict, question: dict, entry: dict, not_counted, group_of: dict,
                         language: str) -> List[str]:
    """Paragraphs printed under a question: choice reason, comment, and numbered notes."""
    t = lambda key, **kw: i18n.t(key, language, **kw)     # noqa: E731
    items = []
    if not_counted(question["id"]):
        why = ("report.not_counted_teacher"
               if grading_summary.group_pick(group_of[question["id"]]) == grading_summary.PICK_TEACHER
               else "report.not_counted_long")
        items.append(f"<p class='muted'>{_e(t(why))}</p>")
    comment = str(entry.get("comment") or "").strip()
    if comment:
        items.append(f"<p><span class='label'>{_e(t('report.comment'))}{'：' if language == 'ja' else ':'}</span> {_e(comment)}</p>")
    for i, ann in enumerate(entry.get("annotations") or [], 1):
        text = str(ann.get("text") or "").strip()
        if not text:
            continue
        kind = ann.get("type")
        if kind in ("strength", "growth"):
            tag_key = "report.note_strength" if kind == "strength" else "report.note_growth"
            tag = f" <span class='note-tag {kind}'>[{_e(t(tag_key))}]</span>"
        else:
            tag = ""
        items.append(f"<p><b>({i})</b>{tag} {_e(text)}</p>")
    return items


def _question_notes(config: dict, question: dict, entry: dict, not_counted, group_of: dict, language: str) -> str:
    return "".join(_question_note_items(config, question, entry, not_counted, group_of, language))


def _answer_geometry_for_report(session: storage.Session, layout: slicer.Layout,
                                question: dict, student: dict, crop_w: int, crop_h: int) -> dict:
    scan_rel = student.get("file")
    if scan_rel and question.get("boxes"):
        scan_path = session.path(f"{storage.SCANS_DIR}/{scan_rel}")
        if os.path.isfile(scan_path):
            boxes = slicer.parse_boxes(question["boxes"], layout)
            geom = slicer.answer_geometry(scan_path, boxes, layout)
            if (geom["width"], geom["height"]) == (crop_w, crop_h):
                return geom
    return slicer._build_geometry([(1, crop_w, crop_h, (0, 0, crop_w, crop_h), 1.0)], divider_px=0)


def _draw_overlay(page, rect: fitz.Rect, win_x0: float, win_y0: float, win_w: float, win_h: float,
                  part_index: Optional[int], proj_hls: List[dict], proj_notes: List[dict],
                  include_bottom: bool = True) -> None:
    if win_w <= 0 or win_h <= 0:
        return
    for hl in proj_hls:
        rgb, alpha = _HIGHLIGHT_FILLS.get(hl.get("colour"), _HIGHLIGHT_FILLS["yellow"])
        for piece in hl.get("pieces") or []:
            if part_index is not None and piece["part_index"] != part_index:
                continue
            ix0 = max(piece["cx"], win_x0)
            iy0 = max(piece["cy"], win_y0)
            ix1 = min(piece["cx"] + piece["cw"], win_x0 + win_w)
            iy1 = min(piece["cy"] + piece["ch"], win_y0 + win_h)
            if ix1 <= ix0 or iy1 <= iy0:
                continue
            px0 = rect.x0 + ((ix0 - win_x0) / win_w) * rect.width
            py0 = rect.y0 + ((iy0 - win_y0) / win_h) * rect.height
            px1 = rect.x0 + ((ix1 - win_x0) / win_w) * rect.width
            py1 = rect.y0 + ((iy1 - win_y0) / win_h) * rect.height
            page.draw_rect(fitz.Rect(px0, py0, px1, py1), color=None, fill=rgb,
                           fill_opacity=alpha, overlay=True)

    for ann in proj_notes:
        if part_index is not None and ann["part_index"] != part_index:
            continue
        cx, cy = ann["cx"], ann["cy"]
        if not (win_x0 <= cx <= win_x0 + win_w):
            continue
        if include_bottom:
            if not (win_y0 <= cy <= win_y0 + win_h):
                continue
        elif not (win_y0 <= cy < win_y0 + win_h):
            continue
        sx = rect.x0 + ((cx - win_x0) / win_w) * rect.width
        sy = rect.y0 + ((cy - win_y0) / win_h) * rect.height
        fill = _STAMP_FILLS.get(ann.get("type"), _STAMP_FILLS[None])
        page.draw_circle((sx, sy), 7.5, color=(1, 1, 1), fill=fill, width=0.9, overlay=True)
        label = str(ann["num"])
        fs = 8.5 if len(label) == 1 else 7.2
        tw = fitz.get_text_length(label, fontname="hebo", fontsize=fs)
        page.insert_text((sx - tw / 2, sy + fs * 0.34), label, fontname="hebo",
                         fontsize=fs, color=(1, 1, 1), overlay=True)


def _question_with_image(w: _Writer, session: storage.Session, layout: slicer.Layout, question: dict,
                         student: dict, entry: dict, parts: List[tuple], note_items: List[str],
                         language: str) -> None:
    name = slicer.crop_file(question["id"], slicer.student_crop_key(student), layout)
    crop = session.path(f"{storage.CROPS_DIR}/{name}")
    x_img = MARGIN + LABEL_W
    if os.path.isfile(crop):
        with Image.open(crop) as crop_im:
            crop_w, crop_h = crop_im.size
            geom = _answer_geometry_for_report(session, layout, question, student, crop_w, crop_h)
            proj_notes = slicer.project_annotations(geom, entry.get("annotations") or [])
            proj_hls = slicer.project_highlights(geom, entry.get("highlights") or [])
            natural_h = crop_h * (IMAGE_MAX_W / crop_w) if crop_w else 0

            if natural_h <= IMAGE_MAX_H or not geom["parts"]:
                jpg_bytes, enc_w, enc_h = _encode_jpeg(crop_im)
                img_w, img_h = _fit(enc_w, enc_h, IMAGE_MAX_W, IMAGE_MAX_H)
                row_h = max(img_h, 28)
                w.ensure(row_h)
                top = w.y
                w.at(fitz.Rect(MARGIN, top, x_img - 6, top + row_h),
                     f"<h2>{_e(question['label'])}</h2>", shrink=True)
                rect = fitz.Rect(x_img, top, x_img + img_w, top + img_h)
                w.page.insert_image(rect, stream=jpg_bytes)
                w.page.draw_rect(rect, color=FRAME, width=0.8)
                _draw_overlay(w.page, rect, 0, 0, crop_w, crop_h, None, proj_hls, proj_notes)
                x_grade = x_img + img_w + 10
                w.at(fitz.Rect(x_grade, top, x_grade + GRADE_W, top + row_h),
                     _grade_html(parts, language), css=GRADE_CSS, shrink=True)
                w.y = top + row_h + 4
            else:
                pt_per_px = IMAGE_MAX_W / crop_w
                first_h = geom["parts"][0]["crop_h"] * pt_per_px
                w.ensure(min(max(first_h, 28), 140))
                header_drawn = False
                for part in geom["parts"]:
                    pw, ph = part["crop_w"], part["crop_h"]
                    part_draw_w = pw * pt_per_px
                    part_draw_h = ph * pt_per_px
                    if part_draw_h > (w.bottom - w.y) and part_draw_h <= PAGE_ROOM - 8 and w.y > MARGIN + 1:
                        w.new_page()
                    part_im = crop_im.crop((part["crop_x"], part["crop_y"],
                                            part["crop_x"] + pw, part["crop_y"] + ph))
                    try:
                        cur_px = 0
                        while cur_px < ph:
                            if w.bottom - w.y < 60:
                                w.new_page()
                            avail_h = w.bottom - w.y
                            slice_px = ph - cur_px
                            if slice_px * pt_per_px > avail_h:
                                slice_px = max(1, min(ph - cur_px, int(avail_h / pt_per_px)))
                            is_last = (cur_px + slice_px >= ph)
                            strip_h_pt = slice_px * pt_per_px
                            strip_im = (part_im if (cur_px == 0 and is_last)
                                        else part_im.crop((0, cur_px, pw, cur_px + slice_px)))
                            try:
                                jpg_bytes, _, _ = _encode_jpeg(strip_im)
                            finally:
                                if strip_im is not part_im:
                                    strip_im.close()
                            top = w.y
                            rect = fitz.Rect(x_img, top, x_img + part_draw_w, top + strip_h_pt)
                            if not header_drawn:
                                row_h = max(strip_h_pt, 28)
                                w.at(fitz.Rect(MARGIN, top, x_img - 6, top + row_h),
                                     f"<h2>{_e(question['label'])}</h2>", shrink=True)
                                x_grade = x_img + IMAGE_MAX_W + 10
                                w.at(fitz.Rect(x_grade, top, x_grade + GRADE_W, top + row_h),
                                     _grade_html(parts, language), css=GRADE_CSS, shrink=True)
                                header_drawn = True
                            w.page.insert_image(rect, stream=jpg_bytes)
                            w.page.draw_rect(rect, color=FRAME, width=0.8)
                            _draw_overlay(w.page, rect, part["crop_x"], part["crop_y"] + cur_px,
                                          pw, slice_px, part["index"], proj_hls, proj_notes,
                                          include_bottom=is_last)
                            w.y = top + strip_h_pt + 4
                            cur_px += slice_px
                    finally:
                        part_im.close()
    else:
        row_h = 28
        w.ensure(row_h)
        top = w.y
        w.at(fitz.Rect(MARGIN, top, x_img - 6, top + row_h),
             f"<h2>{_e(question['label'])}</h2>", shrink=True)
        x_grade = x_img + 10
        w.at(fitz.Rect(x_grade, top, x_grade + GRADE_W, top + row_h),
             _grade_html(parts, language), css=GRADE_CSS, shrink=True)
        w.y = top + row_h + 4

    for item in note_items:
        w.html(item, x=x_img, width=CONTENT_W - LABEL_W, gap=2)
    w.y += GAP * 1.4


def _questions_as_grid(w: _Writer, rows: List[tuple], language: str) -> None:
    """No images: a grid for bare grades, then one row per question with anything
    to say. ``rows`` holds (question, grades, notes)."""
    plain = [(q, parts) for q, parts, notes in rows if not notes]
    width = CONTENT_W / GRID_COLUMNS
    for start in range(0, len(plain), GRID_COLUMNS):
        w.ensure(GRID_ROW_H)
        for j, (q, parts) in enumerate(plain[start:start + GRID_COLUMNS]):
            _cell(w, MARGIN + j * width, width, GRID_ROW_H,
                  f"<p><b>{_e(q['label'])}</b>&nbsp;&nbsp;&nbsp;{_e(_grade_text(parts, language))}</p>")
        w.y += GRID_ROW_H
    noted = [[f"<p><b>{_e(q['label'])}</b></p>", f"<p>{_e(_grade_text(parts, language))}</p>", notes]
             for q, parts, notes in rows if notes]
    if noted:
        _table(w, [40, 66, CONTENT_W - 106], noted)
    w.y += GAP


def _section_heading(w: _Writer, name: str, right: str, room: float) -> None:
    """A heading always stays on the same page as the first row under it."""
    w.ensure(28 + room)
    w.page.draw_rect(fitz.Rect(MARGIN, w.y, MARGIN + CONTENT_W, w.y + 22), color=None, fill=HEADING)
    w.at(fitz.Rect(MARGIN + PAD, w.y + 4, MARGIN + 340, w.y + 22), f"<p><b>{_e(name)}</b></p>", shrink=True)
    if right:
        w.at(fitz.Rect(MARGIN + 340, w.y + 4, MARGIN + CONTENT_W - PAD, w.y + 22),
             f"<p style='text-align:right'><b>{_e(right)}</b></p>", shrink=True)
    w.y += 28


# --- One student ----------------------------------------------------------------------------

def _submission_pages(w, session, config, grades, student, entries, options, language):
    from .workflow import student_scan_path
    path = student_scan_path(session, student)
    q = config["questions"][0]
    entry = entries.get(q["id"]) or {}
    # The submission is the assessed item; its grade must print even when
    # no pages carry annotations and the rubric table is off (assignments show it beside the rubric).
    parts = _grades(config, grades, student["id"], q)
    if grading_summary.question_mode(config, q) and not model.is_assignment(config):
        w.html(_grade_html(parts, language))
    notes = entry.get("annotations") or []
    highlights = entry.get("highlights") or []
    marked = {a["page"] for a in notes + highlights}
    selected = range(1, student["pages"] + 1) if options["all_submission_pages"] else sorted(marked)
    for number in selected:
        w.new_page()
        w.html(f"<h2>{_e(i18n.t('common.page_of', language, page=number, pages=student['pages']))}</h2>")
        geom = slicer.whole_page_geometry(path, number)
        with slicer.load_page_image(path, number) as im:
            data, iw, ih = _encode_jpeg(im)
        width, height = _fit(iw, ih, CONTENT_W, w.bottom - w.y)
        rect = fitz.Rect(MARGIN, w.y, MARGIN + width, w.y + height)
        w.page.insert_image(rect, stream=data)
        projected = [a for a in slicer.project_annotations(geom, notes) if a["page"] == number]
        _draw_overlay(w.page, rect, 0, 0, geom["width"], geom["height"], None,
                      slicer.project_highlights(geom, highlights), projected)
        w.y += height + GAP
    for item in _question_note_items(config, q, entry, lambda _: False, {}, language):
        w.html(item)


def build_student_pdf(session: storage.Session, config: dict, grades: dict, student: dict,
                      language: str, out_path: str, day: Optional[date] = None) -> str:
    from .workflow import display_name, report_options    # avoid an import cycle
    t = lambda key, **kw: i18n.t(key, language, **kw)     # noqa: E731
    name = display_name(config, student)
    summary = grading_summary.student_summary(config, grades, student["id"])
    entries = (grades.get("grades") or {}).get(student["id"]) or {}
    group_of = {qid: g for g in config.get("choice_groups") or [] for qid in g["questions"]}
    options = report_options(config)

    def not_counted(qid):
        g = group_of.get(qid)
        return (g is not None and g["id"] not in summary["pending"]
                and qid not in summary["ungraded"] and qid not in summary["counted"])

    with fitz.open() as doc:
        w = _Writer(doc, f"{config['exam_name']} · {name}")

        # Header ---------------------------------------------------------------------------
        w.html(f"<h1>{_e(config['exam_name'])}</h1>"
               f"<p class='muted'>{_e(_format_date(day or date.today(), language))}</p>", gap=4)
        w.html(f"<p class='label'>{_e(t('report.student'))}</p><h2>{_e(name)}</h2>", gap=GAP)

        _results(w, config, grades, student, summary, options, not_counted, language)

        # The rubrics, once, and only those this exam uses ---------------------------------
        used = {rid for q in config.get("questions") or []
                for rid in grading_summary.question_rubric_ids(config, q)}
        sub_q = (config.get("questions") or [{}])[0]
        sub_entry = entries.get(sub_q.get("id")) or {}
        for r in config.get("rubrics") or []:
            if r["id"] in used:
                if model.is_assignment(config):
                    level = grading_summary.level_of(config, sub_entry, sub_q, r["id"])
                    final = level if isinstance(level, int) else None
                    side = f"<p class='label'>{_e(t('report.result'))}</p>{_grade_html([(r, level, rubrics.rubric_max(r))], language)}"
                    _criterion_block(w, r, side, options["rubric_table"], final)
                else:
                    result = summary["rubrics"][r["id"]]
                    final = result["final"] if options["overall_criteria"] else None
                    side = (_criterion_side(r, result, summary["marks"]["weighted"], language)
                            if options["overall_criteria"] else "")
                    _criterion_block(w, r, side, options["rubric_table"], final)

        overall = ((grades.get("overall") or {}).get(student["id"]) or {}).get("comment", "").strip()
        if overall:
            w.html(f"<p class='label'>{_e(t('report.overall_comment'))}</p><p>{_e(overall)}</p>", gap=GAP * 1.5)

        if model.whole_submission(config):
            _submission_pages(w, session, config, grades, student, entries, options, language)
        else:
            # Questions, grouped by section ----------------------------------------------------
            w.ensure(120)
            w.html(f"<h2>{_e(t('report.questions'))}</h2>", gap=6)
            for section, row in zip(grading_summary.sections(config), summary["sections"]):
                images = section["id"] not in options["no_images_for"]
                if config.get("sections"):
                    right = (_marks_text(row["total"], row["max"], row["percent"])
                             if options["section_results"] and row["max"] else "")
                    _section_heading(w, _section_name(config, section, language), right, 140 if images else 40)
                rows = [(q, _grades(config, grades, student["id"], q),
                         _question_note_items(config, q, entries.get(q["id"]) or {}, not_counted, group_of, language))
                        for q in section["questions"]]
                if images:
                    for q, parts, note_items in rows:
                        _question_with_image(w, session, slicer.Layout.from_config(config.get("layout")), q, student,
                                             entries.get(q["id"]) or {}, parts, note_items, language)
                else:
                    _questions_as_grid(w, [(q, parts, "".join(note_items)) for q, parts, note_items in rows], language)

        w.finish()
        doc.subset_fonts()
        doc.save(out_path, garbage=4, deflate=True)
    return out_path


def preview_pdf(session: storage.Session, config: dict, grades: dict, student: dict, language: str) -> bytes:
    """One student's report, without touching the reports folder."""
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "report.pdf")
        build_student_pdf(session, config, grades, student, language, path)
        with open(path, "rb") as fh:
            return fh.read()


# --- The whole class -------------------------------------------------------------------------

def report_filename(config: dict, student: dict, taken: set) -> str:
    """'<Student Name>_<Exam Name>.pdf'.

    With a class list, a paper not matched to it is marked UNMATCHED_ so it
    is never sent to the wrong person. Without a class list the paper's own
    name is used, since the scans are often already named after students.
    """
    from .workflow import display_name
    exam = slicer.safe_filename(config["exam_name"], "Exam")
    named = bool(student.get("roster_id") or str(student.get("name") or "").strip()
                 or not config.get("roster"))
    if named:
        base = f"{slicer.safe_filename(display_name(config, student))}_{exam}"
    else:
        base = f"UNMATCHED_{slicer.safe_filename(os.path.splitext(student.get('source') or student['file'])[0])}"
    return slicer.unique_name(base[:150] + ".pdf", taken)


def student_pdfs_dir(session: storage.Session) -> str:
    return session.path(f"{storage.REPORTS_DIR}/student_pdfs")


def export_student_pdfs(session: storage.Session, config: dict, grades: dict, language: str,
                        progress: Optional[Callable[[int, int], None]] = None) -> dict:
    """Write every student's report into reports/student_pdfs/ (replacing old ones).

    A file that can't be written (e.g. open in a PDF viewer) is reported in
    ``errors`` and the rest of the class still gets their reports.
    """
    out_dir = student_pdfs_dir(session)
    if os.path.isdir(out_dir):
        for name in os.listdir(out_dir):
            if name.lower().endswith(".pdf"):
                try:
                    os.remove(os.path.join(out_dir, name))
                except OSError:
                    pass
    os.makedirs(out_dir, exist_ok=True)
    taken: set = set()
    files: List[str] = []
    errors: List[dict] = []
    students = config.get("students") or []
    for i, student in enumerate(students, 1):
        filename = report_filename(config, student, taken)
        path = os.path.join(out_dir, filename)
        try:
            build_student_pdf(session, config, grades, student, language, path)
            files.append(filename)
        except Exception as exc:                  # keep going for the rest of the class
            errors.append({"student": student["id"], "file": filename, "error": str(exc)})
        if progress:
            progress(i, len(students))
    return {"folder": out_dir, "files": files, "errors": errors}


def check_writable_file(path: str) -> None:
    """Raise a friendly error if a report file is open in another program."""
    if os.path.exists(path):
        try:
            with open(path, "ab"):
                pass
        except PermissionError as exc:
            raise UserError("report_file_open", file=os.path.basename(path)) from exc
