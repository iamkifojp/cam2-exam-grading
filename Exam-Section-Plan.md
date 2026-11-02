# CAM2 — Exam Sections & Report Options (Implementation Plan)

> **Status:** agreed design, not built yet (2026-11-02). It adds to [PLAN.md](PLAN.md); where the two differ, this plan wins once it is built.
> **Mock-up:** see §6. Everything in it is made up.

---

## 1. Goal

Many MYP exam papers are divided into sections. A section of multiple-choice questions is marked, its total becomes a percentage, and the teacher uses that to help decide a rubric level. Giving a rubric level to each multiple-choice question makes no sense.

So CAM2 should let a teacher:
- divide a paper into sections, each graded with marks or a rubric;
- report each criterion's grades as they were given, and optionally decide an overall level per criterion;
- choose how much each section counts towards the final percentage;
- produce a clearer, shorter report that can leave out answer images.

**CAM2 stays simple.** It grades one exam at a time, with nothing that spans classes or assignments. Prefer what the app can work out for itself over a new setting, and hide anything that does not apply to this exam.

**Marks are the simplest path.** A teacher who only wants marks, or just counts right and wrong with one-mark questions, never has to see a criterion or rubric. They may handle criterion grades outside CAM2.

**Words used in this plan**
- **Criterion:** what is being assessed, such as Criterion B. Each has a rubric.
- **Rubric level:** a number on that rubric's scale, such as 5 in the 5–6 band. Written with its criterion as `B5`.
- **Final level:** an overall level for one criterion, decided by the teacher. Optional.

---

## 2. Teacher Flow

### Step ② Set up the questions
- **Sections are optional.** With none, the whole paper is one section and the screens look as they do today.
- **Adding one:** in the question list, **Start a new section here** adds a divider. Sections follow the order of the paper, so a question always sits inside one section. Moving a question past a divider moves it into that section.
- **Each section has:**
  - a name, which is optional (blank shows as `Section 1`);
  - **Marks** or **Rubric**.
- **Criteria are ticked per question**, so one section can cover several criteria.
  - A question in a rubric section must have at least one criterion, and gets a level for each.
  - A question in a marks section needs no criterion. The ticks appear only if the teacher has added a rubric.
- **Rubrics** are required only for rubric sections. In a marks exam they sit behind a small **Add criteria (optional)** link, and a teacher who ignores it sees no rubric screens anywhere.
- **A question is whatever the teacher draws a box around.** A printed "Question 1" of 24 multiple-choice items can be one question worth 24 marks, or 24 questions. A "Question 2" with parts A and B can be two questions. No separate "parts" feature is needed.
- **Choice questions** ("answer 2 of 3") must stay inside one section, because otherwise a section's total has no clear meaning.
- **Locks:** a section's marks or rubric choice is fixed once one of its questions has a grade. A graded question cannot move into a section of the other kind, because marks and levels cannot be converted.

### Step ④ Grade
- Each question shows marks buttons or rubric levels, according to its section. Otherwise this is unchanged.
- A rubric level is reported as given, with its criterion: Q5 is `B5`, Q6 is `A3`. CAM2 does not average them.

### Step ⑤ Review & export

**Overall criterion results** is optional and off by default. It is offered only when the exam uses criteria. Because each question has its own criterion, this gathers a criterion's results however many sections they are spread across, including a few Criterion A questions inside a mostly different section. The teacher then decides the final level:

```text
Student      Criterion A          Final   Criterion B                     Final   Criterion C    Final
Yui Suzuki   Marks 46/55 · 83.6%  [   ]   Marks 6/10 · 60.0%; Grades B6, B5  [   ]   Grades C5, C6  [   ]
```

- **Marks questions:** added together into one total for the criterion, using any section percentages (§3).
- **Rubric questions:** the actual grades achieved, listed separately. They are never added to marks, totalled or averaged.
- A criterion with only marks shows only the total, and one with only rubric questions shows only the grades.
- Choice-group questions that did not count are left out.
- The final level starts blank, and a final level left blank does not print.
- **Export warning:** if a final level is filled in for some students but not others, the teacher is told which before the reports are made.

**A level for each section:** a tick inside Overall criterion results, off by default. It adds one blank level per criterion for each section, for teachers who turn a section's percentage into a band and then decide the final level from those. CAM2 never calculates it. It prints on that section's row, so ticking it also turns on Section results.

**Section percentages** apply to marks only. CAM2 never works out a section total for rubric grades.
- **Count sections by percentage** is off by default, and the total is simply the marks added up.
- When on, the marks sections start with equal shares: 50 and 50, or 34, 33 and 33 for three sections. Rubric sections have none.
- **The shares always add up to exactly 100.** When a teacher types a percentage, that section keeps it and the sections not yet typed share the rest equally, with any leftover going to the first of them. One section always stays automatic, so the teacher never has to do the sum.
- The shares do not stop at 99, because then a student with full marks would get 99%.
- The **Total on report** override then changes the final percentage instead of the marks total.

**Report options:** at most five, each hidden when it does not apply, and saved with the session. They apply to the whole class. An exam with only marks and no sections sees just the last two.

| Option | Shown when | Default |
|---|---|---|
| Section results | the exam has two or more sections | Off |
| Overall criterion results | the exam uses criteria | Off |
| Rubric table | a criterion with descriptors is used | On |
| Overall marks and percentage | the exam has marks questions | On |
| Answer images, one tick per section | always (one tick if there are no sections) | All on |

**See one report first** makes the PDF for the selected student, so the teacher can check it before making the whole class's reports.

---

## 3. Calculations

| Item | Rule |
|---|---|
| Section marks | The section's counted marks over its maximum, added up from its questions and never typed in. Choice groups count as they do today, inside their section. |
| Section percentage | Marks over maximum, shown to 1 decimal place. |
| Total, no weighting | All marks sections added together, shown as `52 / 65 · 80.0%`. |
| Total, with weighting | The sum of (section marks ÷ section maximum × weighting). It is worked out from unrounded figures and **rounded half up only once, at the end**. The report shows only the percentage, because it would not agree with a total out of 65. |
| Equal shares | 100 divided by the number of marks sections. Any leftover goes to the first sections, one point each, so the shares add up to exactly 100. |
| Mixed paper | Rubric levels are never added to marks. The overall line says which sections it covers. |
| Criterion marks, no weighting | The marks of the questions on that criterion, added together: `46 / 55 · 83.6%`. A question on two criteria counts in both. |
| Criterion marks, with weighting | Each question counts as much here as it does in the overall percentage: its share is section weighting × question maximum ÷ section maximum. The criterion's percentage is the sum of (marks ÷ question maximum × share), divided by the sum of those shares, and rounded once at the end. The report shows only the percentage. |
| Incomplete papers | An ungraded question stays in the criterion's maximum, as it does in the overall total, and the student is flagged incomplete. |
| Rubric levels | **Reported as given.** CAM2 no longer averages a student's levels or suggests a final level, and this replaces the rubric rows in PLAN.md §3. Rules for ranking choice-group questions stay as they are. |
| Final level | Optional, and always typed by the teacher. Must be a level in one of the rubric's bands, so the report can always shade the right band. |
| Short form of a grade | The last letter of the criterion's name when that name ends in a single letter (`Criterion B` or `基準B` gives `B5`). Any other name prints in full (`Knowledge 5`). |
| Ungraded question | Not counted, and the student is flagged incomplete, as today. |

**Why no average:** a level should be a best-fit judgement against the descriptors, not arithmetic. See §8.

**Example with weighting:** Section A 22 / 25 (88%) at 50% and Section B 30 / 40 (75%) at 50% gives 81.5%. Simply adding the marks gives 52 / 65, or 80%.

**Example for a criterion:** Criterion A covers all of Section A and 24 / 30 of Section B's 40 marks.
- Without weighting: 22 + 24 = 46 out of 25 + 30 = 55, or 83.6%.
- With 50% on each section: Section A's share is 50, and Section B's Criterion A questions have a share of 50 × 30 ÷ 40 = 37.5. So (88% × 50 + 80% × 37.5) ÷ 87.5 = 84.6%.
- A criterion on only part of the paper still reaches 100% when its questions earn full marks, because the shares are divided by their own sum.

---

## 4. What is Saved

`cam2_session.json` gains:

```json
{
  "sections": [{"id": "sec1", "name": "Scientific knowledge", "mode": "marks", "weight": 50},
               {"id": "sec2", "name": "", "mode": "rubric", "weight": null}],
  "questions": [{"id": "q1", "section_id": "sec1", "rubric_ids": ["r1"]}],
  "weighted": true,
  "report_options": {"section_results": true, "overall_criteria": false, "section_levels": false,
                     "rubric_table": true, "overall_marks": true, "no_images_for": ["sec1"]}
}
```

`grades.json` gains, under `overall.<student>`:

```json
{"section_levels": {"sec1": {"r1": 7}}, "report_percent": null}
```

- **`final_levels` stays** as the overall level for each criterion. Only its meaning changes: blank now means no level, not "use the average".
- **Typed shares:** a section's `weight` holds the share and each section also records whether the teacher typed it (`"weight_typed": true`), so the app knows which ones to rebalance.
- **Grades stay keyed by question and student ids**, so sections can change without a grade moving to another question or student.
- **Old sessions** have no `sections`. They read as one section using the existing `mode`, and open and grade as before. A final level the teacher did not type starts blank.
- **`model.VERSION` goes to 2**, so an older CAM2 refuses a session it would misread.
- **The wipe guard** (`model.grades_mass`) also counts section and final levels, because they are now teacher work that nothing can recalculate.

---

## 5. Code Changes

| File | Change |
|---|---|
| `engine/model.py` | Document the new shapes, bump the version, extend `grades_mass`. |
| `engine/grading_summary.py` | Add `sections()` and `question_mode()`, and use `question_mode()` for every exam-wide `mode` check (`slots`, `set_grade`, `question_values`, `student_summary`, `class_summary`). Add per-section and per-criterion marks, weighting with equal shares and rebalancing, and `set_section_level`. Remove `average`, `suggested` and the rubric `adjusted`. Choice groups must stay inside a section (`check_choice_groups`). `marks_maximum` works per section. `set_final_level` uses `rubrics.check_level`. |
| `engine/workflow.py` | Save sections and options. Move the `mode_locked` check to each section, and refuse to move a graded question between section kinds. `check_ready` checks each question by its section's mode, and only asks for rubrics when a rubric section exists. |
| `engine/reports.py` | The new order and layout (§6), using a small drawn-table helper: MuPDF's HTML ignores table column widths. A rubric prints if any question ticks it, in marks or rubric sections. |
| `engine/gradebook_xlsx.py` | Add section marks, percentages and weightings, the section and final levels, and the overall percentage. Remove the average columns. List sections on the second sheet. Show the class average, maximum and minimum for each section. |
| `app.py` | Routes for sections, section and final levels, weighting, report options and the one-report preview. |
| `static/js/step2.js`, `step4.js`, `step5.js`, `store.js` | The screens in §2. |
| `i18n/en.json`, `i18n/ja.json` | Every new string in both languages. |

Nothing here adds a dependency or a bundled file, so packaging is unaffected.

---

## 6. The Report

Printed in this order:
1. **Header:** exam name, date, student.
2. **Results:** the overall line, with one row per section above it if Section results is on.
   - The format follows the section: a marks section shows marks and percentage (`22 / 25 · 88.0%`), and a rubric section lists each question's grades with no total (`Q5 B6 · Q6 B5 C5 · Q7 C6`).
   - A level for the section, if the teacher decided one, prints on that section's row.
   - The Weighting column appears only when section percentages are on.
   - With no sections, only the overall line prints.
3. **Rubric:** one copy of each table, only for criteria used in this exam, and only if the Rubric table option is on.
   - With Overall criterion results on, **one box per criterion** holds everything together beside its table: the **Final level** if the teacher decided one, the marks total, and the rubric grades (`B6, B5`). The final level's band is shaded.
   - With the table off, the same boxes print on their own.
4. **Overall comment:** below the tables, only if there is one.
5. **Questions, grouped by section:**
   - Each section's heading shows its marks total only if Section results is on.
   - **Images on:** as today, with the label, answer image and grade in a row and the comment below. A question on two criteria shows `B5` and `C5`.
   - **Images off:** a five-column grid of grades, followed by one row for each question that has a comment.

**The rule that keeps options few: what the teacher filled in prints, and what is blank does not.** Levels, final levels and the overall comment need no tick boxes of their own.

**A marks-only exam** prints just the header, the overall marks and percentage, any overall comment and the questions.

Per-section images matter because answer images are capped at 330 points tall (`IMAGE_MAX_H`). A multiple-choice question boxed across several pages would shrink until it can't be read, so a teacher can turn off images for that section and keep the written answers.

### Mock-up
Made by `tools/make_report_mockup.py` from made-up data, with sample rubric wording. CAM2 still ships no rubric text. It shows a full report, with Section results and Overall criterion results on, final levels decided, and without the optional level for each section.

**No answer images (2 pages)**

![Page 1 of the report: results table, three rubric tables with final levels, overall comment](doc/mockups/report-no-images-p1.png)
![Page 2 of the report: compact grids of question grades, grouped by section](doc/mockups/report-no-images-p2.png)

**Images for Sections B and C only (3 pages).** Page 1 is the same as above.

![Page 2: Section A as a grid, Section B with answer images](doc/mockups/report-images-by-section-p2.png)
![Page 3: Section C with answer images](doc/mockups/report-images-by-section-p3.png)

---

## 7. Build Phases

Each phase ends with its tests passing, and with `CHANGELOG.md` and `ARCHITECTURE.md` updated.

**Phase 1: Engine**
- Sections, per-question mode, section totals, weighting, section and final levels, removing the averages.
- Tests:
  - an old marks session and an old rubric session give the same marks and levels as before;
  - a marks exam with no sections or rubrics needs nothing new;
  - a mixed paper's total ignores rubric levels;
  - the 81.5% example, plus a case where rounding too early would give a different answer;
  - the criterion examples in §3, a criterion spread across sections, one with both marks and rubric grades, and one reaching 100% on full marks;
  - equal shares and rebalancing always add up to exactly 100, for one to seven sections;
  - a choice group across two sections is refused;
  - the mode lock works per section, and a graded question cannot change section kind.

**Phase 2: Step ② screens**
- Dividers, section cards and per-question criteria in both kinds of section.

**Phase 3: Step ④ grading**
- Each question grades by its own section's mode, including on a mixed paper.

**Phase 4: Step ⑤**
- Overall criterion results, section percentages, new review columns, report options, the export warning.

**Phase 5: Report**
- The layout in §6 and the one-report preview. Delete `tools/make_report_mockup.py` and `doc/mockups/` once real reports replace the mock-up.
- Tests: each grade and level reaches the right student's report; blanks do not print; only criteria used are printed; the right band is shaded; each image option works.

**Phase 6: Gradebook**
- The columns in §5, with tests.

**Phase 7: Run-through**
- In a browser, in English and Japanese, on Windows and a Mac:
  - a marks-only exam with no sections, checking that no rubric screens appear;
  - all one criterion across three marks sections;
  - several criteria with a mix of marks and rubric sections;
  - a real scanned paper. **Real papers stay out of the repository.**

---

## 8. MYP Notes

These come from school policies and third-party summaries, not the IB's own guide, which was not available when this was written. Check them against *MYP: From Principles into Practice*.

- **Best fit:** teachers judge a student's work against the descriptors as a whole. A level is not a percentage.
- **No mechanical averaging:** a school policy quotes the guide warning teachers not to "mechanically and uncritically average achievement levels".
- **The 1–7 grade** comes from all four criteria, totalled out of 32, so it does not belong on a single exam's report.

Sources: [The Codrington School policy](https://codrington.edu.bb/wp-content/uploads/2024/06/TCS-MYP-Assessment-Policy.pdf), [Sir Geoffrey Leigh Academy policy](https://sirgeoffreyleighacademy.org.uk/wp-content/uploads/2025/07/Assessment-Reporting-Policy-2025-2026.pdf), [IB Mid-Atlantic slides](https://www.ibmidatlantic.org/Math_Presentation_Jan_2020.pdf), [RevisionDojo on final grades](https://www.revisiondojo.com/blog/how-myp-criteria-levels-combined-final-grade).

---

## 9. Deliberately Not Included

- Averages, totals or suggested levels for rubric grades.
- Required rubrics or final levels in a marks exam.
- Levels for a hand-picked group of questions. A level belongs to one question, one section or the whole paper.
- Automatic conversion from a percentage to a level (`85% = 7`).
- The MYP 1–7 grade.
- A separate strand layer. Teachers type the strands into the criterion's descriptors and can name sections after them.
- Per-section comments.
- Anything spanning several exams, classes or assignments.
