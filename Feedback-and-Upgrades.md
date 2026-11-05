# CAM2 Feedback and Upgrades

What colleagues have asked for, what each request would take, and what was decided. Read this when planning a new version. Once something is agreed for a version, its design moves to [PLAN.md](PLAN.md), and what shipped goes in [CHANGELOG.md](CHANGELOG.md).

**Suggesters stay anonymous: entries give a subject or role, never a name.**

**Nothing here is being built yet.** More feedback is still to come, so these wait until the next version is decided (2026-11-05).

## Requests

| # | Request | From | Size | Status |
|---|---|---|---|---|
| [F1](#f1-highest-level-for-a-question-or-section) | Highest level for a question or section, for banded papers | Several colleagues | Small | Proposed |
| [F2](#f2-notes-drawn-on-the-answer-image) | Notes drawn on the answer image | Biology colleague | Medium | Proposed; main design choices agreed |

**Size** is a rough guess at the work, including tests and the English and Japanese text. Small is about half a day (around 100 lines). Medium is a few days (around 500 lines), plus time for a teacher to try it.

**Status** is one of: Proposed, Agreed for a version, Done, or Not doing (with the reason).

### Checking a new request

Before agreeing to anything, check it against what CAM2 is:

- It grades one exam at a time, so nothing should span classes, assignments or the school year.
- Few options. Prefer something the app can work out for itself over a new setting, and hide what doesn't apply.
- Marks stay the simplest path. A marks exam never needs criteria, rubrics or final levels.
- It works offline, with no accounts and no services.

### Adding an entry

Copy this under [Details](#details), and add a row to the table above.

```markdown
### F3: Short name

**From:** subject or role, date. **Size:** ... **Status:** Proposed

**What they asked:** in their terms, with the example they gave.

**What it means:** the actual need, if it differs from the words.

**Proposal:** what the teacher would see, and what would change.

**Still to decide:** anything that needs a person's answer.
```

## Details

### F1: Highest level for a question or section

**From:** several colleagues, 2026-11-05. **Size:** Small. **Status:** Proposed

**What they asked:** many papers are banded or tiered. Section 1 targets Criterion A levels 1–2, section 2 targets 3–4, and so on. This already works in CAM2, but nothing stops a teacher giving a level above what the question could earn.

**What it means:** this is a ceiling, not a restriction to one band. A question targeted at 5–6 can still earn 0–4, because a student may fall short, but it can never earn 7–8. So one number is enough, the highest level allowed, and there is no lowest level to set.

**Proposal:**

- **Set-up (Step 2 question table):** each ticked criterion gets a small choice beside its tick: *All levels*, *up to 2*, *up to 4*, *up to 6*. The choices come from the tops of that rubric's bands, so they follow the MYP pairs without any special rule. The default is *All levels*, so nothing changes for anyone who doesn't use it.
- **A section shortcut:** on a paper with sections, the same choice on the section's heading row fills in all its questions. This saves setting it 20 times, while a single question can still differ.
- **Grading (Step 4):** bands above the ceiling aren't shown, so a 5–6 question shows the 0, 1–2, 3–4 and 5–6 cards. A short line on the card says *Up to 5–6*.
- **Saving:** a level above the ceiling is refused when saved, so a wrong grade can't get in from anywhere.
- **Changing it later:** a ceiling can't go below a level already given. This is the same rule as lowering a question's marks below its highest mark (`question_max_below_grade`).

**Why it is small:** CAM2 reports levels as given (`B5`) and never averages them, so no calculation changes. Reports stay as they are, and the final level stays the teacher's own for the whole paper.

**What changes:**

| Where | Change |
|---|---|
| `engine/workflow.py` `set_questions` | Keep `level_caps: {"r1": 6}` on the question, one per criterion. Check it against grades already given |
| `engine/grading_summary.py` `set_grade` | Refuse a level above the ceiling |
| `static/js/step2.js` `questionTable` | The choice beside each tick, and the section shortcut |
| `static/js/step4.js` `gradeCard` | Leave out bands above the ceiling |
| `engine/gradebook_xlsx.py` | Optional: show the ceiling on the reference sheet |
| `engine/model.py` | Bump the session version, so an older CAM2 can't open the session and lose the ceilings |

**Still to decide:**

1. Keep the Step 4 badge on the criterion's scale? Recommended yes: `6 / 8 · 5–6`, not `6 / 6`, because the level is still a level out of 8.
2. Should the student's report say a question was capped, for example `Q3 (up to 5–6)`? Recommended not until someone asks.

### F2: Notes drawn on the answer image

**From:** biology colleague, 2026-11-05. **Size:** Medium. **Status:** Proposed; main design choices agreed

**What they asked:** to mark up the student's answer image with comments, as in the Kami app. Kami also has OCR, which is out of scope. The idea to test: draw a box on the answer and attach a comment to it.

**What can be drawn:** none of these need OCR, because they sit on the image by position. Only selecting or searching the student's text would.

| Overlay | Extra work | Worth it? |
|---|---|---|
| **Box with a note** | Medium; this builds the layer everything else uses | **Yes, first.** It points at part of a diagram, which is the biology need |
| **Comment stamp** (a distinctive numbered icon at one spot) | Small, once boxes exist | **Yes, with the first version.** It puts a comment from the list on the answer with no box to draw |
| Highlight (see-through box) | Very little, once boxes exist | Yes, if asked |
| Tick and cross stamps | Small, once boxes exist | Yes, if asked; handy for labelled diagrams |
| Arrow | Small | Later |
| Text typed directly on the image | Medium; it needs moving and resizing, and covers the writing | Probably not |
| Freehand pen | Medium; needs undo, and is hard to use with a mouse | Only with a stylus user asking |
| OCR, or selecting handwritten text | Very large | No |

**Proposal: numbered notes, with their text listed under the answer.** Numbering the notes is agreed.

1. **Step 4** gets a **✏ Add note** button. Today, dragging on the answer moves it around when zoomed, so drawing needs its own mode.
2. Drag a box over part of the answer. It gets a number, and a small floating card opens beside it, with a text box and the exam's quick comments. Clicking a quick comment copies its text into the note, where it can be edited for this student.
3. Or place a **stamp** from the comment list instead of drawing a box (see [the quick comment list](#the-quick-comment-list) below).
4. Click a box or stamp to edit, move or delete it.
5. **On the report** the box or stamp prints with its number, and the notes print under the answer, after the teacher's comment:

```
 Q3  ┌───────────────────────────────┐   B5
     │  student's diagram            │
     │     ┌─────────┐①              │
     │     │         │               │
     │     └─────────┘               │
     └───────────────────────────────┘
     Comment: Good use of terms. Check your scale.
     ① Label the cell membrane, not the cell wall.
```

**Why not float the comment beside the box on the PDF?** It works on screen, and the card above does exactly that, but not on the report. The answer image there is at most about 390 points wide, between the question label and the grade. Text at a readable size would cover the student's writing or run off the image, and every note would need its own placement. Numbers avoid all of that, and any length of note fits.

**Merging with the existing comment: keep them separate (agreed).** Mixed together, they could confuse, would be hard to format, and would be harder for students to read. The comment is also one free-text field, and CAM2 already rewrites its first line for ticked quick comments, so lines for notes mixed into that text would be hard to keep right when a box is deleted or the comment is edited. Notes get their own list, and they appear together only where they are read:

- on the report, as above;
- in the gradebook, added to that question's comment cell;
- in the review table, where a note counts as a comment for the "has a comment" marker.

#### The quick comment list

**Notes should draw on the comment list (agreed).** Otherwise the list becomes even more superfluous.

- **Is it editable?** The list already is, through **✎ Edit list**. A note's copied text can also be edited for one student without changing the list.
- **Stamps:** a quick comment can go on the answer as a distinctive numbered icon at one spot. There is no box to draw or resize, and the icon is easy to spot on a student's handwriting.
- **Placing a stamp:** there are two ways, to choose when this is built. Both make the same note:
  - **Drag and drop:** drag a quick comment onto the answer. It is direct, but it has to share the pills with their tick-box behaviour.
  - **Stamp tool:** pick a quick comment, then click the answer. It also works well on a laptop trackpad, where dragging across the screen while zoomed in is harder.
- **Ticks stay as they are.** Ticking still writes the generated line in the comment. Using a quick comment in a note doesn't tick it.

**How it would work:**

- **Stored** in `grades.json`, on that student's answer next to the comment: `annotations: [{"page", "x", "y", "w", "h", "text"}]`, where a stamp has no `w` or `h`. It is shared across a question's criteria, as the comment is.
- **Positions are fractions of the scanned page (0–1), not pixels or crop positions.** That makes them independent of zoom, screen DPI and the report's image resizing, on Windows and Mac alike. One engine function turns a page position into a position on the current crop, for both the screen and the report. It has to allow for the way a question with several boxes stacks them with a divider line.
- **The crop files are never changed.** The boxes are drawn over the image on screen and in the PDF, so the existing rule holds and the PDF lines stay sharp.

**When a box is adjusted:** the notes follow the student's writing, because their page positions don't change. **✎ Adjust this box** needs no conversion, and nothing is removed.

- **Still inside the new crop:** the note stays on exactly the same writing.
- **Now outside the crop:** it shows at the nearest place inside, shrunk if the crop is now smaller than the box. On a question with several boxes, that means the nearest box on the same page. If no box is on that page any more, it goes to the top of the crop.
- **Moved notes are flagged:** a moved note no longer points at what it marked, so Step 4 marks it to check, and **✎ Adjust this box** says how many moved. Dragging it into place, or clicking to confirm, clears the flag.
- **Only what is shown moves:** the saved position stays as drawn, so widening the box again puts a note back where it was. Dragging a note saves its new position.

**What changes:**

| Where | Change |
|---|---|
| `static/js/step4.js` `viewer` | A layer over the image that follows zoom, the drawing mode (separate from drag-to-pan in `attachZoomAndPan`), and the floating card. `boxes.js` snaps to the grid, so its drawing can guide this but not be reused directly |
| `engine/grading_summary.py`, `app.py` | Save, edit and delete notes |
| `engine/reports.py` `_question_with_image`, `_question_notes` | Draw the numbered boxes and print the list. With images off for a section, print the note text alone |
| `engine/gradebook_xlsx.py`, `static/js/step5.js` | The comment cell and the review table marker |
| `engine/model.py` `grades_mass`, `engine/workflow.py` `_has_work` | Count notes as teacher work, so the wipe guard protects them and page fixes don't move pages under them |
| `engine/slicer.py` | Turn a page position into a crop position and back, keeping it inside the crop (about 50 lines plus tests, using the same grid math as `range_to_bbox` and `stitch_vertical`) |

**Still to decide:**

1. **Placing a stamp:** drag and drop, the stamp tool, or both.
2. **Length of quick comments.** The list allows 60 characters each (`MAX_LABEL` in `engine/keywords.py`). That suits short keywords, but it may be tight now the list also feeds notes, so it may need to be longer.
3. **Whole page view.** Recommended: notes only on the answer view in the first version, because that is the image the report prints. Page positions make it easy to show them there later.
4. **Try it with the biology colleague before building the extras.** Ask which of highlights and tick and cross stamps they would actually use.

## Done

From colleagues trying the test builds. Details are in [PLAN.md](PLAN.md) §8.

| Request | Version |
|---|---|
| School laptops have no **Run anyway**, so say how to unblock CAM2 on Windows | `v0.3.1-dev` |
| A new version opened an older CAM2 that was still running | `v0.3.1-dev` |
