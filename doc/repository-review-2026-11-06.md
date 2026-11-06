# Standalone Binary Release Readiness Review

Date: 2026-11-06

Reviewed commit: `ed8ac1faff6fb53787878c6379e242f4d4e20130`.

Scope: standalone Windows and Apple Silicon macOS release readiness, following
`AGENTS.md`. The working tree was clean at the end of the review; no uncommitted
changes are included. Review began at `8d5b41398014aaaafd03aacc3a5e450cd5fa1942`;
the intervening commit changed only `AGENTS.md`, leaving application code unchanged.

Status: four confirmed data-integrity findings. The recommendations below have
not been applied. The four findings recorded as fixed in
`repository-review-2026-10-31.md` are not repeated here.

## 1. [P1] Navigating away can erase every rubric

**Location:** `static/js/main.js:35–41` and `static/js/step2.js:88–105`.
The receiving route is `app.py:488–493`.

**Supported teacher actions:**

1. Open an existing exam's rubric editor in Step 2.
2. Edit a rubric name, level band, or descriptor.
3. Click another reachable wizard step before the 600 ms rubric-save debounce
   expires and allow navigation to finish.

**Expected:** the edit saves before navigation discards the editor's draft.

**Actual:** the delayed save can erase all rubric definitions and remove the
questions' explicit criterion assignments from the saved session.

**Evidence and code path:** `goTo()` flushes `saveQuestions`, but does not flush
`saveRubrics`. Once the step request succeeds, it replaces `app.draft` with a new
object. The delayed rubric callback then reads `app.draft.rubrics`, which is now
`undefined`. JSON serialization omits that property, sending `{}` to
`/api/setup/rubrics`. The route treats the missing field as an empty list;
`workflow.set_rubrics()` replaces the rubrics with that list and strips the
questions' removed criterion IDs.

A focused JavaScript reproduction executed the existing debounce and rubric
saver with navigation clearing the draft before the timer fired. Its recorded
request was `/api/setup/rubrics` with JSON `{}`. A separate Flask reproduction
confirmed that the late request returns HTTP 200 and persists both
`rubrics: []` and an empty `rubric_ids` list on the question. This was a code
harness and route reproduction, not an interactive browser test.

**Recommendation:** export the existing `saveRubrics` debouncer and await its
flush before `goTo()` clears the draft. Apply the same ordering to session
closure, which also discards the draft. This is approximately four lines using
the existing saver; no new dependency or abstraction is needed.

**Regression check:** schedule a rubric edit, navigate before 600 ms, then reopen
the session and verify the edited descriptor, other rubrics, and question
assignments remain intact.

## 2. [P1] Replacing a reordered class list assigns results to different students

**Location:** `engine/workflow.py:923–927`.

**Supported teacher actions:**

1. Load a class list containing Alice followed by Bob and match their scans.
2. Grade Alice's paper and add a comment.
3. Use **Change list**, or paste a replacement list, with Bob followed by Alice.

**Expected:** papers retain their student identities, or matches that cannot be
preserved safely are cleared for rematching.

**Actual:** Alice's existing paper and grades become labelled as Bob's, and vice
versa. The wrong names reach the PDF reports and Excel gradebook.

**Evidence and code path:** `roster._roster()` assigns `n001`, `n002`, and so on
from the incoming row order. `workflow.set_roster()` keeps an existing paper's
`roster_id` whenever that ID exists in the new list, without checking whether it
still names the same person. Already matched papers are then excluded from
automatic matching. `display_name()` resolves the retained ID against the new
list, while grades remain attached to the original paper ID.

A Flask reproduction replaced `Alice\nBob` with `Bob\nAlice`. The generated Excel
row contained student `Bob`, source `Alice.pdf`, mark `9`, and comment
`Alice answer`. The generated PDF likewise printed `Student Bob`, `9 / 10`,
and Alice's comment.

**Recommendation:** clear existing roster matches before replacing the list and
run the existing automatic matching against the new entries. This takes fewer
than ten lines and prevents row-number IDs from silently changing ownership.
Papers without a certain filename match will require manual matching again.

**Regression check:** replace a matched list with a reordered list and with a
list containing an inserted first row. Verify that no paper retains a match to
a different person, and check the resulting PDF and Excel student names.

## 3. [P1] A new criterion inherits a deleted criterion's grades

**Location:** `engine/workflow.py:584–590`.
The UI creates new criteria with empty IDs at `static/js/step2.js:83–85` and
permits removing one of several criteria at `static/js/step2.js:139`.

**Supported teacher actions:**

1. Set up criteria `r1` and `r2`.
2. Give a question a level on `r2`, and enter a final level for that criterion.
3. Remove `r2` while retaining `r1`.
4. Add a new criterion and select it on the question.

**Expected:** the new criterion starts without question levels or final levels.

**Actual:** it can inherit the deleted criterion's stored levels, including a
teacher-entered final result.

**Evidence and code path:** the browser sends an empty ID for a new criterion.
`set_rubrics()` derives its ID from its current position and checks only IDs
already encountered in that incoming list. Removing the second criterion and
adding a replacement therefore reuses `r2`. Existing question levels remain in
`grades[student][question].levels.r2`, and final levels remain under
`overall[student].final_levels.r2`. Selecting the new criterion makes those
old values visible under its new name.

A Flask reproduction recorded question level `6` and final level `7` for the
original `r2`, deleted it, and added a differently named criterion. The server
assigned the new criterion `r2`; its summary then contained the old level `6`
and final level `7` without either being entered for the new criterion.

**Recommendation:** give every new criterion a fresh unique ID while preserving
IDs on existing criteria. For the normal new-criterion path, the existing
`model.new_session_id()` allows a one-line replacement:

```python
rid = rubric["id"] or f"r{model.new_session_id()}"
```

**Regression check:** delete a criterion with question and final levels, add a
new one, select it, and verify that both kinds of result start blank, including
after saving and reopening.

## 4. [P2] An unrelated successful save hides unsaved grades

**Location:** `appstate.py:75–88` and `static/js/store.js:59–60`.

**Supported teacher actions:**

1. Encounter a cloud conflict copy affecting `grades.json`.
2. Change a grade; its save fails and the red save-failure banner appears.
3. Navigate to another wizard step, saving the session configuration.

**Expected:** the failure remains visible until the grades are successfully
saved, even if saving the configuration succeeds meanwhile.

**Actual:** the configuration save clears the shared failure flag, and the
successful response clears the browser banner, although the grade on disk is
still older than the value held in memory. A portable session folder can
therefore contain stale grades while the screen indicates a successful save.

**Evidence and code path:** `save_config()` and `save_grades()` both reset the
single `save_failed` flag on their own success. Browser `act()` also clears
`app.saveError` on any successful response containing a session, without
checking whether either session file remains unsaved.

A reproduction created a disposable `grades (1).json` conflict copy. Updating
a rubric level returned HTTP 409 and set `save_failed` to true. A subsequent
`/api/step` request returned HTTP 200 with `save_failed: false`. Reading the
files confirmed the saved grade was still `6`, while memory held the attempted
update `5`. The emergency-copy mechanism was not shown to lose that update;
the confirmed bug is the false saved state and hidden warning.

**Recommendation:** retain failure state separately for configuration and
grades, and report a failed state while either file remains unsaved. Browser
response handlers should clear the banner only when the returned session
confirms that both are saved. This needs more than ten lines because the server
and browser both maintain and clear the state; changing only one side leaves
the other able to hide the warning.

**Regression check:** block one file's save, successfully save the other, and
verify that the warning remains. Resolve the conflict and retry saving both;
the warning should clear only after the pending grade reaches disk. Check both
directions: failed grades/configuration and successful configuration/grades.

## Release recommendation

Fix the four findings before the next standalone release. They concern ordinary
teacher actions and can either alter the ownership of results, erase rubric
setup, or hide a failure to persist grades. Keep the corrections limited to
save ordering, identity allocation and matching, and accurate save status.

No additional bugs were substantiated in binary packaging, cross-platform
geometry, or memory/resource handling during this review. The verification
limits below prevent treating that as complete certification of either platform.

## Verification performed and limits

- Read `AGENTS.md`, `ARCHITECTURE.md`, `CHANGELOG.md`, `Exam-Section-Plan.md`,
  and the earlier review. Inspected the launcher, both builders, PyInstaller
  recipe, build requirements, and relevant browser, route, engine, persistence,
  and export paths.
- Ran `PYTHONDONTWRITEBYTECODE=1 build/venv/bin/python -m unittest discover -s tests -t .`.
  The suite ran 354 tests, reporting four localhost-socket errors caused by the
  sandbox and one skipped JavaScript syntax test because Node.js was not on PATH.
  Reran all eight launcher tests with localhost sockets enabled; they passed.
- Separately parsed all 12 browser JavaScript modules successfully in the Node
  runtime. Parsing does not establish browser behavior.
- Executed the focused JavaScript and Flask reproductions described above.
  All fixtures were synthetic and confined to temporary directories; no real
  student data was used or committed.
- Exercised the existing Apple Silicon Mach-O `arm64` app in `dist/`, which
  reported version `0.3.2-dev`. It passed the packaged HTTP startup/assets check,
  then imported a generated PDF, sliced it, recorded a grade and comment,
  generated a Japanese report preview, and exported one student PDF plus an
  Excel gradebook with zero reported export errors. App data and session output
  were confined to temporary directories.
- No new frozen binaries were built. The existing Mac binary's reported version
  was checked, but its embedded source was not compared byte-for-byte with the
  reviewed commit. The source findings were reproduced against the repository.
- No Windows executable was run. Native dialogs, Finder double-click and
  first-run permission behavior, interactive browser/display-scaling behavior,
  and class-scale memory profiling were not exercised. The Mac API checks do
  not establish those behaviors.

No repository files were changed during the review. This report was added
afterward at the user's request; application fixes remain outstanding.
