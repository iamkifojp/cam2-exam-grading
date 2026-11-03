# CAM2 Exam Grading

CAM2 turns a stack of scanned exam papers into one-question-at-a-time grading,
then produces a PDF report for every student and an Excel gradebook.

It is a standalone, simplified fork of CAM (Criterion Assessment Metrics),
built so that any teacher can use it **without installing anything and without
training**:

- **Unzip and double-click.** The Windows and Mac downloads carry their own
  Python, so nothing has to be installed.
- **Five guided steps.** Exam & scans → set up questions → match names →
  grade → review & export. Each step shows one instruction at a time.
- **Stop any time.** Every grade is saved the moment it is given. Next time,
  **Continue** takes you back to the same question and student.
- **Safe on USB sticks and cloud drives** (OneDrive, Google Drive, iCloud
  Drive, Dropbox). CAM2 checks every save,
  keeps an emergency copy on your computer, and warns you before two
  computers overwrite each other.
- **English and 日本語** for the whole app and for student reports.
- **Marks or rubrics.** Points per question, or your own rubric (for example
  MYP 0–8). CAM2 ships no rubric text; you type, paste or upload your own.
  An exam can use several criteria, and one question can be assessed on more
  than one of them, with a level for each.
- **Real scans, not perfect ones.** Scan the whole class into one PDF, a few
  batches, one file per student or phone photos. Booklets scanned open on A3
  are put back in page order, and upside-down, misplaced or missing pages can
  be fixed on screen. Late papers can be added at any time.

## Status

**The app is finished; the downloads are not.** Everything a teacher does in
CAM2 is built and tested, from the start screen to the student PDFs and
the Excel gradebook. The Windows and Apple Silicon Mac packages have each been
tested on the computer that built them, and both are on the Releases page as the
pre-release `v0.2.0-dev`. The tests on other computers are still to do.

| Stage | | State |
|---|---|---|
| Phase 1 | Engine and tests | ✅ done |
| Phase 2 | Start screen and Steps ①–③ | ✅ done |
| Phase 3 | Step ④ grading | ✅ done |
| Phase 4 | Step ⑤ review, student PDFs and Excel gradebook | ✅ done |
| Phase 4b | Scanning guide, booklets, page fixes, late papers | ✅ done |
| Phase 4c | Questions assessed on several criteria | ✅ done |
| Phase 5 | No-install Windows and Mac downloads, tested end to end on real computers | ⏳ Packages built; tests on other computers next |
| Exam sections | Sections, mixed marks and rubric questions, and report options ([plan](Exam-Section-Plan.md)) | ⏳ Phases 1 to 6 of 7 (the engine, the screens, the student report and the gradebook) done; the run-through is next |

All 321 automated tests pass, and every finished stage was also tried out in a
browser with sample papers, in English and Japanese. Exam sections and papers that
mix marks and rubric questions are built from set-up to gradebook, but have not yet
had their full run-through, and are not in the test builds. CAM2 can also be run from
the source code (see [For developers](#for-developers)). [PLAN.md](PLAN.md) has the full plan and
[CHANGELOG.md](CHANGELOG.md) the details of each stage.

## For teachers

The downloads are test builds for now, as they are still being tried on other
computers. They are on this repository's
[Releases](https://github.com/iamkifojp/cam2-exam-grading/releases) page:

| Computer | Download | First start |
|---|---|---|
| Windows 10 / 11 | `CAM2-exam-grading-Windows-vX.zip` | Unzip, then double-click **Start CAM2 Exam Grading**. If Windows says it protected your PC, click **More info**, then **Run anyway** |
| Mac with an Apple chip (M1 or later) | `CAM2-exam-grading-Mac-AppleSilicon-vX.zip` | Unzip, double-click **Start CAM2 Exam Grading**, then approve it once in System Settings → Privacy & Security → **Open Anyway** |

You will need:
- your scanned papers. Nothing has to be set up before the exam: scan the
  whole class at the photocopier into one PDF (or a few batches). Booklets
  can be unstapled and scanned open on A3, and CAM2 puts their pages back in
  order. One file per student and phone scans work too. The start screen's
  **How to scan your papers** has the details;
- the paper size (A4, B5 or A3);
- optionally, your class list in Excel or CSV.

## For developers

Requires Python 3.14 (the version the packages ship).

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -t .
```

The tests use Python's built-in `unittest`, so no test runner needs to be
installed. They create their own test PDFs and temporary folders and never
read real student data.

### Running the app

```bash
python launcher.py
```

This starts CAM2 on `http://127.0.0.1:5182/` and opens the browser. Useful options:

| Option | What it does |
|---|---|
| `--no-browser` | don't open a browser tab |
| `--idle 0` | never stop by itself (normally it stops 10 minutes after the last tab closes) |
| `--host <handoff.json>` | open one exam for another app (CAM); see `engine/host.py` |
| `--data-dir <folder>` | keep app data (recent sessions, emergency copies) **and** the default Documents folder inside `<folder>`, so trying things out never touches your real ones |

### Sample papers to try it with

```bash
python tools/make_sample_scans.py <output folder>
```

This makes 8 fake two-page papers (made-up names), the same papers as one
combined PDF, the same again as A3 booklets scanned open (one sheet upside
down and one booklet stacked inside sheet first, to try the page fixes), one late student's paper, and a class list. In Step 1, use **Or paste the path…** if you
would rather not click through the folder picker.

### Building the downloads

Each download is built on its own system, with Python 3.14. On Windows:

```bash
python tools/build_windows.py
```

On an Apple Silicon Mac:

```bash
python3 tools/build_mac.py
```

These make `dist/CAM2-exam-grading-Windows-v<version>.zip` and
`dist/CAM2-exam-grading-Mac-AppleSilicon-v<version>.zip`, with the version taken
from `VERSION` in `app.py`. Each installs what it needs into its own
`build/venv`, and starts the packaged app once to check that it works. `build/`
and `dist/` are not committed. The notes on the Mac package are under Phase 5 in
[PLAN.md](PLAN.md).

### More documents

- [ARCHITECTURE.md](ARCHITECTURE.md) explains how the code and the session
  folder are organised.
- [PLAN.md](PLAN.md) is the implementation plan.
- [CHANGELOG.md](CHANGELOG.md) lists changes by phase.

### Keeping student data out of the repository

`.gitignore` excludes session folders, scans, crops, reports, PDFs and
spreadsheets. Never commit a real session folder; tests must build their own
data (see `tests/helpers.py`).

## Credits

Forked from CAM (`criterion-assessment-metrics`). The grid geometry, the
save-safety rules, the Windows folder picker and the portable-package builder
come from CAM.

## Licence

CAM2's own code is released under the [MIT License](LICENSE), the same licence
as CAM.

The downloads also include PyMuPDF, which CAM2 uses under the GNU AGPL version
3, so each download as a whole is licensed under the
[AGPL](licences/AGPL-3.0.txt). [licences/NOTICE.txt](licences/NOTICE.txt) lists
every library in the downloads, and
[licences/THIRD-PARTY-NOTICES.txt](licences/THIRD-PARTY-NOTICES.txt) has their
licence texts. The zip carries the same files in its `Licences` folder.
