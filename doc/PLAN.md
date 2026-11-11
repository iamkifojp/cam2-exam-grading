# CAM2 — Plan to the first official release (v1.0.0)

**Agreed:** 2026-11-11. **Status:** planned; no application code has changed under this plan.
**What 1.0 must do:** [SPEC.md](SPEC.md). **Coding agent:** Claude Opus, one phase per session. Codex Astra for an independent review of a finished phase, following [AGENTS.md](../AGENTS.md).

This is the only plan. It replaces the root `PLAN.md`, `Feedback-and-Upgrades.md` and `doc/next-release-plan.md`, which are kept in [archive/](archive/) for their reasoning. Where they disagree with this document, this document is right. [Exam-Section-Plan.md](Exam-Section-Plan.md) stays the authority for mixed grading, calculations and report options.

## 1. Decisions

| Date | Decision |
|---|---|
| 2026-11-11 | **One release.** Everything below ships together as `v1.0.0`. No public test build in between. Trial builds for the teacher's own checks are allowed and are not releases |
| 2026-11-11 | **1.0 replaces CAM's grading workspace (CGW) completely.** This reverses the 2026-11-10 plan, which left the workspace in place |
| 2026-11-11 | **Highlights snap to the 5 mm grid** and are drawn like answer boxes. **Comment stamps are placed freely** |
| 2026-11-11 | **Assignments and drafts open from CAM only.** The standalone start screen stays exam-only |
| 2026-11-11 | **CGW features CAM2 must cover:** several files per student, partners sharing one grade, a Late flag. Omitting page ranges is not carried over |
| 2026-11-10 | Class grid has This question and Whole papers views, with 2, 3, 4 or 5 columns |
| 2026-11-10 | Japanese wording is accepted on colleagues' use. New text still needs English and Japanese |
| 2026-11-06 | Fix the level buttons moving, and the Total on report box, in the next update |
| 2026-11-05 | Notes are numbered and kept apart from the question's comment. Limits: 8 list comments, 120 characters per note, 300 per question comment, 600 overall |
| 2026-11-05 | Videos are watched outside CAM2. Docs, Slides and Word files are converted to PDF by the teacher's Apps Script |
| 2026-11-05 | CAM2 never contacts Google (CAM's D17) |

**Boundaries.** Flask on localhost, plain JavaScript modules, the portable session folder, PyMuPDF reports, PyInstaller builds. No framework, CDN, OCR, service or new dependency. Protect atomic saves, emergency copies, conflict checks and file-lock handling.

## 2. Where things stand (checked 2026-11-11)

| Item | State |
|---|---|
| Standalone `main` | `2157409`, clean, matches GitHub |
| Latest release | `v0.3.2-dev` (tag `4423090`), Windows and Apple Silicon zips |
| App / session versions | `0.3.2-dev` / format 2 |
| Tests | 354 run, all pass, 1 skipped (the JavaScript syntax check; Node isn't on this Mac's PATH). Run with `build/venv/bin/python` |
| CAM's vendored copy | `0.3.2-dev-cam.1`, at `920fea1`: two commits main doesn't have |
| Pull requests | None open. #1 and #2 merged |

### Open from earlier phases

The original build (Phases 1–5) and exam sections (Phases 1–7) are finished. These are still open, and Phases A and B close them before anything new is built:

| # | Open item | Source | Closed by |
|---|---|---|---|
| 1 | Leaving the rubric editor within 600 ms can erase every rubric | Review 2026-11-06, P1 | A1 |
| 2 | Replacing a reordered class list gives results to the wrong student | Review 2026-11-06, P1 | A2 |
| 3 | A new criterion inherits a deleted criterion's grades | Review 2026-11-06, P1 | A3 |
| 4 | An unrelated successful save hides unsaved grades | Review 2026-11-06, P2 | A4 |
| 5 | `e39afdc` (report-value guard) and `920fea1` (return-to-CAM guidance) are in CAM but not in standalone main. Branches `codex/report-total-phase4` and `codex/cam-host-finish` | Maintenance | B1 |
| 6 | Level buttons move after a grade, so a second click misses | Found 2026-11-06 | B2 |
| 7 | Merged branch `note-report-total-box` still on GitHub | Housekeeping | Delete after B1 |

Not tried item by item, and accepted on colleagues' use: the Windows first run, a Mac that has never run CAM2, and the Japanese names of the Mac approval buttons.

## 3. Order of work

| Phase | What | Repo | Size |
|---|---|---|---|
| **A** | Four data-integrity fixes | CAM2 | Small–medium |
| **B** | Maintenance commits, level buttons, Slide 16:10 | CAM2 | Small |
| **C** | Session format 3 and tiered levels | CAM2 | Small–medium |
| **D** | Annotations and long-answer reports | CAM2 | Large |
| **E** | Class grid | CAM2 | Medium |
| **G** | Whole-submission tasks | CAM2 | Large |
| **H** | Assignments, drafts, Late and partners | CAM2 | Medium |
| **I** | CAM takes CAM2 as its only grader; the workspace is removed | CAM | Large |
| **J** | Verification and release of both apps | Both | Medium |

Each phase has an exit check. Don't start a phase while an earlier one has anything open; list what is open first and get the teacher's answer. (There is no Phase F: its content is now in I and J.)

**Risk of one release.** Nothing reaches colleagues until the end, so mistakes in A–E surface late. To limit that: finish and verify each phase in the browser before the next, keep each phase on its own branch and pull request, and make a trial build after E and after H for the teacher to try on real scans.

---

## 4. Phase A — keep teacher work safe

Read `ARCHITECTURE.md`, `CHANGELOG.md`, `Exam-Section-Plan.md` and both repository reviews. The October 31 findings are fixed; don't reopen them without a demonstrated regression. For each item: add a focused failing test, make the smallest fix, and try the browser path.

### A1. Flush rubric edits before leaving their editor

**Now:** `static/js/main.js:goTo` flushes `saveQuestions`, then replaces `app.draft`. `static/js/step2.js:saveRubrics` later reads the discarded draft and can send `{}`; `workflow.set_rubrics` then erases the rubrics and the questions' criterion assignments.

- Expose and await the rubric saver before navigation clears the draft, including Save & close and switching sessions.
- A flush must tell success from a caught failure. Keep the editor and its draft when saving fails.
- Capture the edited data and its owner before any await. Apply server-assigned IDs to that same draft, not whichever screen is now showing.
- When question and rubric changes are both pending, a stale question payload must not restore removed criterion assignments.

**Accept:** edit a descriptor and leave within 600 ms; reopen and check every rubric, descriptor, assignment and grade. Repeat with a blocked save: navigation must not drop the edit. Include close and session switch.

### A2. Don't keep row-based matches when a class list is replaced

**Now:** `engine/roster.py:_roster` gives IDs by row; `engine/workflow.py:set_roster` keeps a match whenever the ID still exists.

- Clear old matches on replacement, then run the existing file-name matching and the manual matcher. A reused row ID is not proof of identity.
- Grades, comments and crops stay with their paper. Show that names need checking again.

**Accept:** Alice and Bob with different results; replace the list reversed, and with a row inserted first. No paper silently takes another's name. Rematch, then check PDF and Excel after reopening. Include pasted and uploaded lists, and an ambiguous name that must stay unmatched.

### A3. Never reuse a deleted criterion's ID

**Now:** `engine/workflow.py:set_rubrics` gives `r1`, `r2` … by position; old levels and final levels stay under those IDs.

- New criteria get fresh IDs (`model.new_session_id()` is enough). Existing criteria keep theirs through reorder and rename.
- A removed criterion's stored results must not appear under a new one. Don't delete historical work as a shortcut.

**Accept:** grade `r2`, enter its final level, delete it, add a differently named criterion. Both kinds of level start blank, after reopening and in exports. Reorder and rename keep the original values.

### A4. Keep a save failure visible until that file is saved

**Now:** `appstate.py:save_config` and `save_grades` each clear one shared flag; `static/js/store.js:act` clears the banner after any success.

- Track configuration and grades separately, and derive the existing saved/failed status from both.
- Clear a file's failure only when its pending content is saved. Check the direct handlers in `main.js`, `step2.js`, `step4.js` and `step5.js` as well as `act`.
- Keep in-memory edits and the emergency copy. Closing must not present unsaved work as saved.

**Accept:** fail a grade save with a synthetic conflict copy, then save configuration: the old grade is still on disk and the warning stays. Resolve and retry: only then it clears. Test the reverse, both together, a missing folder, retry, emergency restore and close.

**Exit:** four regressions pass, normal saving works, browser behaviour recorded.

## 5. Phase B — maintenance and small fixes

### B1. Bring the CAM maintenance commits into main

Cherry-pick `e39afdc` then `920fea1`, keeping main's documents. Review the diff before committing.

- Report overrides show the calculated value as a hint; focusing an override selects it.
- A total is between 0 and the exam's maximum; a weighted percentage between 0 and 100. Clearing restores the calculated value. Invalid input leaves the saved value alone.
- Hosted Save & close and return-to-CAM guidance stay. A standalone session shows no host.
- Use 1.0's own version number; `0.3.2-dev-cam.1` is the maintenance build.

**Accept:** replace, clear and reject overrides on a marks exam and a weighted mixed exam; preview, export, re-export, reopen. Hosted send, save and close, lock release, and standalone close, in both languages. Then delete the three stale remote branches.

### B2. Level buttons stay still after a grade

In `static/js/step4.js:setGrade`, use `focus({preventScroll: true})` where **Next paper** is focused.

**Accept:** on a short window, choose a level and change it at once; both clicks save. Enter still moves on. Recheck after Phase D adds controls.

### B3. Slide 16:10

Extend `engine/slicer.py` (sizes, grids, shape detection, JPEG crop choice), the Step 1 picker, translations, tests and guides. Search every 16:9 and 4:3 check.

- Landscape 254 × 158.75 mm, about 51 × 32 cells at 5 mm, stored in the same convention as the other sizes.
- Recognised on landscape PDF pages of any physical size, after the paper sizes. Photo-only pages and pictures are never slides.
- Saved 16:9 sessions are not reread as 16:10.

**Accept:** 16:10 decks at two sizes; 16:9 and 4:3 unchanged; photo PDFs; paper and portrait pages. Draw a known rectangle and compare the preview with the exported crop.

## 6. Phase C — format 3 and tiered levels (F1)

### C1. One format change for the whole release

Raise `engine/model.py` to version 3, covering everything Phases C to H store: level ceilings, notes, highlights, task kind, Late flags and partner groups. Settle those shapes on paper before writing the upgrade, so the format changes once.

- Versions 1 and 2 upgrade with every ID, grade, final level, comment, generated quick-comment line, override, choice, box, section and report option intact. New fields start absent or empty.
- If only one of the two files was written before an interruption, reopening and recovery still work.
- An older CAM2 refuses version 3 visibly. Keep a pre-upgrade backup of the session.

### C2. A highest level per question and criterion

Store `level_caps: {"criterion-id": 6}` on the question. No entry means the whole scale. It is a ceiling, not a band: a question capped at 6 can earn 0 to 6.

- **Step 2:** beside each ticked criterion on a rubric question, *All levels* or the top of each of that rubric's bands. Nothing is hardcoded to MYP pairs.
- **Section shortcut:** on a section heading, set a ceiling per criterion for its rubric questions. It changes those questions; it is not a second setting. Validate the whole change before applying any of it.
- **Step 4:** show only permitted levels and a short *Up to 5–6*. The grade stays on the rubric's scale (`6 / 8`). Final levels are not capped.
- **Server:** `set_grade` refuses a level above the ceiling. `set_questions` refuses a ceiling below a grade already given. A rubric edit that leaves a ceiling on no band's top asks for a correction.
- Marks questions are untouched. Removing a criterion from a question removes its ceiling.
- Reports don't mention ceilings. The gradebook's reference sheet lists them.

**Accept:** two criteria with different ceilings on one question; shortcut plus an exception; custom bands; an above-ceiling grade through the screen and the route; lowering below a grade; rubric edits; rename, reorder, delete, add; reopen; mixed choice groups; totals unchanged.

## 7. Phase D — annotations (F2)

### D1. Ownership, storage and geometry

Notes and highlights are stored in `grades.json` beside that student's question comment and shared across the question's criteria. Each has a stable ID; a note's number comes from its place in the list.

```json
{
  "annotations": [{"id": "…", "page": 1, "x": 0.25, "y": 0.40, "text": "Explain this inference.", "type": "growth"}],
  "highlights": [{"id": "…", "page": 1, "x": 0.18, "y": 0.38, "w": 0.40, "h": 0.03, "colour": "yellow"}]
}
```

- Pages are one-based, as in `page1!`. Positions are fractions of the scanned page after its rotation, independent of CSS pixels, screen scaling and crop size.
- **One geometry for screen and report.** The engine returns an answer's *parts*: source page, rectangle, scale, stacked offset and divider gap. Build it on `range_to_bbox`, `crop_boxes` and `stitch_vertical` in `engine/slicer.py`. Handle several boxes on a page, unequal widths, overlaps and several pages. A point on padding or a divider is not a page position.
- **A whole page must be a valid part.** Phase G shows submissions as full pages with the same layer, so nothing here may assume a crop.
- Edits go through the guarded grade save. Capture IDs and the draft before a request; flush note text before changing student, question or criterion, opening the grid, previewing, exporting or closing. A refused save keeps the draft and its owner. A late response never overwrites a newer list.

### D2. What the teacher does

- **Tools in the viewer:** Pan, Add note, Highlight.
- **Notes:** click a spot and type, or drag a quick comment onto it. A numbered stamp marks the spot, exactly where placed; the text sits in an editable numbered list. Drag a stamp to move it. Deleting renumbers. Changing the quick-comment list never changes placed notes.
- **Highlights:** with the tool on, drag as for an answer box. The rectangle **snaps to the 5 mm grid cells**, reusing the snapping in `static/js/boxes.js`. Yellow, blue or pink, with no grade meaning. Click one with the tool on to remove it. The snapped rectangle is stored as page fractions, so a later grid change can't move it. A session on an older coarse grid snaps to 5 mm cells all the same.
- Pointer events throughout, for mouse, trackpad, touch and stylus. Zoom, pan and the grade controls keep working on a tall answer.
- Authoring is in the answer view. Whole-page view is for context, with a clear way back.
- **Quick comments** become a list to place, not to tick. Strength and Area to develop stay as optional types, shown with text as well as colour. Text already written by ticks stays as ordinary comment text; old `keywords` and `keyword_text` no longer regenerate, delete or duplicate it. Existing lists are kept, including long ones.
- **New lists start with four:** *Well explained.* (strength), *More explanation needed.*, *Incomplete answer.*, *Hard to read.* (areas to develop), in both languages.
- **Limits:** 8 list comments, 8 notes per answer, 120 characters per note. Highlights don't count. Existing text and lists are never cut; they can be kept or shortened, not grown. Count characters the same in Python and JavaScript, and respect Japanese input composition.

### D3. When a box is adjusted

Notes follow the writing, because page positions don't change. Scan and crop files are never altered.

- Inside the new crop: unchanged. Highlights are clipped to each part.
- Outside it: shown at the nearest point in a box on the same page, or at the start of the answer, marked *Check position*. The stored position stays until the teacher moves the stamp or confirms the place, which then records that place. Widening the box restores the original.
- A fully excluded highlight stays stored and is listed so it can be inspected or removed.
- Notes and highlights count as teacher work in `grades_mass`, `_has_work`, the page-fix and scan-replacement guards, progress markers and emergency recovery. Deleting one on purpose still works under the wipe guard.

### D4. Reports and gradebook

`engine/reports.py:_question_with_image` fits a whole stitched answer into one rectangle. A three-page essay becomes unreadable.

- Short answers print as now. Long answers continue across report pages at a readable width, part by part, splitting an oversized part with nothing missing or repeated.
- Stamps and highlights are drawn with PyMuPDF at the same page positions as on screen. Each note's text prints once, under the question, after the teacher's comment.
- With a section's images off, the note text still prints. Every report option is respected.
- The gradebook adds numbered note text to the question's comment cell; the stored comment is untouched. Step 5's comment marker counts notes.
- Preview, export and re-export agree. Close image and PDF resources per student.

**Accept:** a third-of-a-page answer, a half page, a one-page letter, two- and three-page essays, several boxes on one page, rotated and landscape scans, every slide size. Marks at edges, on each essay page and beside dividers. Zoom, display scaling, re-slicing, excluded marks, criterion switching, fast navigation. Reopen and compare positions and owners. Both languages in preview, PDF and Excel. Annotation-only work, a conflict failure and emergency restore. Try the 8-note limit on the three-page essay with the teacher and agree a change if it is too few.

## 8. Phase E — class grid (F11)

The interaction comes from CAM's workspace: student cards, a column control, enlarge on click. Reuse the idea, not its Drive or group code.

- **Class grid** in Step 4, with a clear way back. Views **This question** and **Whole papers**; columns **2, 3, 4, 5**, default 3, remembered on this computer. A narrow window shows fewer without losing the choice.
- **This question:** a card per student with the answer in a bounded preview, the grade or status for the current criterion, and its annotations. A long answer shows its part count.
- **Whole papers:** a card per student with a page preview, page count and small page arrows. Other pages load on demand. Clicking opens that student at that page; the current question stays the one being graded, and says so.
- Clicking a card opens that student, question and criterion in the normal view. Coming back restores the view, columns and scroll position. There is no second grade model and no batch grading.
- Order follows paper or shuffle order. Sorting by grade is offered in the question view only, for the current criterion or marks, with Ungraded and Not answered apart. Filters show *n of class* so a filter can't look like missing papers.
- **Hide student names** applies to labels, titles and accessibility text. Identity always comes from IDs, never card position.
- Thumbnails are bounded and cached by student, question or page, and crop revision. Cards load as they near the screen, and full-size images are released when they leave it.
- Pending edits are flushed under the same rules as A and D before opening a card.

**Accept:** a made-up class of 30–40 with long essays and photo slides; both views; every column count at laptop and 32-inch widths; page arrows; return from grading; names hidden; shuffle; sort; filters; late papers; re-slicing; refused comments. Watch image memory through repeated scrolling.

## 9. Phase G — whole-submission tasks

A task with no answer boxes: each student's submission is one item, read page by page. This is what lets CAM2 take over from the workspace. Full reasoning: [archive/feedback-and-upgrades.md](archive/feedback-and-upgrades.md) F5.

- **Task kind.** The session records `exam`, `assignment` or `draft`. Absent means exam. Only the hand-over from CAM (`engine/host.py`) sets the other two. The standalone start screen doesn't change.
- **Bringing work in.** A folder of submissions. A student may have several files, PDFs and images of different sizes, joined into one paper in a stated order (SPEC §10, question 3). Match by student ID or full name in the file name, or a subfolder per student; the rules in CAM's `submission_identity.py` are the reference. Unmatched files stay as their own papers for the manual matcher; they are never merged by guess. Different page counts raise no warning.
- **No Step 2 boxes and no crops.** The item's parts are its full pages (D1). Pages are rendered from `scans/` when needed, through a bounded cache. Nothing renders a whole class up front.
- **Mixed page sizes.** There is no paper-size choice. Each page gets a 5 mm grid from its own size, or a nominal grid from its shape when an image has no physical size, so highlights still snap.
- **Step 4.** The page viewer with the Phase D tools. The note limit applies per page here, not per submission.
- **Class grid.** The Whole papers view is the default.
- **Report.** A layout for whole pages at a readable size, with stamps, highlights and the note list. By default only pages with marks are printed, with an option for every page, to keep PDFs small enough to send.
- **Protection.** Page fixes, late papers, added files and replacement keep IDs and work, as for exams.

**Accept:** a made-up class with one-file and several-file students, mixed PDFs and photos, portrait and landscape, 1 to 25 pages; an ID match, a name match, a subfolder, a duplicate name and an unmatched file; a late submission; a file added to a student who already has notes; reopen on another computer; report and gradebook in both languages; memory while paging through the class. The standalone start screen and an exam session behave exactly as before.

## 10. Phase H — assignments, drafts, Late and partners

- **Draft:** no grade controls. The existing refusal of a question with no marks or criteria is lifted for drafts only. A paper counts as seen once it has a comment or a note. Nothing about a draft counts towards a total.
- **Assignment:** one level per criterion, using the rubric cards and criterion tabs already in Step 4. The criteria come from CAM. The level given is the result; there is no separate final level and no calculation.
- **Late:** a tick per student, stored with that student's overall record. CAM may fill it in on hand-over. It shows on the card and in the grid, and goes to CAM. It never writes into the comment text.
- **Partners:** link students into a group. A grade or comment given to one applies to all, by student ID. When a student joins a group that has a grade, the group's grade stands and no comment is lost: comments are combined, not replaced. Notes and highlights stay on each student's own pages. Unlinking leaves each with a copy.
- **Step 5 and exports** show what applies: no totals for a draft, levels for an assignment, Late and group columns in the gradebook.
- **Sending to CAM.** Settle SPEC §10 question 1 first. The workspace's CSV carries: student, a grade per criterion, checked keywords, comment, due date, file count, files, Late, assessment mode, focus criteria and draft partner group. Whatever route is chosen, CAM must receive all of these, with the note text added to the comment once, in order.

**Accept:** a draft with comments only, reopened and re-sent; an assignment on two criteria; Late set by CAM and changed by the teacher; partners linked before and after grading, unlinked, and with one late paper; a refused save while linked; annotation-only feedback. The same results in CAM2's gradebook and in what CAM receives.

## 11. Phase I — CAM takes CAM2 as its only grader

This work is in CAM's repository and follows CAM's own plan documents (`docs/CAM2_ENGINE_UPGRADE_PLAN.md`, `docs/CAM2_FEEDBACK_FOR_CAM.md`). This section lists what CAM2 needs from it. Never edit CAM's `exam_grading/` copy; tag CAM2 and `git subtree pull`.

1. Read session format 3. An older CAM reports a newer session and leaves it alone.
2. The bridge reads note text with each question's comment, once, in order. Highlights add no text. The exam block in term prompts includes it.
3. **Grade this Assignment** opens CAM2 on an assignment or draft, with its folder, class list, criteria and task kind. The fixed folder is `<class cloud folder>/assignments/<task>/`.
4. Results from Phase H reach the gradebook, the Classroom Entry tab and `draft_feedback` for term prompts. A re-send neither duplicates nor resurrects anything.
5. **Run both side by side:** one real draft, then one real assignment, graded in the workspace and in CAM2, and the results in CAM compared. Drafts first, because a mistake can't touch a mark.
6. **Remove the workspace:** `cam_grading_workspace/`, OAuth and Drive code, credentials handling and their set-up documents. Marks and comments already in CAM stay. Amend CAM's decision D16.
7. The Apps Script that turns Classroom work into PDFs covers Docs and Word as well as Slides and PowerPoint.
8. CAM's links to `Feedback-and-Upgrades.md` on GitHub now point at a moved file; update them to this plan.

**Accept:** CAM's test suite, including bridge tests for notes, Late, partners, drafts and re-sends; the side-by-side comparison written up; a clean CAM install with no Google set-up grading an exam, an assignment and a draft.

## 12. Phase J — verification and release

Only made-up papers and temporary folders. Add to the existing `unittest` modules; use focused browser checks for what parsing can't show.

```sh
python -m unittest discover -s tests -t .
```

Node must be available so the JavaScript check runs. Record real results, skips and what a platform couldn't show.

| Fixture | Must survive and agree |
|---|---|
| Version 1 and 2 marks and rubric sessions | Upgrade, IDs, names, grades, comments over the limit, generated lines, choices, overrides, final levels |
| Mixed exam with sections and choice groups | Ceilings, totals, shares, final half-up rounding, report options |
| Structured answer and three-page essay | Positions, crop adjustment, page breaks, note text, preview, export, gradebook |
| Rotated paper; 16:9, 4:3 and 16:10 decks | Grid, preview and crop alignment; slide detection; JPEG and PNG |
| Class of 30–40 | Grid identity under sort, shuffle and filter; late papers; bounded memory |
| Assignment and draft classes | Several files, matching, Late, partners, results in CAM |
| Save failure during editing | Warning stays, drafts keep their owner, retry, restore, lock release |

**Packages.** Build Windows and Apple Silicon from one commit with the existing builders, `tools/cam2.spec` and `requirements-build.txt`. In each frozen build: new assets present, double-click, reopen, pickers, data outside the bundle, the annotation, grid, 16:10 and assignment flows, export in both languages, non-English paths, and replacing a file open in Excel or a PDF viewer.

**Release steps.**

1. Set `VERSION` in `app.py`, update the documents, commit and push.
2. Build the Windows zip from that commit. On the Mac, pull, confirm the same commit, build the Mac zip.
3. Copy the Mac zip as it is; never re-zip it on Windows.
4. Make the sample exams with `python tools/make_sample_exam.py`, and zip `sample-exam-en` and `sample-exam-ja`.
5. Tag the commit and publish the release with both zips, the samples and the two source archives named in `licences/NOTICE.txt`.
6. Pull the tag into CAM and release CAM on it. Release notes say every computer needs the update before opening an upgraded session.

Update `CHANGELOG.md`, `ARCHITECTURE.md`, `README.md`, [SPEC.md](SPEC.md), the bundled guides and the table in §14.

---

## 13. Requests and backlog

Requests from colleagues and ideas from research. **Suggesters stay anonymous: give a subject or role, never a name.** Full write-ups of F1–F15 are in [archive/feedback-and-upgrades.md](archive/feedback-and-upgrades.md).

| # | Request | From | Status |
|---|---|---|---|
| F1 | Highest level for a question or section | Several colleagues | **1.0**, Phase C |
| F2 | Notes and highlights on the answer | Biology colleague | **1.0**, Phase D. Comment limits shipped in `v0.3.2-dev` |
| F3 | One comment list across CAM2 and the workspace | Project lead | Not doing: the workspace is removed |
| F4 | Ticking in the workspace wiped typed comments | Project lead | Done in CAM, 2026-11-08 |
| F5 | Move drafts and assignments into CAM2; retire the workspace | Project lead | **1.0**, Phases G, H, I |
| F6 | Exam comments in CAM's term comments | Project lead | Done in CAM, 2026-11-08 |
| F7 | A permanent place for a year's work | Project lead | Folder layout in Phase I. The rest is CAM's, after 1.0 |
| F8 | Compact and delete finished sessions | Project lead | After 1.0 |
| F9 | Grading from the keyboard | Research | After 1.0; recommended |
| F10 | Spread of grades while grading | Research | After 1.0; recommended |
| F11 | Class grid, 2–5 columns | Research, then the teacher | **1.0**, Phase E |
| F12 | Calibration mode | Research | After 1.0, in part only |
| F13 | Straightening crooked scans | Research | After 1.0; check the need on real scans first |
| F14 | Class analysis | Research | After 1.0, in part only |
| F15 | Rubric points that update totals | Research | Not doing: totals already recalculate, and levels are never added |

### After 1.0, in suggested order

- **F8 Compact and delete.** Show each session's size on the start screen. *Compact* removes answer crops, which rebuild from the scans on opening; name crops stay for CAM. *Delete* removes only CAM2's own files, after a confirmation. A session from CAM shows *Linked to CAM* instead of Delete. Raise the recent list from 10 to about 200, in a scrolling box.
- **F9 Keyboard grading.** `0`–`9` for a level or mark, arrows for papers, `N` for Not answered, `C` for the comment. Keys do nothing while typing. Changing an existing grade by key asks first.
- **F10 Spread of grades.** One line of counts per band above the paper strip; click a band to review those papers. The list is fixed on entry. Ask colleagues whether it helps or pushes towards an expected shape.
- **F14 Analysis sheet.** Band counts and each question's average as a percentage, on a gradebook sheet sharing F10's counts. Standard deviation if wanted. Discrimination index only for marks, and later.
- **F12 Review summary.** After a band review: how many were raised, lowered and unchanged, with *Put these back*. No trial copy of grades, no checklist. A benchmark paper beside the current one only if the grid doesn't cover it.
- **F13 Straightening.** Count clipped answers on real copier scans first. If needed: find the angle with Pillow at import, save it per page, turn the page in `load_page_image`, never change the scan, leave sliced sessions alone. No OpenCV.
- **F7 in CAM.** A student's work over time, promotion between years, and CAM compacting finished tasks.
- **Smaller ideas set aside:** tick and cross stamps, arrows, annotating in whole-page view, omitting page ranges across an assignment, standalone assignments.

### Checking a new request

- Does it stay within one task? Anything across tasks or years is CAM's.
- Can the app work it out instead of adding a setting?
- Does a marks-only teacher still never see it?
- Does it work offline with no account?

Add a row to the table, with the request in the colleague's own terms, the real need if it differs, what the teacher would see, and what is still to decide.

## 14. Handover and progress

Prompt for a coding session:

> Read AGENTS.md, doc/SPEC.md and doc/PLAN.md. Before any code, check that every earlier phase is finished: tests, open pull requests, and the progress table against the code and git. List what is open and wait for my answer. Then implement Phase ⟨X⟩ only, on its own branch. Reproduce a bug before fixing it. Keep changes small and protect existing teacher work. Check behaviour in the browser, not only by tests. Update the progress table with the branch, commit, the exact checks you ran and what you couldn't check. Open a pull request and stop.

Keep source commits apart from packaging results. On another computer, check for local changes before pulling; never reset to match this plan.

| Phase | State | Evidence / next action |
|---|---|---|
| A: integrity fixes | Not started | Reproduce the four paths; add regressions |
| B: maintenance, buttons, 16:10 | Not started | Cherry-pick `e39afdc`, `920fea1` |
| C: format 3, tiered levels | Not started | Settle every new stored shape first |
| D: annotations, long-answer reports | Not started | Geometry contract first |
| E: class grid | Not started | |
| G: whole-submission tasks | Not started | SPEC §10 questions 3 and 4 |
| H: assignments, drafts, Late, partners | Not started | SPEC §10 question 1 |
| I: CAM, workspace removed | Not started | In CAM's repo |
| J: verification and release | Not started | |

**2026-11-11:** plans consolidated into this document and SPEC.md written. Read the source documents, both reviews, CAM's workspace README, CSV export and CAM2 notes; ran the test suite (354 pass, 1 skipped). No application code changed.
