# CAM2 next release — implementation handoff

> **Archived 2026-11-11.** Kept for its reasoning and history. The current plan is [doc/PLAN.md](../PLAN.md) and the specification is [doc/SPEC.md](../SPEC.md); where this file disagrees with them, they are right.

**Agreed scope:** 2026-11-10. **Status:** planned; application changes have not been implemented by this document.
**Intended coding agent:** GPT 6.1 Sol, medium reasoning. Work in small, verified phases in the order below.
**Proposed release:** `v0.4.0-dev`, with session format 3. Confirm the next unused version at release preparation; do not publish under an existing tag.

This is the implementation plan for the next standalone CAM2 update and its subsequent import into CAM. It supersedes conflicting proposals in `Feedback-and-Upgrades.md` for F1, F2 and F11. `Exam-Section-Plan.md` remains authoritative for mixed grading, calculations and report options. This document defines intended behavior, not evidence that it already works.

## 1. Decisions and baseline

The teacher approved one release containing:

- The four data-integrity corrections from `doc/repository-review-2026-11-06.md`.
- The existing report-total correction and hosted-session close guidance, brought upstream from the CAM maintenance branches.
- Stable level buttons after grading and support for **Slide 16:10**. Slide 16:9 and Slide 4:3 already exist.
- **Tiered assessment:** a maximum permitted rubric level per question and per criterion, with a section shortcut.
- **Answer annotations:** numbered comment stamps and highlights, usable on structured answers and essays spanning several pages, and included in reports and the gradebook.
- **Class grid:** switch between the current question's answers and whole papers; choose **2, 3, 4 or 5 columns**. Click a card to open the student for grading and annotations. The teacher explicitly approved both views and requested five columns for a 32-inch monitor.

Japanese wording is accepted for this release based on colleagues' use and no reported wording problems (teacher decision, 2026-11-10). This is not a claim of a separate formal translation review. Existing Japanese comments and feedback are supported. All new UI, validation and report text must be available in English and Japanese; no outstanding general wording review blocks release.

### Verified repository baseline on 2026-11-10

| Item | State |
|---|---|
| Standalone `main` | `97ac11b0e9c56764713df89f657ca054002ae35f`; local and GitHub matched; clean checkout |
| Latest standalone release | `v0.3.2-dev`, tag `4423090`, Windows and Apple Silicon zips published |
| Application/session versions | `0.3.2-dev` / format 2 |
| `e39afdcc87c1c3b073229291ecbed1a9396d6b71` | Report-value fix on `codex/report-total-phase4`; already shipped inside CAM, not standalone main |
| `920fea1dc3142d978c25764a830035e4e8335e83` | Hosted save-and-close guidance on `codex/cam-host-finish`; contains `e39afdc` in its ancestry; already shipped inside CAM |
| Four November 6 review issues | Still present in standalone main; maintenance commits do not resolve them |
| Current source checks | 354-test suite exercised; sandbox socket errors resolved by rerunning eight launcher tests with loopback access; skipped JS syntax check rerun successfully with Node |

Do not confuse a maintenance branch with a release, or CAM's newer bundled copy with standalone main. Recheck refs before starting. The maintenance branches diverged before later documentation updates: preserve current main's documents when integrating the code. Do not replace the checkout wholesale with a branch tree.

### Boundaries

Keep Flask on localhost, plain JavaScript modules, the existing portable session structure, PyMuPDF reports and PyInstaller builds. No frontend framework, CDN, OCR, new service, generic annotation framework, or new dependency is needed. Follow `AGENTS.md` and protect existing atomic saves, emergency copies, conflict checks and file-lock behavior.

This release does not retire CAM's workspace, add assignment management, introduce cross-year portfolios, or implement freehand drawing, arrows, tick/cross stamps, AI feedback, calibration, or class statistics. The grid is the requested F11 feature; other F9–F15 ideas are not implicitly approved.

## 2. Phase A — preserve teacher work first

Read `ARCHITECTURE.md`, `CHANGELOG.md`, `Exam-Section-Plan.md`, and both repository reviews. The October 31 findings are already fixed; do not reopen them without a demonstrated regression. For each November 6 issue, add a focused failing regression, make the smallest correction, and exercise the browser path as applicable.

### A1. Flush rubric edits before leaving their editor

**Current path:** `static/js/main.js:goTo` flushes `saveQuestions`, then replaces `app.draft`. `static/js/step2.js:saveRubrics` later reads the discarded draft and can send `{}`. `app.py` and `workflow.set_rubrics` then erase the rubric list and question assignments.

- Expose and await the existing rubric saver before navigation clears its draft, including Save & close and switching sessions where applicable.
- A flush must distinguish success from a caught save/validation failure. Keep the editor and its draft when saving fails; simply awaiting a callback that swallows failure is insufficient.
- Capture the edited data and its owner before asynchronous work. Apply server-assigned IDs to that same draft, not whichever screen now happens to be active.
- Check ordering when both question and rubric changes are pending; a stale question payload must not restore removed criterion assignments.

**Acceptance:** edit a descriptor and leave within 600 ms; reopen and verify every rubric, descriptor, question assignment and grade. Repeat with a blocked save: navigation must not drop the edit. Include close/session switch, not only clicking a wizard step.

### A2. Do not retain row-based matches when replacing a roster

**Current path:** `engine/roster.py:_roster` assigns IDs by row position; `engine/workflow.py:set_roster` retains matches whenever those IDs still exist. Reordering the uploaded names therefore changes who owns a paper's results.

- Clear old roster matches on replacement, then use the existing reliable filename/name matching and manual matching flow. Reused row IDs are not proof of identity.
- Keep scan/student IDs, question results, comments and crops attached to their original paper. Do not reorder grade ownership to match display order.
- Show that names need checking again. Allow unmatched papers to be rematched using the existing workflow.

**Acceptance:** give Alice and Bob different results, replace their list in reverse order, and verify no paper silently acquires the other's identity. Rematch and verify the right grades/comments in PDF and Excel after reopen. Include pasted and uploaded lists and an ambiguously named paper that must remain unmatched.

### A3. Never reuse a deleted criterion's identity

**Current path:** `engine/workflow.py:set_rubrics` allocates `r1`, `r2`, etc. from list position. Old question levels and final levels remain under those IDs.

- Use fresh IDs for newly created criteria (the existing `model.new_session_id()` is sufficient); preserve IDs on existing criteria.
- Keep removed criteria's stored results from appearing under a new criterion. Avoid destructive cleanup of historical work as a shortcut.
- Reordering or renaming an existing criterion must preserve its results.

**Acceptance:** grade `r2`, enter its final level, delete it and add a differently named criterion. Both question and final levels for the new criterion must start blank, including after save/reopen and export. Verify criterion reorder/rename preserves the original values.

### A4. Keep save failures visible until the affected data reaches disk

**Current path:** `appstate.py:save_config/save_grades` each clear one shared failure flag; `static/js/store.js:act` clears the browser banner after unrelated success. Other direct response handlers also clear it.

- Track configuration and grade save failure/pending state independently, retaining useful error details. Derive the existing aggregate saved/failed status from both.
- Clear a file's failure only when its pending content has been saved successfully. A successful position, preference or configuration request cannot clear an outstanding grade failure.
- Make browser status and banner handling follow the returned aggregate state; inspect direct handlers in `main.js`, `step2.js`, `step4.js` and `step5.js` as well as `act`.
- Preserve in-memory edits and emergency recovery; a close must not present unsaved work as saved. Keep existing explicit recovery/discard choices meaningful.

**Acceptance:** fail saving grades using a synthetic conflict copy, then save configuration successfully: disk still has the old grade and the warning must remain. Resolve and retry: only then may it clear. Test the inverse, both failures together, USB/folder unavailability, retry, emergency restore, and close. Compare memory, session JSON and browser status.

**Phase A exit:** all four regressions pass, normal saving still works, and browser behavior is recorded. These fixes are prerequisites for new editing surfaces.

## 3. Phase B — integrate maintenance and add 16:10

### B1. Bring the CAM maintenance changes into standalone main

Integrate `e39afdc` and `920fea1` once, in ancestry order, preserving later main documentation. Review the diff before committing; a targeted cherry-pick is appropriate if they remain unmerged.

- Report overrides show the calculated value as a hint; focusing an existing override selects it for replacement.
- Totals must be between zero and the exam marks maximum; weighted percentages between zero and 100. Clearing restores calculated values. Invalid input leaves the previous saved value intact, including when a request contains multiple edited fields.
- Keep calculated and teacher-overridden results distinct in summaries, PDF and Excel.
- Retain hosted Save & close and return-to-CAM guidance. Standalone sessions should not show a nonexistent host.
- Use the next release's own application version when preparing packages; `0.3.2-dev-cam.1` identifies the maintenance build, not this feature release.

**Acceptance:** replace, clear and reject overrides in marks-only and weighted mixed exams; test preview/export/re-export and reopening. Exercise hosted send, save/close, lock release and standalone close, in EN/JA.

### B2. Stop level buttons moving after grading

In `static/js/step4.js:setGrade`, retain the Enter-to-next-paper behavior while preventing focus from scrolling the grade column or window, using `focus({preventScroll: true})` where the current focus call is made.

**Acceptance:** on a short laptop window, select and immediately change a level. The buttons stay under the pointer and both clicks save. Enter still advances. Check after new annotation controls are added too.

### B3. Add Slide 16:10 throughout the existing slide path

Extend `engine/slicer.py` paper constants, dimensions, grids, shape detection and JPEG crop selection; update the Step 1 size picker, translations, tests and relevant guide text. Search all existing 16:9/4:3 checks rather than changing only detection.

- Follow the current 10-inch-wide convention: landscape 254 × 158.75 mm; approximately 51 columns × 32 rows at 5 mm. Store dimensions/grid orientation in the same convention as the existing sizes.
- Recognize landscape 16:10 PDF pages at different physical dimensions, after standard paper detection.
- Preserve photo exclusions, portrait-page behavior, A4/A3/B5 recognition, forced landscape for slides and restoration of the previous landscape setting when returning to paper.
- Slide answer crops use JPEG quality 85; name crops remain PNG. Do not reinterpret saved 16:9 sessions as 16:10.

**Acceptance:** synthetic landscape 16:10 decks at two physical sizes, 16:9 and 4:3 regression cases, photo-only PDFs and phone images, standard paper and portrait pages. Draw/crop a known rectangle and compare browser preview and exported crop. Verify reopen and bilingual picker labels.

## 4. Phase C — format 3 and tiered rubric assessment (F1)

### C1. Upgrade sessions once for this release

Bump `engine/model.py` session/grades version to 3 for ceilings and annotations together. Extend the existing upgrade path for supported versions 1 and 2. Preserve every existing ID, grade, final level, comment, generated quick-comment line, override, choice, box, section and report option. New ceilings are absent (unrestricted); annotations/highlights start empty.

Do not silently discard text during conversion. Keep existing save/recovery semantics when only one of the two files has been written before an interruption; test that reopening/recovery preserves their shared identity and work. Older apps must reject version 3 visibly rather than open and rewrite it. Explain in release notes that every computer and CAM installation reading an upgraded session needs the compatible update; retain a pre-upgrade session backup for rollback.

### C2. Per-question, per-criterion ceilings

Use the proposed question field `level_caps: {"criterion-id": 6}`. No entry means the full rubric scale. This is a maximum level, not a minimum band: a question capped at 6 can earn 0 through 6.

- Step 2: beside each selected criterion on a rubric-graded question, offer All levels and the upper endpoints of its actual bands. For the common rubric these are up to 2, 4, 6, 8; do not hardcode MYP pairs or force arbitrary custom rubrics onto an eight-point scale.
- Keep individual levels selectable within a band: 1 and 2, 3 and 4, etc. A ceiling is separate for each criterion on the same question.
- On a section heading, provide a shortcut per criterion to apply a ceiling to applicable rubric questions in that section. It changes those questions, not a second inherited setting. Individual questions may then differ. Validate the entire bulk change before applying it.
- Step 4: show permitted levels and a brief “Up to 5–6” indication. Keep the grade on the original scale (e.g. 6/8), not 6/6. Final criterion levels for the whole paper remain teacher-entered and are not capped by one question.
- Server: enforce the ceiling in `set_grade`; refuse lowering it below any existing grade in `set_questions`. Preserve zero, Not answered and Ungraded distinctions. Rubric edits must not leave a cap that points to a nonexistent permitted endpoint; request correction rather than silently changing grades.
- Marks questions, including marks attributed to criteria, continue to use marks maxima. They do not acquire a second level grade or cap.
- Reordering/renaming questions, sections or criteria preserves the relevant IDs and caps. Removing a criterion assignment removes its cap for that question, without reassigning old results.
- PDF grades retain the original scale; no new student-facing cap badge is required. Include the cap in the gradebook reference sheet so teachers can inspect the setup.

**Acceptance:** two criteria with different ceilings on one question; section shortcut plus individual exception; custom bands; attempted above-cap grade via UI and API; attempted lowering below existing grades; rubric edit; rename/reorder/delete/add; save/reopen; mixed marks/rubric choice groups; final levels and weighted totals unchanged by caps.

## 5. Phase D — annotations for structured answers and essays (F2)

### D1. Ownership, storage and coordinates

Store annotation lists alongside a student's question comment in `grades.json`, shared across that question's criteria. Every operation targets stable student and question IDs. Give each note/highlight a stable ID; displayed note numbers are derived from list order and may change after deletion.

Suggested shapes (document the final shape in `engine/model.py`):

```json
{
  "annotations": [{"id": "note-id", "page": 1, "x": 0.25, "y": 0.40, "text": "Explain this inference.", "type": "growth"}],
  "highlights": [{"id": "highlight-id", "page": 1, "x": 0.18, "y": 0.38, "w": 0.40, "h": 0.03, "colour": "yellow"}]
}
```

Specify page numbering explicitly (use the existing one-based `page1!` convention) and normalize positions to the displayed source page, independent of CSS pixels, device scale or stitched crop dimensions. Rotation must use the same transformed page geometry as the crop renderer.

Build on `range_to_bbox`, `crop_boxes` and `stitch_vertical` in `engine/slicer.py`. Return crop-part geometry from the engine for the browser and use the same calculations for reports: source page/rectangle, pixel scaling, stacked offset and divider spacing. Account for multiple boxes on one page, unequal widths, repeated/overlapping regions and multi-page stacking. A point in padding or a divider must not become a source-page note. If a marked source region appears twice, both visual copies may show the same mark, with only one note-list entry.

Annotation edits go through the existing guarded grade save path, preserving unrelated fields and per-criterion grades. Capture IDs and draft payloads before requests; flush pending note text before student/question/criterion changes, grid entry, report preview, export, close or session change. A failed/refused save retains the draft and owner. Do not silently overwrite a newer note list with a delayed older response.

### D2. Teacher controls

- Tools in the answer viewer: Pan, Add note and Highlight. Add a note by clicking a location and typing, or drag a saved quick comment onto it. Allow direct typed notes without first changing the reusable list.
- Numbered stamps point to the answer; an editable numbered list holds their text. Move or delete a stamp without moving the image; deleting renumbers displayed notes. Changing a saved quick comment never changes notes already placed.
- Highlights are translucent rectangles, in yellow, blue or pink, with no grade meaning. Draw with pointer events; make remove and cancel actions explicit. Support mouse, trackpad and touch/pointer input without requiring hover.
- Keep zoom/pan and the grade controls usable while reading a tall answer. Notes remain legible at all zoom levels. Initial annotation authoring is in the answer view; whole-page mode remains for inspecting context, with a clear route back to the answer to annotate.
- Keep Strength/Area to develop as optional quick-comment/note types with text as well as colour. This resolves the older F2 conflict between keeping types in the prose and removing them in its code table.
- Replace quick-comment ticking with reusable note placement in the new UI, as F2 proposed. Preserve the complete text already generated by legacy ticks. Old `keywords`/`keyword_text` metadata must no longer regenerate, delete or duplicate that text after migration. Preserve existing custom lists, including oversized lists.
- Start new lists with the four EN/JA sentence comments proposed in F2. Initial limits remain: 8 reusable comments, 8 notes per answer, 120 Unicode characters per new note/list comment; 300 question-comment and 600 overall-comment limits remain. Never truncate existing text or oversize lists; allow preservation/shortening but not growth. Count characters consistently in Python and JavaScript, and preserve Japanese IME composition.
- Before release, try the 8-note limit on the three-page essay fixture with the teacher. This is a carried-forward F2 default, not evidence that 8 is sufficient for every essay. If inadequate, agree a revised limit and update both UI/server and report tests together; do not confuse note count with reusable-comment count. Highlights do not consume note slots.

### D3. Box adjustments and teacher-work protection

Annotations follow source-page writing when a crop changes; never bake them into or overwrite scan/crop files.

- Keep stored source coordinates. Clip highlights against each displayed crop part.
- If a note is outside the new crop, project its display to the nearest point in a box on the same page; if no such box exists, show it at the start of the answer. Clearly mark it “Check position.” Do not silently make that projected position permanent.
- Moving the stamp explicitly saves a new source position. Confirming a projected location must also record that chosen location; it cannot merely clear a transient flag while leaving an ambiguous anchor. Widening a box restores unchanged original anchors where they become visible again.
- Fully excluded highlights remain stored and appear in an excluded-mark indication so a teacher can inspect/remove them; do not silently delete them or draw a false highlight elsewhere.
- Add notes and highlights to `grades_mass`, `_has_work`/`class_has_work`, page-edit/scan-replacement guards, progress/comment indicators where appropriate, and emergency-recovery tests. An annotation-only paper is teacher work even without a grade or typed question comment. Deleting one annotation deliberately must remain possible under the wipe guard.

### D4. Reports and gradebook, including long answers

Current `engine/reports.py:_question_with_image` fits the entire stitched answer into one image rectangle. That is inadequate for a two- or three-page essay with readable annotations.

- Preserve compact rendering for short answers. For long answers, use crop parts/continuations across report pages at a readable width. Split oversized parts into successive vertical segments if necessary, with no missing or duplicated writing. Do not shrink three source pages into one tiny box.
- Render numbered stamps and transparent highlights using PyMuPDF at the same source locations seen in the browser, transformed for each segment. Labels/continuation labels, grade placement and note numbering must remain clear across page breaks. Print each note's text once per question; paginate the list without cutting text.
- With section answer images disabled, omit images and graphical marks but still print note text with the question. Respect every existing report option.
- Append numbered note text to that question's gradebook comment cell, leaving the separately stored question comment intact; include notes in Step 5's comment marker. Highlights alone are not invented text.
- Preview, full export and re-export must render the same annotation content/options. Close image/PDF resources per student/part; do not retain a whole class's rendered pages.

**Acceptance:** one-third-page and half-page answers; one-page letter; two- and three-page essays; multi-box same-page answer; rotated/landscape scans and all slide sizes. Place marks near edges, on each essay page and beside crop dividers. Test zoom, display scaling, re-slicing, excluded marks, criterion switching and rapid navigation. Reopen and compare coordinates and ownership. Verify English/Japanese text, long notes and legacy comments in preview, PDF and Excel. Check ordinary deletion, annotation-only work, conflict failure and emergency restore.

## 6. Phase E — class submission grid (F11)

Reference interaction: CAM's `cam_grading_workspace/app.py` uses student cards, a 2–5 column control and expanded media. Reuse the interaction idea, not the workspace's Drive/provider/group-work code.

- Add a Class grid action in Step 4 and a clear return to the focused grading view. Provide **This question / Whole papers** views and **2 / 3 / 4 / 5 columns**; default to 3. Persist column preference per computer. On a narrow viewport reduce the effective columns to keep cards usable, without losing the requested wide-screen preference.
- **This question:** one card per student, showing the current question's full answer crop in a bounded preview, grade/status for the active criterion where applicable, and existing annotation overlay. Do not crop away the only indication of a long answer: show page/part count and open the complete answer on click.
- **Whole papers:** one card per student with a page preview, page count and small previous/next page controls. Load additional pages only on demand. Clicking the card opens that student's focused view at the chosen page for context; the current question remains the grading target. Make the question selector explicit so a page click never silently changes which answer receives a grade or note.
- Clicking a question card opens that exact student's current question and criterion. Grade and annotate in the existing focused view, then return to the same grid mode, column choice and scroll position. No separate editable grade model or batch-grading mechanism.
- Default order follows current paper/shuffle order. Offer grade ordering only in question view, for the active criterion (or marks), with Ungraded and Not answered distinct; no adding levels across criteria. Keep filters explicit and show visible/class counts so ungraded-only mode cannot look like missing submissions.
- Respect Hide student names and existing reveal behavior in labels, titles and accessibility text. Identity always comes from IDs, never card positions, sort rank or shuffled indices. Whole-paper previews may contain handwritten names in the scan, just as existing whole-page view does; Hide names does not promise image redaction.
- Use bounded thumbnail responses/cache keyed by student, question/page and crop revision. Load near-visible cards lazily and release offscreen full-resolution image resources where needed. Do not fetch/decode every full-resolution essay for initial grid paint. Keep cache data regenerable and invalidate after re-slicing/page changes.
- Flush/retain pending edits under the same rules as Phase A/D before opening a card or changing modes. Late papers, question reorder and re-slicing must update the correct cards.

**Acceptance:** fictional class of 30–40 papers including long essays and photo-heavy slides; both modes; every column count on laptop and 32-inch display widths; page navigation; scrolling; returning from grading; names hidden; shuffle; grade sort; filters; late papers; re-slicing; pending/refused comments. Check browser network/image memory during repeated open/close/scroll cycles and that memory is not retained for every full-resolution class page.

## 7. Phase F — CAM integration and release verification

### F1. CAM compatibility is a separate repository change

The first CAM upgrade already shipped the workspace comment correction (F4) and exam feedback in term prompts (F6). Do not reimplement those in standalone CAM2.

For the next import, coordinate with CAM's `docs/CAM2_ENGINE_UPGRADE_PLAN.md` and `docs/CAM2_FEEDBACK_FOR_CAM.md`:

- Tag the verified CAM2 source and use CAM's existing subtree workflow; never edit its vendored `exam_grading/` copy independently.
- Update CAM's session-version reader for format 3 and its bridge to read question note text alongside comments, once, in note order. Highlights add no fabricated text. Preserve raw rubric levels, final decisions, overrides and the distinction between calculated/report values.
- Test re-send, edited/deleted notes, comments cleared, duplicate imports, student/question ownership and exam feedback in term prompts. Notes must not disappear or be resurrected from an old mirror. Include annotation-only feedback and final levels.
- Carry both maintenance commits forward. Publish compatibility guidance identifying the matching CAM version. Do not claim existing CAM accepts version 3 until verified; an older CAM must report incompatibility without altering the session.

CAM integration can proceed after the CAM2 data shape is settled. Standalone implementation completion and CAM bridge completion must be reported separately. Cross-app feature acceptance requires both.

### F2. Required verification

Use only generated fictional papers and temporary app-data/session folders. Add to existing `unittest` modules; use focused JS/browser checks for behavior that parsing cannot test. Use the full suite at integration boundaries and before release:

```sh
python -m unittest discover -s tests -t .
```

Use an environment with the repository dependencies installed and Node available. On the checked Mac, `build/venv/bin/python` has the runtime dependencies; `.venv/bin/python` did not. Do not hardcode that Mac path as a Windows instruction. Launcher tests need localhost sockets. Record actual test results, skips and platform limits rather than reusing the old count.

Minimum combined fixture matrix:

| Fixture | What must survive and agree |
|---|---|
| Existing v1/v2 marks and rubric sessions | Upgrade/reopen, IDs, names, grades, comments including over-limit text, legacy generated lines, choices, overrides, final levels |
| Mixed exam with sections and choice groups | Per-criterion caps, marks-only totals, weight shares, final half-up rounding, report options |
| Structured answer plus three-page essay | Browser anchors, annotations, crop adjustment, page breaks, note text, report preview/export and gradebook |
| Rotated paper and 16:9/4:3/16:10 decks | Grid/preview/crop alignment, slide detection exclusions, JPEG versus name PNG |
| 30–40-paper class | Grid sorting/shuffle/filter identity, late papers, bounded image memory and resources |
| Save failure during editing/navigation | Failure stays visible, drafts retain their owner, successful retry, reopen/emergency restore and lock release |

Build Windows and Apple Silicon packages from the same release commit using the existing builders, `tools/cam2.spec` and `requirements-build.txt`. Check all new JS/assets are included, double-click/start/reopen and native pickers work, and data stays outside the bundle. Run the new annotation/grid/16:10 workflow in each frozen build, including EN/JA export, non-English paths and replacing exports open in a viewer/Excel. Source tests alone do not establish package behavior.

Update `CHANGELOG.md`, `ARCHITECTURE.md`, `README.md`, relevant plan statuses and bundled guides to describe completed behavior, the format upgrade and verified limits. Release Windows/Mac zips, sample exams and required library source archives according to `PLAN.md`; tag must identify the source of both builds.

## 8. Handoff and progress record

Suggested coding prompt:

> Use GPT 6.1 Sol at medium reasoning. Read AGENTS.md and doc/next-release-plan.md, then implement this plan in phase order. Start by checking the current checkout and remote refs and reproducing the four Phase A bugs. Preserve existing teacher work and keep changes small. Commit coherent verified phases, update the progress record with exact checks and unresolved items, and leave each phase easy to resume on another computer. Do not mark a feature done from syntax checks alone. Keep CAM changes in its own repository and report platform checks that cannot be performed here explicitly.

At each handoff record the branch/commit, completed phase, tests/browser checks actually performed, and the next concrete action here. Keep implementation source commits separate from release packaging results. On another laptop, check for local changes before a fast-forward pull; do not reset or overwrite work to match this plan.

| Phase | State | Evidence / next action |
|---|---|---|
| A: four integrity fixes | Not started | Reproduce November 6 paths and add regressions |
| B: maintenance + 16:10 | Not started | Integrate the two known maintenance commits without losing main docs |
| C: format 3 + ceilings | Not started | Implement migration and per-criterion caps after A |
| D: annotations + long-answer reports | Not started | Establish source/crop geometry contract, then editing and exports |
| E: class grid | Not started | Both views, 2–5 columns, open a card to grade |
| F1: CAM integration | Not started | Coordinate format 3 and note import in CAM after schema settles |
| F2: release verification | Not started | Both frozen platforms, docs, samples and matching tagged packages |

**Planning verification, 2026-11-10:** read current source and review/feature documents; compared remote refs and the two maintenance diffs; inspected CAM's column-grid interaction and current report image fitting. This documentation commit implements no application features and does not constitute a new binary test.
