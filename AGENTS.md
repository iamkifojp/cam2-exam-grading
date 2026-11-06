# Project Context & Review Rules

## Architecture & Scope
- Lightweight, offline-first local Python application for batch-grading scanned exam PDFs, defining coordinate answer boxes, and exporting student PDF reports and an Excel gradebook.
- The desktop launcher serves Flask on `127.0.0.1`; the screen is a browser using plain JavaScript modules. There is no frontend framework, build step, CDN, or remote service.
- Target distribution: Standalone Windows (.exe) and Apple Silicon macOS (.app) binaries, built with PyInstaller on each platform.
- `engine/` holds the grading, scan, persistence, and export logic; `app.py` exposes it through routes; `appstate.py` holds the open session and background jobs; `static/js/` holds the screens.
- Each exam lives in a portable session folder. Preferences, recent sessions, emergency copies, and launcher state live in the per-computer app-data folder.

## Strict Anti-Bloat & Review Philosophy
- **Trusted Local Input:** Assume the user is a teacher supplying valid PDF scans on a local machine. Do NOT suggest input sanitization for adversarial/malicious files, extreme edge-case validation, or enterprise-grade telemetry/logging.
- **No Defensive Over-Engineering:** Do NOT suggest `try/except` wrappers, fallback mechanisms, or schema checks for unlikely scenarios. Let unexpected internal errors fail fast and visibly.
- **Keep It Small:** Do not recommend abstracting simple functions into classes, adding third-party dependencies, or splitting files unless it directly fixes a bug.
- **Protect Teacher Work:** USB removal, cloud-sync conflicts, files open in Excel/PDF viewers, and interrupted saves are supported everyday conditions. Regressions in the existing save/recovery behavior are in scope; this is distinct from speculative defensive hardening.
- **Review Implemented Behavior:** Missing wishlist features, cosmetic changes, wording preferences, and general refactoring are not findings. `Feedback-and-Upgrades.md` includes proposals, not requirements for the current app.

## High-Priority Review Targets (ONLY flag these)

1. **Binary Packaging Blockers:** Assets or imports missing from `tools/cam2.spec`, runtime paths depending on the working directory, writes into the bundle, and launcher/picker subprocesses that work from source but fail when frozen. Check `launcher.py`, both platform builders, and `requirements-build.txt` together. PyInstaller supports this app's `__file__`-relative asset paths; do not require `sys._MEIPASS` or `importlib.resources` when the existing path and bundled data work.
2. **Cross-Platform Bugs (Windows vs. macOS):** Path separator or case-sensitivity mistakes, non-English file names, Windows file locks when replacing PDFs/gradebooks, native picker behavior, and Mac double-click/single-instance behavior. Flag actual path bugs, not use of `os.path` instead of `pathlib.Path`. Include coordinate discrepancies between the browser preview and Python crops across display scaling, rotation, landscape paper, and slide sizes.
3. **Memory & Resource Leaks:** Unclosed PDF documents, image buffers, or workbooks during class-wide import, slicing, preview, and export. Check that high-resolution scans and slide decks are processed without retaining the whole class's rendered pages in memory. The report engine uses PyMuPDF, not ReportLab.
4. **Data Integrity:** Wrong, lost, overwritten, or misassigned grades, comments, crops, and exported results. Review these paths in particular:
   - **Identity and page order:** student/question/criterion IDs must stay attached to the same work through question deletion/reordering, roster matching, scan replacement, page fixes, late papers, booklet unfolding, and re-slicing. Display order and shuffled grading order must not determine ownership.
   - **Mixed grading and calculations:** grading mode is per question, based on its marks maximum and criteria; the exam-wide `mode` is only a starting choice. Marks and rubric levels are never added together. Check per-criterion levels, choice-group counting, ungraded versus not answered, section maxima, shares totaling 100%, and rounding half up only at the final percentage.
   - **Reports and gradebook:** calculated results stay distinct from teacher overrides, final levels are teacher-entered, and report options control what prints. Verify the right student's values and comments reach both exports, the PDF includes the correct answer images, and preview/export and re-export agree with the intended options.
   - **Saving and upgrades:** older supported sessions retain their meaning after upgrade and reopening. Preserve atomic saves, conflict detection, emergency recovery, and the save-failure state. Check debounced browser edits and navigation so comments or grades cannot be lost or applied to a different student/question; comment limits must preserve existing text and the generated quick-comment line.

## Review Method & Evidence

- Read `ARCHITECTURE.md` for the code map and `CHANGELOG.md` for changes. Use `Exam-Section-Plan.md` for mixed grading, weighting, and report rules; it supersedes the older rubric calculations in `PLAN.md`.
- Read `doc/repository-review-2026-10-31.md` before reusing earlier findings. Its four issues are recorded as fixed; only report them again if the current code demonstrates a regression.
- Confirm the review's commit/range and working-tree changes. Follow affected behavior through browser state, routes, engine, persistence, and exports as relevant; a passing engine test alone does not prove browser save/navigation behavior.
- Each finding needs a concrete supported teacher action, the resulting failure, an exact code location, and the smallest practical fix. Reproduce it with a focused test or provide a complete code-path explanation. Do not report hypothetical risks without evidence.
- Use existing `unittest` tests and generated fixtures; never use or commit real student data. Run relevant tests for the behavior under review, or the full suite with `python -m unittest discover -s tests -t .` when appropriate. `tests/test_ui_syntax.py` needs Node.js and otherwise skips; it checks parsing, not browser behavior.
- State what was actually verified and what remains untested. Source tests do not establish that a frozen Windows or Mac build works; packaging claims require checks of the corresponding build.
- Report findings first, ordered by impact, with file/line references. If none are substantiated within the four categories, say so and note material verification limits; do not pad the review with improvements outside scope.
