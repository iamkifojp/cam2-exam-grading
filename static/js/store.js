// The browser's copy of the app state, and `act()`, which every button uses
// to call the server: it updates the session, re-renders, and routes errors
// (save problems become the red banner; anything else a toast).
import { get } from "./api.js";
import { toast } from "./ui.js";

export const app = {
  view: "start",          // start | new | wizard
  step: 1,                // wizard step shown (1–5)
  session: null,          // server's session view (config, grid, saved_at, …)
  recent: [],
  saveError: null,        // { message, code } while saving is failing
  lockWarning: null,      // another computer's lock seen by the heartbeat
  version: "",
  draft: {},              // per-screen scratch state, keyed by screen
  prefs: {},              // per-computer settings: { hide_names, shuffle_papers }
  host: null,             // the app that opened CAM2 (CAM) and its exam, or null
  finishedHost: null,     // host whose sent session was just closed in this tab
};

let renderFn = () => {};
export function onRender(fn) { renderFn = fn; }
export function render() { renderFn(); }

let mutationSeq = 0;
let latestApplied = 0;
export function nextMutationSeq() { return ++mutationSeq; }
export function applySession(session, seq = null) {
  if (seq !== null && seq < latestApplied) return false;
  if (seq !== null) latestApplied = seq;
  app.session = session;
  if (!session?.save_failed) app.saveError = null;
  return true;
}

export function config() { return app.session?.config; }

// The criteria (rubrics) a question is assessed on, in rubric order. Without
// marks, the only rubric when none was picked; a question with marks counts
// towards only what is really ticked (as grading_summary.question_rubric_ids).
export function criteriaOf(c, q) {
  const list = c.rubrics || [];
  const picked = new Set(q.rubric_ids ?? (q.rubric_id ? [q.rubric_id] : []));
  const found = list.filter((r) => picked.has(r.id));
  return found.length || list.length !== 1 || q.max ? found : [list[0]];
}

// How a question is graded: marks, rubric levels, or null while it has neither
// (as grading_summary.question_mode).
export function gradedWith(c, q) {
  if (q.max) return "marks";
  return criteriaOf(c, q).length ? "rubric" : null;
}

// The criteria that any question is assessed on, marks or rubric.
export function usedCriteria(c) {
  return (c.rubrics || []).filter((r) => c.questions.some((q) => criteriaOf(c, q).includes(r)));
}

// One grade on one paper: marks or a level, "not_answered", or null (ungraded).
// Pass the criterion on a rubric question; levels come from the server's summary.
export function gradeOf(sid, qid, rid = null) {
  if (!rid) return app.session.grades.grades?.[sid]?.[qid]?.value ?? null;
  const s = app.session.summary.students.find((x) => x.student_id === sid);
  return s?.levels?.[qid]?.[rid] ?? null;
}

export async function act(promise, { rerender = true, quiet = false } = {}) {
  const seq = nextMutationSeq();
  const sessionId = app.session?.config?.session_id;
  try {
    const data = await promise;
    if (data && "session" in data) {
      if (!sessionId || data.session?.config?.session_id === sessionId || !app.session) {
        applySession(data.session, seq);
      }
    }
    if (rerender) render();
    return data;
  } catch (err) {
    await handleError(err, quiet);
    return null;
  }
}

export async function handleError(err, quiet = false) {
  if (err.saveError) {
    app.saveError = { message: err.message, code: err.code };
    try {                         // the server kept the change in memory: resync
      const state = await get("/api/state");
      app.session = state.session;
    } catch { /* offline */ }
    render();
  } else if (!quiet) {
    toast(err.message, "error");
  }
}
