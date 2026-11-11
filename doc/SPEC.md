# CAM2 — Product Specification

**Status:** agreed direction, 2026-11-11. **Applies to:** the first official release, `v1.0.0`.
**Current build:** `v0.3.2-dev` (session format 2).

This document says what CAM2 is, who it is for, and what the first official release must do. It is the reference for deciding whether a request belongs in CAM2. The work needed to get there, in order, is in [PLAN.md](PLAN.md). How the code is laid out is in [ARCHITECTURE.md](../ARCHITECTURE.md).

Each feature below is marked **Built** (in `v0.3.2-dev`) or **1.0** (to be built for the first official release).

---

## 1. What CAM2 is

CAM2 is a small offline app in which a teacher grades one piece of class work at a time, on screen, and gets a PDF report for each student and an Excel gradebook.

It runs in two ways, from the same code:

| | Standalone | Inside CAM |
|---|---|---|
| Who | Any teacher, with no CAM and no training | A teacher using CAM (Criterion Assessment Metrics) for the year's record |
| How it starts | Double-click the download | CAM opens it on one task |
| What it grades | A scanned exam | A scanned exam, an assignment, or a draft |
| Where results go | Student PDFs and the Excel gradebook | The same, and back to CAM's records and term comments |

**The goal of 1.0:** CAM2 is the only grading tool in CAM. CAM's grading workspace (CGW, `cam_grading_workspace/`), with its Google sign-in and Drive access, is removed. Everything a teacher graded there is graded in CAM2.

**Division of work.** CAM holds the year: classes, terms, grades, term comments and where files live. CAM2 grades one task and hands the results over. CAM2 never contacts Google or any other service; files reach it as downloads or through a synced folder.

## 2. Principles

These decide every request. A feature that breaks one needs a stated reason.

1. **One task at a time.** Nothing in CAM2 spans classes, tasks or the school year. That belongs in CAM.
2. **No training.** Five guided steps, one instruction at a time. Prefer what the app can work out over a new setting, and hide what doesn't apply.
3. **Marks stay the simplest path.** A teacher who only wants marks never sees a criterion, rubric or final level.
4. **The teacher decides.** Rubric levels are reported as given and never averaged, totalled or added to marks. Final levels are typed by the teacher. Calculated results stay distinct from the teacher's overrides.
5. **Teacher work is never lost.** Every change saves at once, safely. A failed save stays visible until the work reaches disk. USB removal, cloud-sync conflicts and files open in Excel are everyday conditions.
6. **Offline and private.** Localhost only, no accounts, no services, no telemetry.
7. **Nothing to install.** One zip for Windows, one for Apple Silicon Mac.
8. **English and Japanese** throughout: screens, messages and reports.
9. **Small.** Flask, plain JavaScript modules, PyMuPDF, Pillow, openpyxl. No framework, build step or new dependency without a bug that needs it.
10. **The standalone app stays an exam grader.** What CAM needs must not add choices for a teacher who only grades exams.

## 3. Kinds of task

| Task | What it is | Answer boxes | Grades | Available |
|---|---|---|---|---|
| **Exam** | Scanned papers with the same layout for every student | Yes, drawn once on the grid | Marks, rubric levels, or a mix, per question | Standalone and from CAM. **Built** |
| **Assignment** | Each student's submitted work: PDFs and images of any length | None; the whole submission is the item | One level per criterion | From CAM only. **1.0** |
| **Draft** | As an assignment, for feedback | None | No grade; comments and annotations only | From CAM only. **1.0** |

CAM tells CAM2 which kind a task is. The standalone start screen offers only exams. Whether standalone teachers ever get assignments is to be looked at again after 1.0 has been used.

## 4. What the teacher can do

### 4.1 Bring in the work

- **Built:** one PDF of the whole class, one file per student, or photos of each page. Batches joined. Folded A3 booklets unfolded. Page fixes (move, turn, remove, blank page, booklet sheet fixes). Late papers added at any time.
- **Built:** A4, B5 (ISO and JIS), A3, Slide 16:9 and Slide 4:3, detected and confirmed. **1.0:** Slide 16:10.
- **1.0, assignments and drafts:** a folder of submissions where a student may have **several files**, PDFs and images of different sizes, joined into one paper in a stated order. Files are matched to the class list by student ID or full name in the file name, or by a subfolder per student. Papers may differ in length without a warning.
- The session folder is portable and holds a copy of the work, so it opens on another computer.

### 4.2 Set up (exams)

- **Built:** draw answer boxes on a 5 mm grid on the first paper; several boxes per question, across pages; a name box; question order; sections; choice groups ("answer 2 of 3"); the teacher's own rubrics, typed, pasted or uploaded; marks and criteria per question, mixed freely.
- **1.0, tiered papers:** a highest permitted level per question and per criterion, with a shortcut on a section heading. A question aimed at levels 5–6 can earn 0 to 6 and never 7 or 8.

Assignments and drafts skip box drawing. Their criteria and rubric come from CAM.

### 4.3 Match names

- **Built:** class list from Excel, CSV or paste; names matched from file names; the handwritten name crop beside a search box; unmatched papers allowed.
- **1.0:** replacing a class list never moves one student's results onto another.

### 4.4 Grade

- **Built:** one question across every paper. Marks buttons or rubric band cards. Questions on several criteria graded one criterion at a time. Not answered. A comment per question and an overall comment, with length limits. Hide names, shuffle papers, show ungraded only. See whole page. Adjust a box and re-slice that question.
- **1.0, annotations:** for long, structured answers in languages, history and economics, and for art.
  - **Numbered comment stamps**, placed exactly where the teacher clicks, with their text in a numbered list. A stamp can be typed directly or dragged from the quick-comment list.
  - **Highlights**, drawn like answer boxes: dragged on the same 5 mm grid and snapping to its cells, in yellow, blue or pink.
  - Both follow the student's writing when a box is adjusted, print on the report, and reach the gradebook as text. The scan and crop files are never changed.
- **1.0, class grid:** the whole class at once, in 2, 3, 4 or 5 columns, as **This question** (each student's answer) or **Whole papers**. Clicking a card opens that student for grading and annotating, and returns to the same place in the grid.
- **1.0, assignments and drafts:** the submission is read page by page with the same stamps and highlights. An assignment gets a level per criterion; a draft gets none. Each student has a **Late** tick. **Partners** can be linked so that group work shares one grade and comment.

### 4.5 Review and export

- **Built:** a review table with calculated results, the total or percentage on the report, final levels, overall comments, section results and weighting. Report options chosen per exam, with a one-report preview. One PDF per student and the Excel gradebook, in English or Japanese.
- **1.0:** the total on the report is checked against the exam's maximum. Long answers run across report pages at a readable size instead of shrinking to fit. Stamps, highlights and note text print with the answer. A report layout for whole-page submissions.

### 4.6 Work with CAM

- **Built:** CAM opens one exam in CAM2 with its folder and class; CAM reads the session's results, comments and name crops; the teacher is guided back to CAM after sending.
- **1.0:** CAM opens assignments and drafts in CAM2 the same way. Their grades, comments, note text, Late flags and partner groups reach CAM's gradebook, its Classroom entry routine and its term-comment prompts with nothing lost and nothing duplicated on a re-send.
- **1.0:** CAM no longer contains the grading workspace, OAuth set-up or Drive code. Marks and comments already stored in CAM stay.
- The two apps move together: CAM2 is tagged first, then pulled into CAM with `git subtree`. CAM's copy is never edited in place. A CAM that is too old for a session says so and leaves it alone.

### 4.7 Saving

**Built**, and unchanged in meaning: atomic writes with read-back, retry on sync locks, an emergency copy on this computer, conflict-copy detection, a second-computer warning, a wipe guard and daily backups. **1.0:** a save failure stays on screen until the affected file is saved, and edits still waiting to save are never dropped by moving to another screen.

## 5. What replaces each workspace feature

| CGW feature | In 1.0 |
|---|---|
| Grading PDFs and images of students' work | Assignment and draft tasks in CAM2 |
| Drafts: comments only | Draft task |
| Criterion grades for an assignment | Assignment task, one level per criterion |
| Strengths / Areas to develop keywords | CAM2's quick-comment list and numbered stamps |
| Gallery of all students' work, 2–5 columns | Class grid |
| Several files per student | Joined into one paper |
| Partners sharing one grade and comment | Linked partners in CAM2 |
| Late badge and tick | Late tick in CAM2 |
| Anonymous grading | Hide names and Shuffle papers |
| Matching files to students | CAM2's matching by ID or name, and the manual matcher |
| CSV to CAM, then Classroom entry | CAM2 sends the same information to CAM |
| Google Drive browsing and sign-in | **Removed.** Work is downloaded, or sits in a synced folder |
| Docs, Slides and Word previews | **Not in CAM2.** The teacher's Apps Script converts them to PDF first |
| Videos | **Not in CAM2.** Watched online; the grade and comment are entered in CAM |
| Omit page ranges for a whole assignment | **Not carried over.** Look again if teachers miss it |
| Older drafts of the same work | The newest file is used; an earlier one is its own draft task |

## 6. Data and compatibility

- A session is a folder: `cam2_session.json`, `grades.json`, scans, crops, backups and reports. Paths inside it are relative.
- **Identity comes from IDs,** never from position, display order, shuffle order or a row number in a class list. Results stay with the same student, question and criterion through reordering, renaming, deletion, re-slicing, list replacement and late papers.
- 1.0 uses **session format 3**. Sessions in formats 1 and 2 open and keep their meaning. An older CAM2 or CAM refuses a format 3 session visibly and does not rewrite it.
- Annotation positions are stored as fractions of the scanned page, so they don't depend on zoom, screen scaling or how a crop was cut. Highlights snap to the grid when drawn, and are stored the same way.

## 7. The screens

The current design works and stays: the start screen, the five steps, the grading card, the review table. Changes for 1.0 are limited to what the new features need:

- Step 2: the highest-level choice beside each criterion.
- Step 4: Pan / Add note / Highlight tools, the numbered note list, and the Class grid with its view and column controls. The grading card and viewer must still fit a school laptop with these added.
- Assignments and drafts reuse the same screens with what doesn't apply hidden: no box drawing, and no grade controls on a draft.

## 8. Not in 1.0

- OCR, selecting handwritten text, AI feedback or AI grading.
- Freehand drawing, arrows, tick and cross stamps, text typed straight onto the image.
- Anything spanning tasks, classes or years; portfolios over time (CAM's job).
- Google or any other online service from CAM2.
- Built-in rubrics, half marks, Word import, matching names by paper order.
- Calibration mode, class statistics beyond what exists, straightening crooked scans, keyboard grading, session compacting. These stay in the backlog in [PLAN.md](PLAN.md) §13.
- Signed or notarised packages, and an Intel Mac build.

## 9. When 1.0 is done

1. Every phase in [PLAN.md](PLAN.md) has passed its acceptance checks, with what was and wasn't verified written down.
2. No open data-integrity finding from any repository review.
3. One real exam, one real assignment and one real draft have each been graded in CAM2 through CAM, and the results in CAM compared with what the workspace would have produced.
4. CAM has been released without the grading workspace, on the same CAM2 tag as the standalone downloads.
5. Windows and Apple Silicon packages built from one tagged commit have run the new features, in English and Japanese.
6. README, ARCHITECTURE, CHANGELOG, the bundled guides and this document describe what was built.

## 10. Still to decide

| # | Question | Needed by |
|---|---|---|
| 1 | How assignment and draft results reach CAM: the workspace's CSV format (least change in CAM) or the session bridge that exams use | Before Phase H in the plan |
| 2 | Is 8 notes per answer enough for a three-page essay? Try it on the essay sample | During Phase D |
| 3 | In what order are a student's several files joined: file name, or newest first as the workspace lists them? | Before Phase G |
| 4 | Does a draft's student PDF get made at all, or only when the teacher asks? | Before Phase G |
| 5 | The app's name, *CAM2 Exam Grading*, once it also grades assignments inside CAM | Before release |

## 11. Documents

| Document | What it holds |
|---|---|
| [SPEC.md](SPEC.md) | This: what CAM2 is and what 1.0 must do |
| [PLAN.md](PLAN.md) | The one plan: open items, phases to 1.0, requests and backlog, progress |
| [Exam-Section-Plan.md](Exam-Section-Plan.md) | The rules for sections, mixed grading, weighting and the report, as built |
| [ARCHITECTURE.md](../ARCHITECTURE.md) | The code map |
| [CHANGELOG.md](../CHANGELOG.md) | What changed in each version |
| [AGENTS.md](../AGENTS.md) | Rules for code review |
| `repository-review-*.md` | Review findings |
| [archive/](archive/) | Earlier plans, kept for their reasoning: the original build plan, the feedback document and the first next-release plan |
