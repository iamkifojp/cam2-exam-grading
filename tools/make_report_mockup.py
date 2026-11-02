"""Make the mock-up student reports for Exam-Section-Plan.md. All data is made up.

    python tools/make_report_mockup.py

Writes to doc/mockups/, as a PDF (ignored by git) and one PNG per page:
    report-images-by-section   answer images on for Sections B and C only
    report-no-images           no answer images, to save paper

This only draws the planned layout from the fixed data below; the app does not
use it. Delete it when the real report is built (Exam-Section-Plan.md, Phase 5).
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymupdf as fitz  # noqa: E402

from engine.grading_summary import round_half_up  # noqa: E402
from engine.reports import (CONTENT_W, CSS, FRAME, GAP, GRADE_CSS, GRADE_W, IMAGE_MAX_H,  # noqa: E402
                            IMAGE_MAX_W, LABEL_W, MARGIN, _e, _fit, _Writer)

OUT = Path(__file__).resolve().parent.parent / "doc" / "mockups"
TABLE_CSS = CSS + " * { font-size: 9.5pt; line-height: 1.3; } p { margin: 0; }"
PAD = 3
AWARDED = (0.87, 0.95, 0.90)
HEADING = (0.93, 0.94, 0.96)
SIDE_W = 92

STUDENT = "Yui Suzuki"
EXAM = "Grade 8 Science: Term 2 Exam"
DATE = "2 November 2026"
OVERALL_COMMENT = ("A strong term. You know the content well and apply it confidently. "
                   "Next, explain why your method is fair and support each conclusion with data.")

# Sample wording only: CAM2 ships no rubric text, and teachers enter their own.
RUBRICS = {
    "Criterion A": {"final": 7, "bands": [
        ("7–8", 7, 8, "Explains ideas fully and applies them to unfamiliar problems."),
        ("5–6", 5, 6, "Outlines ideas and applies them to familiar and some unfamiliar problems."),
        ("3–4", 3, 4, "States ideas and applies them to familiar problems."),
        ("1–2", 1, 2, "Recalls some ideas and suggests solutions with help.")]},
    "Criterion B": {"final": 6, "bands": [
        ("7–8", 7, 8, "Plans a fair method and justifies every choice."),
        ("5–6", 5, 6, "Plans a workable method and explains most choices."),
        ("3–4", 3, 4, "Describes a simple method with some reasons."),
        ("1–2", 1, 2, "States part of a method.")]},
    "Criterion C": {"final": 5, "bands": [
        ("7–8", 7, 8, "Analyses data and draws a conclusion that the evidence fully supports."),
        ("5–6", 5, 6, "Interprets data and draws a conclusion with some evidence."),
        ("3–4", 3, 4, "Describes patterns in data and draws a simple conclusion."),
        ("1–2", 1, 2, "Reads some values from data.")]},
}


def q(label, got=None, top=None, levels=None, comment="", ask="", answer=(), crit=None):
    return {"label": label, "got": got, "top": top, "levels": levels, "comment": comment,
            "ask": ask, "answer": answer, "crit": crit}


WRONG = {7, 15, 22}
SECTIONS = [
    {"name": "Section A", "title": "Scientific knowledge", "weight": 50,
     "questions": [q(f"1.{n}", 0 if n in WRONG else 1, 1, crit="Criterion A") for n in range(1, 26)]},
    {"name": "Section B", "title": "Applying knowledge", "weight": 50,
     "questions": [
         q("2A", 10, 12, crit="Criterion A", ask="2A. Complete the table of plant parts and their functions.",
           answer=("Roots take in water and minerals.", "Leaves make food by photosynthesis.")),
         q("2B", 6, 8, crit="Criterion A", comment="Good idea. Give a reason for each change you suggest.",
           ask="2B. Design a plant for a dry planet. What would you change?",
           answer=("Smaller leaves, so less water is lost.", "Longer roots to reach deep water.")),
         q("3", 8, 10, crit="Criterion A", ask="3. Balance the equation and name each product.",
           answer=("6CO2 + 6H2O gives C6H12O6 + 6O2", "The products are glucose and oxygen.")),
         q("4", 6, 10, crit="Criterion B", comment="Your method tests one variable. Say what you keep the same.",
           ask="4. Plan how to test the effect of light on plant growth.",
           answer=("Grow plants at three light levels for two weeks.", "Measure the height every day."))]},
    {"name": "Section C", "title": "Investigation", "weight": None,
     "questions": [
         q("5", levels=[("Criterion B", 6)], ask="5. Write a testable question and a hypothesis.",
           answer=("Does more light mean more bubbles of gas?", "I think that more light gives more bubbles.")),
         q("6", levels=[("Criterion B", 5), ("Criterion C", 5)],
           comment="The conclusion follows from your graph. Quote values from it next time.",
           ask="6. Draw a graph of the results, then state a conclusion.",
           answer=("The closer the lamp, the more bubbles.", "So light increases photosynthesis.")),
         q("7", levels=[("Criterion C", 6)], ask="7. Explain one way to improve the investigation.",
           answer=("Repeat each distance three times.", "Then an unusual result is easy to spot."))]},
]


def marks_of(section):
    if section["weight"] is None:
        return None
    got = sum(x["got"] for x in section["questions"])
    top = sum(x["top"] for x in section["questions"])
    return got, top, round_half_up(Decimal(got) * 100 / Decimal(top), 1)


def overall_percent():
    """Weighted from unrounded section figures, and rounded once at the end."""
    total = Decimal(0)
    for section in SECTIONS:
        if section["weight"] is not None:
            got = sum(x["got"] for x in section["questions"])
            top = sum(x["top"] for x in section["questions"])
            total += Decimal(got) / Decimal(top) * section["weight"]
    return round_half_up(total, 1)


def criterion_percent(name):
    """Each question counts as much here as it does in the overall percentage,
    so only the questions on this criterion share the 100%."""
    earned = counted = Decimal(0)
    for section in SECTIONS:
        if section["weight"] is None:
            continue
        section_max = sum(x["top"] for x in section["questions"])
        for x in section["questions"]:
            if x["crit"] == name:
                share = Decimal(section["weight"]) * x["top"] / section_max
                earned += Decimal(x["got"]) / x["top"] * share
                counted += share
    return round_half_up(earned * 100 / counted, 1) if counted else None


def height_of(text: str, width: float, css: str = TABLE_CSS) -> float:
    scratch = fitz.open()
    page = scratch.new_page(width=width + 20, height=800)
    spare, _ = page.insert_htmlbox(fitz.Rect(0, 0, width, 800), text, css=css, scale_low=1)
    scratch.close()
    return 800 - spare


def cell(w, x, width, height, text, fill=None, css=TABLE_CSS):
    rect = fitz.Rect(x, w.y, x + width, w.y + height)
    w.page.draw_rect(rect, color=FRAME, fill=fill, width=0.6)
    w.at(fitz.Rect(x + PAD, w.y + PAD, x + width - PAD, w.y + height), text, css=css, shrink=True)


def table(w, widths, rows, fills=None):
    """Bordered rows, drawn cell by cell: MuPDF's HTML ignores table column widths."""
    for i, row in enumerate(rows):
        height = max(height_of(t, widths[j] - 2 * PAD) for j, t in enumerate(row)) + 2 * PAD
        w.ensure(height)
        x = MARGIN
        for j, text in enumerate(row):
            cell(w, x, widths[j], height, text, fills[i] if fills else None)
            x += widths[j]
        w.y += height


def header(w):
    w.html(f"<h1>{_e(EXAM)}</h1><p class='muted'>{_e(DATE)} · Mock-up: the student, marks and "
           "comments are made up</p>", gap=4)
    w.html(f"<p class='label'>Student</p><h2>{_e(STUDENT)}</h2>", gap=GAP)


def results(w):
    w.html("<h2>Results</h2>", gap=4)
    head = ["Section", "Result", "Weighting"]
    rows = [[f"<p class='label'>{h}</p>" for h in head]]
    for s in SECTIONS:
        marks = marks_of(s)
        result = (f"{marks[0]} / {marks[1]} · {marks[2]:g}%" if marks else
                  " &nbsp;·&nbsp; ".join(f"Q{x['label']} <b>{_e(grade_text(x))}</b>" for x in s["questions"]))
        weight = f"{s['weight']}%" if s["weight"] is not None else ""
        rows.append([f"<p><b>{_e(s['name'])}</b> {_e(s['title'])}</p>", f"<p>{result}</p>", f"<p>{weight}</p>"])
    rows.append(["<p><b>Overall</b> (Sections A and B)</p>", f"<p><b>{overall_percent():g}%</b></p>", "<p>100%</p>"])
    fills = [HEADING] + [None] * len(SECTIONS) + [HEADING]
    table(w, [176, CONTENT_W - 234, 58], rows, fills)
    w.y += GAP * 1.5


def rubric_block(w, name, rubric):
    width = CONTENT_W - SIDE_W
    rows = [(f"<p><b>{_e(levels)}</b></p>", f"<p>{_e(text)}</p>", lo <= rubric["final"] <= hi)
            for levels, lo, hi, text in rubric["bands"]]
    heights = [max(height_of(a, 44 - 2 * PAD), height_of(b, width - 44 - 2 * PAD)) + 2 * PAD for a, b, _ in rows]
    title_h = height_of(f"<h2>{_e(name)}</h2>", CONTENT_W) + 3
    w.ensure(title_h + sum(heights) + GAP)
    w.html(f"<h2>{_e(name)}</h2>", gap=3)
    top = w.y
    for (a, b, hit), height in zip(rows, heights):
        fill = AWARDED if hit else None
        cell(w, MARGIN, 44, height, a, fill)
        cell(w, MARGIN + 44, width - 44, height, b, fill)
        w.y += height
    box = fitz.Rect(MARGIN + width + 6, top, MARGIN + CONTENT_W, w.y)
    w.page.draw_rect(box, color=FRAME, width=0.6)
    top_level = max(hi for _, _, hi, _ in rubric["bands"])
    side = (f"<p class='label'>Final level</p><p class='grade'>{rubric['final']}"
            f"<span class='of'> / {top_level}</span></p>")
    given = [f"{name[-1]}{v}" for s in SECTIONS for x in s["questions"]
             for n, v in x["levels"] or [] if n == name]
    percent = criterion_percent(name)
    if percent is not None:
        side += f"<p class='label'>Marks: <b>{percent:g}%</b></p>"
    if given:
        side += f"<p class='label'>Grades: <b>{', '.join(given)}</b></p>"
    w.at(fitz.Rect(box.x0 + PAD, box.y0 + PAD, box.x1 - PAD, box.y1 - PAD), side, css=GRADE_CSS, shrink=True)
    w.y += GAP


def answer_image(question):
    """A made-up cropped answer: printed question, ruled lines, 'handwriting'."""
    doc = fitz.open()
    width, height = 480, 112
    page = doc.new_page(width=width, height=height)
    page.draw_rect(page.rect, color=None, fill=(0.975, 0.975, 0.97))
    page.insert_text((12, 20), question["ask"], fontsize=11)
    for i, line in enumerate(question["answer"]):
        y = 50 + i * 28
        page.draw_line((12, y + 5), (width - 12, y + 5), color=(0.7, 0.7, 0.7), width=0.5)
        page.insert_text((18, y), line, fontsize=14, fontname="tiit", color=(0.1, 0.1, 0.5))
    jpeg = page.get_pixmap(dpi=150).tobytes("jpeg", jpg_quality=82)
    doc.close()
    return jpeg, width, height


def grade_html(question):
    if question["levels"] is None:
        return f"<p class='grade'>{question['got']}<span class='of'> / {question['top']}</span></p>"
    return "".join(f"<p class='grade'>{n[-1]}{v}</p>" for n, v in question["levels"])


def grade_text(question):
    if question["levels"] is None:
        return f"{question['got']} / {question['top']}"
    return " ".join(f"{n[-1]}{v}" for n, v in question["levels"])


def section_heading(w, section, room):
    """A heading always stays on the same page as the first row under it."""
    w.ensure(28 + room)
    marks = marks_of(section)
    right = f"{marks[0]} / {marks[1]} · {marks[2]:g}%" if marks else "Rubric"
    w.page.draw_rect(fitz.Rect(MARGIN, w.y, MARGIN + CONTENT_W, w.y + 22), color=None, fill=HEADING)
    w.at(fitz.Rect(MARGIN + PAD, w.y + 4, MARGIN + 360, w.y + 22),
         f"<p><b>{_e(section['name'])}</b> {_e(section['title'])}</p>")
    w.at(fitz.Rect(MARGIN + 360, w.y + 4, MARGIN + CONTENT_W - PAD, w.y + 22),
         f"<p style='text-align:right'><b>{right}</b></p>")
    w.y += 28


def with_images(w, section):
    for question in section["questions"]:
        jpeg, px_w, px_h = answer_image(question)
        img_w, img_h = _fit(px_w, px_h, IMAGE_MAX_W, IMAGE_MAX_H)
        row_h = max(img_h, 28)
        comment = (f"<p><span class='label'>Teacher’s comment:</span> {_e(question['comment'])}</p>"
                   if question["comment"] else "")
        w.ensure(row_h + (24 if comment else 0))
        top, x_img = w.y, MARGIN + LABEL_W
        w.at(fitz.Rect(MARGIN, top, x_img - 6, top + row_h), f"<h2>{_e(question['label'])}</h2>", shrink=True)
        rect = fitz.Rect(x_img, top, x_img + img_w, top + img_h)
        w.page.insert_image(rect, stream=jpeg)
        w.page.draw_rect(rect, color=FRAME, width=0.8)
        x_grade = x_img + img_w + 10
        w.at(fitz.Rect(x_grade, top, x_grade + GRADE_W - 10, top + row_h), grade_html(question), css=GRADE_CSS, shrink=True)
        w.y = top + row_h + 4
        if comment:
            w.html(comment, x=x_img, width=CONTENT_W - LABEL_W, gap=0)
        w.y += GAP


def compact(w, section):
    """No images: a grid for bare grades, then one row per question with a comment."""
    plain = [x for x in section["questions"] if not x["comment"]]
    columns = 5
    width = CONTENT_W / columns
    for start in range(0, len(plain), columns):
        w.ensure(20)
        for j, question in enumerate(plain[start:start + columns]):
            cell(w, MARGIN + j * width, width, 20,
                 f"<p><b>{_e(question['label'])}</b>&nbsp;&nbsp;&nbsp;{_e(grade_text(question))}</p>")
        w.y += 20
    commented = [x for x in section["questions"] if x["comment"]]
    if commented:
        table(w, [40, 66, CONTENT_W - 106],
              [[f"<p><b>{_e(x['label'])}</b></p>", f"<p>{_e(grade_text(x))}</p>", f"<p>{_e(x['comment'])}</p>"]
               for x in commented])
    w.y += GAP


def build(name: str, images_for: set):
    OUT.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    w = _Writer(doc, f"MOCK-UP · {EXAM} · {STUDENT}")
    header(w)
    results(w)
    for rubric_name, rubric in RUBRICS.items():
        rubric_block(w, rubric_name, rubric)
    w.html(f"<p class='label'>Overall comment</p><p>{_e(OVERALL_COMMENT)}</p>", gap=GAP * 1.5)
    w.ensure(120)
    w.html("<h2>Questions</h2>", gap=6)
    for section in SECTIONS:
        shown = section["name"] in images_for
        section_heading(w, section, 140 if shown else 40)
        (with_images if shown else compact)(w, section)
    w.finish()
    doc.subset_fonts()
    doc.save(OUT / f"{name}.pdf", garbage=4, deflate=True)
    for i, page in enumerate(doc, 1):
        page.get_pixmap(dpi=90).save(OUT / f"{name}-p{i}.png")
    print(f"{name}: {doc.page_count} pages, {(OUT / f'{name}.pdf').stat().st_size // 1024} kB")
    doc.close()


if __name__ == "__main__":
    build("report-images-by-section", {"Section B", "Section C"})
    build("report-no-images", set())
