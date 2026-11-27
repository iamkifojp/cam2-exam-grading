# CAM2 Quick Guide and sample exam — plan

**Agreed:** 2026-11-27. **Status:** planned; nothing built yet. Part of Phase J ([PLAN.md](PLAN.md) §12: "the bundled guides" and the sample exams).

The guide is for two kinds of reader: a teacher who has never used grading software or scanned a class set, and a teacher deciding whether CAM2 is worth trying. The app stays usable without it, so the guide gives a broad overview with pictures and goes into detail only where the app is hard to follow on its own.

## 1. Decisions

| Decision | Why |
|---|---|
| **Page 1 is always the quick start:** starting CAM2 on Windows or Mac (Mac first-run pictures kept) and the five steps in one line each | A teacher who reads nothing else still gets going |
| **Page 2 explains what CAM2 is for**, for teachers considering it | The first question a new reader has |
| **Japanese pages have their own screenshots,** taken with the app in 日本語 | The screens look alike; labels must match the text or readers lose track of which screen is which |
| **No Apps Script in the CAM2 guide** | Downloading Classroom work is a CAM problem and a niche one. Whether CAM documents a script is CAM's decision |
| **Standalone scope only.** Assignments, drafts, Late and partners get one line ("inside CAM it also grades assignments and drafts") | The bundled zip is an exam grader (SPEC §2, principle 10) |
| **Screenshots come only from the made-up sample exam,** never real papers | Public repository; AGENTS.md |
| **Screenshots are taken after Phase I and the rename to *CAM2 Grading*** | Earlier shots would show the old name and any Phase I changes |
| **One sample exam serves the guide, the test guide and the public sample download** | People who download the sample see exactly what the guide shows |

## 2. Guide structure (each language)

1. **Quick start** (one page, as today).
2. **What CAM2 does.** A large Step 4 screenshot next to a sample student report and the Excel gradebook. Offline, nothing to install, papers stay on the computer.
3. **Before the exam.** Nothing to set up in CAM2. Separate answer sheets are the quickest set-up. Leave writing room inside each answer space.
4. **Choose how to scan.** A table, matched to the in-app "How to scan your papers" tips (`guide.1`–`guide.9`), not a second version of them:

   | Method | Best for | What CAM2 does |
   |---|---|---|
   | Whole class in one PDF | Most exams | Cuts it into each student's paper |
   | Several batches | More sheets than the feeder takes | Joins the PDFs |
   | One file per student | Papers already split | Matches names from file names |
   | Phone photos | No copier | Takes JPEG or PNG pages |
   | Folded A3 booklets | Printed booklets | Unfolds each booklet |

   Scanner settings: PDF, 200–300 dpi, 2-sided, greyscale.
5. **Step 1 — Exam & scans.** Screenshot, 3–5 bullets, and the page-fix tools.
6. **Step 2 — Set up questions.** Marks, rubric or mixed; drawing boxes; sections, choice questions and highest levels.
7. **Step 3 — Match names.**
8. **Step 4 — Grade.** Marks buttons and rubric cards, criterion tabs, notes and highlights, the class grid.
9. **Step 5 — Review & export.** The review table, report options, exports.
10. **Where your work lives.** The session folder; USB stick or cloud drive; what a save warning means; carrying on later or on another computer.
11. **Common questions.** A late student, an upside-down page, a box in the wrong place, a file open in Excel, quitting.

### Parts that need more than the app shows

| Topic | Treatment |
|---|---|
| **Folded booklets:** page count, "inside sheets first", fronts or backs upside down | A diagram of one folded sheet and how it scans. Use `tools/make_sample_scans.py`'s A3 booklets |
| **Papers cut from one long stack:** removing or adding a page shifts every later paper (`pages.stream_note`) | A warning box in Step 1 |
| **What locks once grading starts:** scans can't be replaced and graded papers' pages can't change; late papers use "Add more papers" | A short box in Step 1 |
| **Drawing boxes** for a first-time user | Annotated screenshots of the sample's box cases (§3.3) |
| **Marks, rubric or mixed:** "Where to start" is only a starting choice; levels are never added to marks; marks questions can count towards a criterion | A short explanation with the sample's three sections |
| **Choice questions:** best *n* or "I choose" | One line with a screenshot |
| **Highest levels (tiered questions)** | A screenshot of a capped question and the section shortcut |
| **Step 5's three results:** calculated, total on report, and the final level the teacher types; which report option prints what | An annotated screenshot |
| Note and comment limits per page | One line; the app shows the counts |

## 3. The sample exam

`tools/make_sample_exam.py` is rewritten around one theme, **Water**, like an MYP interdisciplinary paper, so every subject sees a familiar question type. A4, **9 pages per student**: the cover, then pages 2–9 as below. 8 students: 7 in the class PDF and one in `late-paper.pdf`, so the class grid fills 4 columns once the late paper is added. Greyscale scans at 200 dpi, about 7.5 MB per language. English and Japanese, as now. **Built 2026-11-27** on `phase-j-sample-exam`.

### 3.1 Criteria

Three made-up MYP-style criteria on levels 0–8, bands 0, 1–2, 3–4, 5–6, 7–8. The descriptors are **our own wording**, not IB's published text.

| Criterion | Name |
|---|---|
| A | Knowing and understanding |
| B | Analysing and evaluating |
| C | Communicating |

The rubrics go in the sample in two places:

- `rubrics.xlsx`, to upload in Step 2.
- A **cover page** on the question paper, "How you will be assessed", listing the three criteria with their bands. It is page 1 of each paper and has no answer boxes, as on many real MYP papers.

### 3.2 Questions

Each section belongs to one criterion; the essay also counts towards B, to show a question graded on two criteria.

| Q | Section / criterion | Type | Graded with | What it shows |
|---|---|---|---|---|
| 1 | A · Criterion A | **Multiple choice**, 5 items | Marks | The simplest box; class grid comparison |
| 2 | A · Criterion A | **Label a diagram** (water cycle, 4 labels) | Marks | One box round a whole diagram |
| 3 | A · Criterion A | **Fill in the blanks** | Marks | A box that includes the question text |
| 4 | A · Criterion A | **True / false or matching** | Marks | Quick marks grading |
| 5 | A · Criterion A | **Calculation with working** (rain-tank volume) | Marks | Method marks; a comment on the working |
| 6 | B · Criterion B | **Plot a graph** from a data table, then describe the trend | Marks | Large box on a printed grid; a highlight |
| 7 | B · Criterion B | **Source-based structured question**: a short source, then parts a, b, c | Rubric level | One stem for several parts: box the source, then **+ Add another box** |
| 8 | C · Criterion C | **Annotated design sketch** (a water-bottle label) | Rubric level, **capped at 4** (a foundation task) | Tiered question; notes placed on a drawing |
| 9 / 10 | C · Criteria B and C | **Essay, choose one.** Each has its own answer space: Q9 on page 7 running onto the top of page 8, Q10 on the bottom of page 8 running onto page 9 | Rubric levels | Choice group; two boxes across two pages; a tab per criterion; notes and highlights; per-page limits |

**Tiered choice in the essays:** Q9 is the standard prompt, capped at **6** on both criteria; Q10 is the extension prompt with the full 0–8. Section C's heading shortcut is shown setting a ceiling, then lifted for Q10.

In Step 5, **Overall criterion results** gathers each criterion's marks and levels, and the teacher types the final level for A, B and C. Section weighting applies to the marks only.

### 3.3 Built into the papers for screenshots

- One student writes past the printed answer space; one crosses out an answer (why boxes should be generous).
- The essay runs onto a second page.
- Each essay is written by one student only, at that student's levels, so the class grid shows no copied essays (short answers still come in strong, middling and weak versions).
- Strong, middling and weak answers; one question left blank (*Not answered*); one student answers both essays; one sits the exam late (a separate PDF, for "Add more papers").
- One upside-down page in the class PDF, for the Step 1 page-fix screenshot.
- Graph points and the sketch are drawn as simple lines in the handwriting colour.

### 3.4 Test guide

`Test-guide.pdf` is rewritten for the new paper, with expected results worked out by plain arithmetic as now. It keeps the checks the current one covers: sections and weighting, the choice group, *Not answered*, ceilings, and half-up rounding of the final percentage. As built, the two runs are:

- **Exam 1, as designed:** marks on Q1–Q6 (/30), rubric levels on Q7–Q10 with the ceilings above, sections A, B and C, the essays counting the best. Weighting gives A and B 50% each, and Section C, with no marks, no share. Upside-down page, late paper and ceilings are checked here.
- **Exam 2, marks on every question** (/50), started from **Marks**: never sent to a rubric screen; the essays use "I choose which count", and the student who wrote both waits for the teacher's choice. Criteria and sections are then added without slicing again, and weighting is 34/33/33.

(The plan first said the second run would give only Section C marks; Q7 in Section B is a rubric question, so that run would still have been mixed.)

## 4. Build changes

- `tools/build_quick_guide.py`: page 1 stays the quick start; the one-page check becomes a check that page 1 fits. Screenshots per language from `tools/guide_images/en/` and `tools/guide_images/ja/`.
- `tools/build_windows.py` and `tools/build_mac.py`: READ ME FIRST says "a short guide" instead of "a one-page guide" / 「1ページの案内」.
- A repeatable capture step (a script or a written checklist) that opens the sample in each language and takes the same shots, so they can be redone whenever a screen changes.
- PDF size stays small enough to email: screenshots as compressed PNG or JPEG at print resolution.

## 5. Order of work

1. Rewrite the sample exam generator and test guide; check the expected results in the app.
2. Write the guide text in English and Japanese, with placeholders for pictures.
3. After Phase I and the rename: take the screenshots in both languages and build the guide.
4. Check the built guide on both platforms' builds in Phase J.

## 6. Still open elsewhere

Phase I is in progress in CAM. Phase H left: no frozen trial build, and Japanese wording not reviewed by a native speaker. The Step 1 heading and Step 5 table layout bugs and the two Draft strings were fixed on 2026-11-27 (`fix/layout-step1-step5`).
