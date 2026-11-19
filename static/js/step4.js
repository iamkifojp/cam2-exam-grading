// Step 4: grade one question across every paper, with marks or rubric levels
// as that question is set up. A rubric question assessed on several criteria
// is graded one criterion at a time: each (question, criterion) pair is its
// own item, with tabs to switch criterion.
// Left: the answer (zoomable, with Pan / Add note / Highlight tools) and badge,
// or the whole page.
// Right: the grading card — grade, Not answered, quick comments, numbered notes,
// question comment, Next paper.
import { get, post } from "./api.js";
import { t } from "./i18n.js";
import { goTo } from "./main.js";
import { act, app, applySession, config, criteriaOf, gradeOf, gradedWith, handleError, nextMutationSeq, render } from "./store.js";
import { button, commentField, commentRefused, debounce, formatTime, h, modal, toast } from "./ui.js";
import { parseRange, snap } from "./boxes.js";

const isDraft = () => config()?.task_kind === "draft";
const isAssignment = () => config()?.task_kind === "assignment";
const wholeSubmission = () => isDraft() || isAssignment();
const summaryOf = (sid) => app.session?.summary?.students?.find((x) => x.student_id === sid) || null;
const isSeen = (sid) => !!summaryOf(sid)?.seen;
const isLate = (sid) => !!summaryOf(sid)?.late;
const NA = "not_answered";
const MAX_BUTTONS = 15;          // above this, a number box with − / +
const ZOOMS = [0.5, 0.75, 1, 1.25, 1.5, 2, 2.5, 3];
const HL_COLOURS = ["yellow", "blue", "pink"];
const GRID_THUMB_WIDTH = 520;

const geometryCache = new Map();
const noteSavers = new Map();    // `${sid}|${qid}|${nid}` -> debounced saver
let gridObserver = null;

if (typeof window !== "undefined") {
  window.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!app.session || app.step !== 4 || !app.draft.grading?.gridOpen) return;
    if (document.querySelector(".modal-backdrop")) return;
    e.preventDefault();
    closeGrid();
  });
}

// --- State helpers ------------------------------------------------------------------

function entry(sid, qid) {
  return app.session?.grades?.grades?.[sid]?.[qid] || null;
}

function hasAnnotationOrComment(sid, qid) {
  const e = entry(sid, qid);
  return !!(wholeSubmission() && app.session?.grades?.overall?.[sid]?.comment?.trim()) || !!(e && ((e.comment || "").trim() || (e.annotations || []).length || (e.highlights || []).length));
}

// Every item graded across the class, in order: { q, r } (r null for a marks question).
function items(c) {
  return c.questions.flatMap((q) => (gradedWith(c, q) === "rubric"
    ? criteriaOf(c, q).map((r) => ({ q, r }))
    : [{ q, r: null }]));
}

const itemKey = (qid, rid) => `${qid}|${rid || ""}`;

function itemIndex(c, d) {
  const i = items(c).findIndex((it) => it.q.id === d.qid && (it.r?.id || null) === (d.rid || null));
  return i < 0 ? 0 : i;
}

function itemLabel(it) {
  return it.r && criteriaOf(config(), it.q).length > 1 ? `${it.q.label} · ${it.r.name}` : it.q.label;
}

const valueOf = (sid, qid, rid) => gradeOf(sid, qid, rid);
const isGraded = (sid, qid, rid) => valueOf(sid, qid, rid) !== null;
const isItemDone = (sid, qid, rid) => (isDraft() ? isSeen(sid) : isGraded(sid, qid, rid));

export function partnerInfo(c, sid) {
  const groups = c?.partner_groups || [];
  const byId = new Map((c?.students || []).map((s) => [s.id, s]));
  let num = 0;
  for (const g of groups) {
    const members = (g.student_ids || []).map((id) => byId.get(id)).filter(Boolean);
    if (members.length < 2) continue;
    num += 1;
    if (members.some((m) => m.id === sid)) {
      return { id: g.id, num, members, others: members.filter((m) => m.id !== sid) };
    }
  }
  return null;
}

export async function openPartnerModal(studentId, { flush = flushStep4 } = {}) {
  if (commentRefused() || !(await flush())) return;
  const bodyEl = h("div", { class: "stack" });
  const drawModal = () => {
    const c = config();
    const student = c.students.find((s) => s.id === studentId);
    if (!student) return;
    const info = partnerInfo(c, studentId);
    const groupedOther = new Set();
    const groupNumOf = new Map();
    for (const s of c.students) {
      const pi = partnerInfo(c, s.id);
      if (pi && pi.id !== info?.id) {
        groupedOther.add(s.id);
        groupNumOf.set(s.id, pi.num);
      }
    }
    const inGroupIds = new Set((info?.members || [student]).map((m) => m.id));
    const candidates = c.students.filter((s) => !inGroupIds.has(s.id));
    const select = h("select", { id: "partner-select", "aria-label": t("partners.add_label") },
      h("option", { value: "" }, t("partners.choose")),
      candidates.map((s) => {
        const gNum = groupNumOf.get(s.id);
        const text = gNum ? `${s.display_name} (${t("partners.group_n", { n: gNum })})` : s.display_name;
        return h("option", { value: s.id, disabled: !!(info && gNum) }, text);
      }));
    const linkBtn = button(t("partners.link_button"), async () => {
      if (!select.value) return;
      const data = await act(post("/api/partners/link", { student_id: studentId, partner_id: select.value }));
      if (data || app.saveError) drawModal();
    }, "primary small", { id: "partner-link-btn", disabled: true });
    select.addEventListener("change", () => { linkBtn.disabled = !select.value; });

    const currentBox = info
      ? h("div", { class: "stack" },
        h("p", { class: "label" }, t("partners.current_group", { n: info.num })),
        h("ul", { class: "partner-list" }, info.members.map((m) => h("li", { class: "row spread partner-row" },
          h("span", {}, m.display_name),
          button(t("partners.unlink"), async () => {
            const data = await act(post("/api/partners/unlink", { student_id: m.id }));
            if (data || app.saveError) drawModal();
          }, "small ghost")))))
      : h("p", { class: "muted small" }, t("partners.none"));

    const addBox = candidates.some((s) => !(info && groupedOther.has(s.id)))
      ? h("div", { class: "row partner-add" }, select, linkBtn)
      : h("p", { class: "muted small" }, t("partners.none_available"));

    bodyEl.replaceChildren(
      h("p", { class: "muted small" }, t("partners.hint")),
      currentBox,
      h("div", { class: "stack" }, h("span", { class: "label" }, t("partners.add_label")), addBox));
  };
  drawModal();
  const student = config().students.find((s) => s.id === studentId);
  modal({
    title: t("partners.title", { name: student?.display_name || "" }),
    body: bodyEl,
    actions: [{ label: t("common.close"), kind: "primary" }],
  });
}

function draft() {
  const c = config();
  if (!app.draft.grading) {
    const list = items(c);
    const resume = c.resume || {};
    const it = list.find((x) => x.q.id === resume.question_id && (!x.r || !resume.rubric_id || x.r.id === resume.rubric_id))
      || list[0];
    const rid = it.r?.id || null;
    const sids = papers(c, it.q.id).map((s) => s.id);
    const anyGraded = sids.some((sid) => list.some((x) => isItemDone(sid, x.q.id, x.r?.id)));
    const sid = sids.includes(resume.student_id) ? resume.student_id
      : (sids.find((s) => !isItemDone(s, it.q.id, rid)) || sids[0]);
    app.draft.grading = {
      qid: it.q.id, rid, sid, ungradedOnly: anyGraded, zoom: 1,
      wholePage: false, page: 1, tool: "pan", hlColour: "yellow",
      pickedKeyword: null, pendingNote: null,
      gridOpen: false, gridView: wholeSubmission() ? "papers" : "question", gridSort: "order",
      gridFilter: "all", gridScroll: 0, gridPages: {},
    };
  }
  const d = app.draft.grading;
  if (!d.tool) d.tool = "pan";
  if (!d.hlColour) d.hlColour = "yellow";
  if (!d.gridView) d.gridView = wholeSubmission() ? "papers" : "question";
  if (!d.gridSort) d.gridSort = "order";
  if (!d.gridFilter) d.gridFilter = "all";
  if (!d.gridPages) d.gridPages = {};
  // Coming from the review table (no criterion given), or the criteria changed.
  const list = items(c);
  if (!list.some((x) => x.q.id === d.qid && (x.r?.id || null) === (d.rid || null))) {
    const it = list.find((x) => x.q.id === d.qid) || list[0];
    d.qid = it.q.id;
    d.rid = it.r?.id || null;
  }
  return d;
}

const savePosition = debounce((qid, sid, rid) => {
  const sessionId = app.session?.config?.session_id;
  post("/api/position", { question_id: qid, student_id: sid, rubric_id: rid })
    .then((data) => {
      if (app.session?.config?.session_id === sessionId && data?.session?.config?.resume) {
        app.session.config.resume = data.session.config.resume;
      }
    })
    .catch((err) => handleError(err, true));
}, 800);

// The page a question's first box is on (where "See whole page" opens).
function firstPage(qid) {
  const q = config().questions.find((x) => x.id === qid);
  return (q && parseRange(q.boxes[0])?.page) || 1;
}

// Moving to another paper or question flushes pending text first and stays
// put if saving fails or a comment/note is over its limit.
async function moveTo(changes) {
  if (commentRefused() || !(await flushStep4())) return;
  const d = draft();
  d.arrived = false;
  d.pendingNote = null;
  d.pickedKeyword = null;
  const switchingQuestion = changes.qid && changes.qid !== d.qid;
  const switchingStudent = changes.sid && changes.sid !== d.sid;
  Object.assign(d, changes);
  if (switchingQuestion && d.gridOpen) d.gridScroll = 0;
  if (switchingQuestion || switchingStudent) {
    d.revealed = null;
    d.page = firstPage(d.qid);
  }
  savePosition(d.qid, d.sid, d.rid);
  render();
}

// "Shuffle papers": a different order for every question, the same each time
// that question is opened, so a paper's number never identifies a student.
const shufflePapers = () => !!app.prefs.shuffle_papers;

function seededShuffle(list, seed) {
  let a = 2166136261;
  for (const ch of seed) a = Math.imul(a ^ ch.codePointAt(0), 16777619);
  const random = () => {
    a = (a + 0x6D2B79F5) | 0;
    let x = Math.imul(a ^ (a >>> 15), 1 | a);
    x = (x + Math.imul(x ^ (x >>> 7), 61 | x)) ^ x;
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
  const out = [...list];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

function papers(c, qid) {
  return shufflePapers() ? seededShuffle(c.students, `${c.session_id}|${qid}`) : c.students;
}

function visibleStudents(c, d) {
  const all = papers(c, d.qid);
  if (!d.ungradedOnly) return all;
  return all.filter((s) => s.id === d.sid || !isItemDone(s.id, d.qid, d.rid));
}

function nextStudentId(c, d, step = 1) {
  const list = visibleStudents(c, d);
  const at = list.findIndex((s) => s.id === d.sid);
  if (d.ungradedOnly) {
    for (let i = 1; i < list.length; i++) {
      const s = list[(at + step * i + list.length) % list.length];
      if (!isItemDone(s.id, d.qid, d.rid)) return s.id;
    }
    return null;
  }
  const target = at + step;
  return target >= 0 && target < list.length ? list[target].id : null;
}

function levelText(r, value) {
  const max = Math.max(...r.bands.map((b) => b.max));
  const band = r.bands.find((b) => b.min <= value && value <= b.max);
  return band && band.min !== band.max ? `${value} / ${max} · ${band.levels}` : `${value} / ${max}`;
}

function badgeText(c, q, sid) {
  if (isDraft()) return null;
  if (gradedWith(c, q) === "marks") {
    const value = valueOf(sid, q.id);
    if (value === null) return null;
    return value === NA ? t("step4.badge_na") : `${value} / ${q.max}`;
  }
  const crit = criteriaOf(c, q);
  const values = crit.map((r) => valueOf(sid, q.id, r.id));
  if (values.every((v) => v === null)) return null;
  if (values.every((v) => v === NA)) return t("step4.badge_na");
  if (crit.length === 1) return levelText(crit[0], values[0]);
  return crit.map((r, i) => `${r.name}: ${values[i] === null ? "—"
    : values[i] === NA ? t("step4.badge_na") : levelText(r, values[i])}`).join("\n");
}

// --- Geometry & projection (matches engine/slicer.py) -------------------------------

function geomKey(c, qid, sid) {
  return `${c.session_id}|${qid}|${sid}|${c.sliced_at || ""}|${wholeSubmission() ? app.draft.grading?.page || 1 : ""}`;
}

function cachedGeometry(c, qid, sid) {
  const rec = geometryCache.get(geomKey(c, qid, sid));
  return rec?.data || null;
}

function loadGeometry(c, qid, sid, onReady = null) {
  const key = geomKey(c, qid, sid);
  const stamp = encodeURIComponent(c.sliced_at || "");
  let rec = geometryCache.get(key);
  if (!rec) {
    rec = { data: null, promise: null };
    geometryCache.set(key, rec);
    rec.promise = get(`/api/geometry/${encodeURIComponent(qid)}/${encodeURIComponent(sid)}?v=${stamp}&page=${app.draft.grading?.page || 1}`)
      .then((geom) => {
        rec.data = geom;
        if (geometryCache.size > 128) geometryCache.delete(geometryCache.keys().next().value);
        return geom;
      })
      .catch(() => null);
  }
  if (onReady) rec.promise.then((geom) => { if (geom) onReady(geom); });
  return rec.promise;
}

function cropPointToPage(geom, cx, cy) {
  for (const part of geom?.parts || []) {
    const x0 = part.crop_x, y0 = part.crop_y;
    const w = part.crop_w, h = part.crop_h;
    if (cx >= x0 && cx <= x0 + w && cy >= y0 && cy <= y0 + h) {
      const rx = w ? (cx - x0) / w : 0;
      const ry = h ? (cy - y0) / h : 0;
      const r = part.rect;
      return {
        page: part.page,
        x: Math.min(Math.max(r.x + rx * r.w, 0), 1),
        y: Math.min(Math.max(r.y + ry * r.h, 0), 1),
        partIndex: part.index,
      };
    }
  }
  return null;
}

function snapHighlightFromCrop(geom, cx0, cy0, cx1, cy1) {
  const parts = geom?.parts || [];
  const start = cropPointToPage(geom, cx0, cy0);
  let part = start ? parts[start.partIndex] : null;
  const left = Math.min(cx0, cx1), right = Math.max(cx0, cx1);
  const top = Math.min(cy0, cy1), bottom = Math.max(cy0, cy1);
  if (!part) {
    part = parts.find((p) => {
      const x1 = p.crop_x + p.crop_w, y1 = p.crop_y + p.crop_h;
      return Math.min(right, x1) > Math.max(left, p.crop_x)
        && Math.min(bottom, y1) > Math.max(top, p.crop_y);
    });
  }
  if (!part) return null;
  const x0 = part.crop_x, y0 = part.crop_y, w = part.crop_w, h = part.crop_h;
  const ix0 = Math.max(left, x0), iy0 = Math.max(top, y0);
  const ix1 = Math.min(right, x0 + w), iy1 = Math.min(bottom, y0 + h);
  if (ix1 <= ix0 || iy1 <= iy0 || w <= 0 || h <= 0) return null;
  const r = part.rect;
  const px0 = r.x + ((ix0 - x0) / w) * r.w;
  const py0 = r.y + ((iy0 - y0) / h) * r.h;
  const px1 = r.x + ((ix1 - x0) / w) * r.w;
  const py1 = r.y + ((iy1 - y0) / h) * r.h;
  const g5 = part.grid || app.session.grid_5mm || app.session.grid;
  const box = snap(part.page, px0, py0, px1, py1, g5.cols, g5.rows);
  return {
    page: box.page,
    x: box.c1 / g5.cols,
    y: box.r1 / g5.rows,
    w: (box.c2 - box.c1 + 1) / g5.cols,
    h: (box.r2 - box.r1 + 1) / g5.rows,
  };
}

function partCropXY(part, px, py, gw, gh) {
  const r = part.rect;
  const rx = r.w ? Math.min(Math.max((px - r.x) / r.w, 0), 1) : 0;
  const ry = r.h ? Math.min(Math.max((py - r.y) / r.h, 0), 1) : 0;
  const cx = part.crop_x + rx * part.crop_w;
  const cy = part.crop_y + ry * part.crop_h;
  return { cx, cy, nx: gw ? cx / gw : 0, ny: gh ? cy / gh : 0 };
}

function projectAnnotations(geom, annotations) {
  const parts = geom?.parts || [];
  const gw = geom?.width || 0, gh = geom?.height || 0;
  return (annotations || []).map((ann, idx) => {
    const page = Number(ann.page || 1), px = Number(ann.x || 0), py = Number(ann.y || 0);
    if (!parts.length) {
      return { ...ann, num: idx + 1, outOfCrop: true, cx: 0, cy: 0, nx: 0, ny: 0,
        confirmedPage: page, confirmedX: px, confirmedY: py };
    }
    const inside = [];
    for (const part of parts) {
      if (part.page !== page) continue;
      const r = part.rect;
      if (px >= r.x && px <= r.x + r.w && py >= r.y && py <= r.y + r.h) {
        const margin = Math.min(
          (px - r.x) * part.page_width, (r.x + r.w - px) * part.page_width,
          (py - r.y) * part.page_height, (r.y + r.h - py) * part.page_height,
        );
        inside.push({ margin, part });
      }
    }
    if (inside.length) {
      inside.sort((a, b) => (b.margin - a.margin) || (a.part.index - b.part.index));
      const { cx, cy, nx, ny } = partCropXY(inside[0].part, px, py, gw, gh);
      return { ...ann, num: idx + 1, outOfCrop: false, cx, cy, nx, ny,
        confirmedPage: page, confirmedX: px, confirmedY: py };
    }
    const samePage = parts.filter((p) => p.page === page);
    let chosenPart = parts[0], qx = parts[0].rect.x, qy = parts[0].rect.y;
    if (samePage.length) {
      let bestDist = Infinity;
      for (const part of samePage) {
        const r = part.rect;
        const cxp = Math.min(Math.max(px, r.x), r.x + r.w);
        const cyp = Math.min(Math.max(py, r.y), r.y + r.h);
        const dist = Math.hypot((px - cxp) * part.page_width, (py - cyp) * part.page_height);
        if (dist < bestDist) {
          bestDist = dist;
          chosenPart = part;
          qx = cxp;
          qy = cyp;
        }
      }
    }
    const { cx, cy, nx, ny } = partCropXY(chosenPart, qx, qy, gw, gh);
    return { ...ann, num: idx + 1, outOfCrop: true, cx, cy, nx, ny,
      confirmedPage: chosenPart.page, confirmedX: qx, confirmedY: qy };
  });
}

function projectHighlights(geom, highlights) {
  const parts = geom?.parts || [];
  const gw = geom?.width || 0, gh = geom?.height || 0;
  return (highlights || []).map((hl) => {
    const page = Number(hl.page || 1);
    const hx0 = Number(hl.x || 0), hy0 = Number(hl.y || 0);
    const hx1 = hx0 + Number(hl.w || 0), hy1 = hy0 + Number(hl.h || 0);
    const pieces = [];
    for (const part of parts) {
      if (part.page !== page) continue;
      const r = part.rect;
      const ix0 = Math.max(hx0, r.x), iy0 = Math.max(hy0, r.y);
      const ix1 = Math.min(hx1, r.x + r.w), iy1 = Math.min(hy1, r.y + r.h);
      if (ix1 <= ix0 || iy1 <= iy0) continue;
      const a = partCropXY(part, ix0, iy0, gw, gh);
      const b = partCropXY(part, ix1, iy1, gw, gh);
      pieces.push({ nx: a.nx, ny: a.ny, nw: b.nx - a.nx, nh: b.ny - a.ny });
    }
    return { ...hl, pieces, excluded: !pieces.length };
  });
}

// --- Saving ------------------------------------------------------------------------------

function updateSavedStatus(session) {
  const status = document.querySelector(".save-status");
  if (status && session?.saved_at && !session?.save_failed) {
    status.className = "save-status ok";
    status.textContent = t("save.saved_at", { time: formatTime(session.saved_at) });
  }
}

async function actKeepingScroll(promise) {
  const scrollTop = document.querySelector(".grade-card-col")?.scrollTop || 0;
  const data = await act(promise);
  if (data) {
    const panel = document.querySelector(".grade-card-col");
    if (panel) panel.scrollTop = scrollTop;
  }
  return data;
}

async function setGrade(sid, qid, value, rid = null) {
  if (commentRefused() || !(await flushStep4())) return;
  const data = await actKeepingScroll(post("/api/grade", {
    student_id: sid, question_id: qid, value, rubric_id: rid,
  }));
  if (data) {
    setTimeout(() => document.getElementById("next-paper")?.focus({ preventScroll: true }), 0);
  }
}

export const saveComment = debounce(async (sid, qid, text) => {
  const sessionId = app.session?.config?.session_id;
  const seq = nextMutationSeq();
  try {
    const data = await post(wholeSubmission() ? "/api/overall" : "/api/grade", { student_id: sid, question_id: qid, comment: text });
    if (app.session?.config?.session_id !== sessionId) return false;
    applySession(data.session, seq);
    updateSavedStatus(data.session);
    if (isDraft()) {
      const c = config();
      const seenCount = (c?.students || []).filter((s) => isSeen(s.id)).length;
      const total = c?.students?.length || 0;
      const progSpan = document.querySelector(".grade-progress span");
      if (progSpan) progSpan.textContent = t("step4.seen_count", { done: seenCount, total });
      const progFill = document.querySelector(".grade-progress .progress-fill");
      if (progFill && total) progFill.style.width = `${(seenCount / total) * 100}%`;
      const activeDone = isSeen(sid);
      document.querySelector(".paper-chip.on")?.classList.toggle("graded", activeDone);
      document.querySelector(".paper-chip.on")?.classList.toggle("noted", hasAnnotationOrComment(sid, qid));
      document.querySelector(".viewer")?.classList.toggle("graded", activeDone);
      document.querySelector(".grade-card")?.classList.toggle("graded", activeDone);
    }
    return true;
  } catch (err) {
    await handleError(err);
    return false;
  }
}, 700);

function noteSaver(sid, qid, noteId) {
  const key = `${sid}|${qid}|${noteId}`;
  let saver = noteSavers.get(key);
  if (!saver) {
    saver = debounce(async (text) => {
      if (!String(text || "").trim()) return true;
      const sessionId = app.session?.config?.session_id;
      const seq = nextMutationSeq();
      try {
        const data = await post("/api/annotations", {
          action: "update_note", student_id: sid, question_id: qid, id: noteId, text,
        });
        if (app.session?.config?.session_id !== sessionId) return false;
        applySession(data.session, seq);
        updateSavedStatus(data.session);
        return true;
      } catch (err) {
        await handleError(err);
        return false;
      }
    }, 700);
    noteSavers.set(key, saver);
  }
  return saver;
}

export async function flushStep4() {
  const checks = await Promise.all([
    saveComment.flush(),
    ...[...noteSavers.values()].map((s) => s.flush()),
  ]);
  return checks.every(Boolean);
}

async function annotate(payload) {
  if (commentRefused() || !(await flushStep4())) return null;
  return actKeepingScroll(post("/api/annotations", payload));
}

function countNotesOnPage(sid, qid, page) {
  return (entry(sid, qid)?.annotations || []).filter((a) => Number(a.page) === Number(page)).length;
}

async function addNote(sid, qid, page, x, y, text, type = null) {
  const cleaned = String(text || "").trim();
  if (!cleaned) {
    toast(t("error.note_text_required"), "error");
    return null;
  }
  const limit = app.session.comment_limits?.notes_per_page || 8;
  if (countNotesOnPage(sid, qid, page) >= limit) {
    toast(t("error.too_many_notes_on_page", { page, limit }), "error");
    return null;
  }
  return annotate({
    action: "add_note", student_id: sid, question_id: qid, page, x, y, text: cleaned, type,
  });
}

// --- Privacy & prefs --------------------------------------------------------------------

const hideNames = () => !!app.prefs.hide_names;

function nameOrReveal(d, student) {
  if (!hideNames() || d.revealed === student.id) return h("span", { class: "student-name" }, student.display_name);
  return button(["👁 ", t("step4.show_name")], () => { d.revealed = student.id; render(); }, "small ghost");
}

function setPref(key, value) {
  app.prefs[key] = value;
  post("/api/prefs", { [key]: value }).catch((err) => handleError(err, true));
  render();
}

const gridColumns = () => {
  const n = Number(app.prefs.grid_columns);
  return [2, 3, 4, 5].includes(n) ? n : 3;
};

async function openGrid() {
  if (commentRefused() || !(await flushStep4())) return;
  const d = draft();
  d.pendingNote = null;
  d.pickedKeyword = null;
  d.gridOpen = true;
  render();
  requestAnimationFrame(() => window.scrollTo(0, d.gridScroll || 0));
}

function closeGrid() {
  const d = draft();
  d.gridScroll = window.scrollY;
  d.gridOpen = false;
  render();
  window.scrollTo(0, 0);
}

async function openCard(studentId, { wholePage = false, page = null } = {}) {
  if (commentRefused() || !(await flushStep4())) return;
  const d = draft();
  d.gridScroll = window.scrollY;
  d.gridOpen = false;
  d.arrived = false;
  d.pendingNote = null;
  d.pickedKeyword = null;
  d.revealed = null;
  d.sid = studentId;
  d.wholePage = wholePage;
  d.page = wholePage ? (page || 1) : firstPage(d.qid);
  savePosition(d.qid, d.sid, d.rid);
  render();
  window.scrollTo(0, 0);
}

// --- Screen -------------------------------------------------------------------------------

export function renderStep4() {
  if (gridObserver) {
    gridObserver.disconnect();
    gridObserver = null;
  }
  const c = config();
  const d = draft();
  if (wholeSubmission()) d.gridView = "papers";
  const list = items(c);
  const at = itemIndex(c, d);
  const item = list[at];
  const q = item.q;
  const rid = item.r?.id || null;
  const student = c.students.find((s) => s.id === d.sid) || c.students[0];
  const gradedHere = c.students.filter((s) => isItemDone(s.id, q.id, rid)).length;
  const go = (it) => moveTo({ qid: it.q.id, rid: it.r?.id || null, sid: firstFor(c, d, it) });

  const questionBar = h("div", { class: "grade-bar" },
    h("div", { class: "row" },
      button(["◀ ", t("step4.prev_question")], () => go(list[at - 1]), "small", { disabled: at === 0 }),
      h("label", { class: "inline" }, h("span", { class: "sr-only" }, t("step4.question")),
        h("select", { class: "question-select", id: "question-select",
          onchange: (e) => go(list.find((x) => itemKey(x.q.id, x.r?.id) === e.target.value)) },
        list.map((x, i) => h("option", { value: itemKey(x.q.id, x.r?.id), selected: i === at ? "selected" : null },
          t("step4.question_of", { label: itemLabel(x), n: i + 1, total: list.length }))))),
      button([t("step4.next_question"), " ▶"], () => go(list[at + 1]), "small", { disabled: at === list.length - 1 })),
    h("div", { class: "grade-progress" },
      h("span", {}, t(isDraft() ? "step4.seen_count" : "step4.graded_count", { done: gradedHere, total: c.students.length })),
      h("div", { class: "progress small" }, h("div", { class: "progress-fill",
        style: { width: `${(gradedHere / c.students.length) * 100}%` } }))),
    d.gridOpen ? null : h("label", { class: "check" }, h("input", { type: "checkbox", checked: d.ungradedOnly,
      onchange: (e) => { d.ungradedOnly = e.target.checked; render(); } }), t(isDraft() ? "step4.unseen_only" : "step4.ungraded_only")),
    h("label", { class: "check" }, h("input", { type: "checkbox", checked: hideNames(),
      onchange: (e) => setPref("hide_names", e.target.checked) }), t("step4.hide_names")),
    h("label", { class: "check" }, h("input", { type: "checkbox", checked: shufflePapers(),
      onchange: (e) => setPref("shuffle_papers", e.target.checked) }), t("step4.shuffle_papers")),
    d.gridOpen
      ? button(t("step4.back_to_grading"), closeGrid, "small on", { id: "grid-toggle" })
      : button(["⊞ ", t("step4.class_grid")], openGrid, "small", { id: "grid-toggle" }),
    d.fromReview
      ? button(t("step4.back_to_review"), () => goTo(5, { next: true }), "primary")
      : button(t("step4.to_review"), () => goTo(5, { next: true }), "ghost"));

  if (d.gridOpen) {
    return h("main", { class: "page full grading grid-mode" },
      questionBar,
      ...classGridSection(c, d, item));
  }

  const strip = h("nav", { class: "paper-strip", "aria-label": t("step4.papers") },
    h("span", { class: "strip-label" }, t("step4.papers")),
    papers(c, q.id).map((s, i) => {
      const done = isItemDone(s.id, q.id, rid);
      const hidden = d.ungradedOnly && s.id !== d.sid && done;
      if (hidden) return null;
      const noted = hasAnnotationOrComment(s.id, q.id);
      return h("button", { type: "button",
        class: `paper-chip ${done ? "graded" : ""} ${noted ? "noted" : ""} ${s.id === d.sid ? "on" : ""}`,
        title: hideNames() ? null : s.display_name, "aria-current": s.id === d.sid ? "true" : null,
        onclick: () => moveTo({ sid: s.id }) }, String(i + 1));
    }));

  const allDone = d.ungradedOnly && gradedHere === c.students.length;

  return h("main", { class: "page full grading" },
    questionBar,
    strip,
    d.arrived && !allDone ? h("div", { class: "now-grading", role: "status" }, t("step4.now_grading", { label: itemLabel(item) })) : null,
    h("div", { class: "grade-layout" },
      viewer(c, d, item, student),
      h("aside", { class: "grade-card-col" }, allDone ? doneCard(c, item) : gradeCard(c, d, item, student))));
}

function firstFor(c, d, it) {
  const all = papers(c, it.q.id);
  const first = d.ungradedOnly ? all.find((s) => !isItemDone(s.id, it.q.id, it.r?.id)) : null;
  return (first || all[0]).id;
}

// --- Left: the answer (with annotation layer) or the whole page -----------------------------

function colourName(colour) {
  if (colour === "blue") return t("step4.hl_blue");
  if (colour === "pink") return t("step4.hl_pink");
  return t("step4.hl_yellow");
}

function toolBar(d) {
  const setTool = (tool) => {
    d.tool = tool;
    if (tool !== "note") d.pendingNote = null;
    if (tool !== "pan") d.pickedKeyword = null;
    render();
  };
  const swatches = d.tool === "highlight"
    ? h("div", { class: "hl-swatches", role: "group", "aria-label": t("step4.hl_colour") },
      HL_COLOURS.map((col) => h("button", {
        type: "button",
        class: `hl-swatch hl-${col} ${d.hlColour === col ? "on" : ""}`,
        title: colourName(col), "aria-label": colourName(col),
        "aria-pressed": d.hlColour === col ? "true" : "false",
        onclick: () => { d.hlColour = col; render(); },
      })))
    : null;
  return h("div", { class: "row tool-bar" },
    h("div", { class: "seg tool-seg" },
      h("button", { type: "button", class: d.tool === "pan" ? "on" : "",
        "aria-pressed": d.tool === "pan" ? "true" : "false",
        onclick: () => setTool("pan") }, t("step4.tool_pan")),
      h("button", { type: "button", class: d.tool === "note" ? "on" : "",
        "aria-pressed": d.tool === "note" ? "true" : "false",
        onclick: () => setTool("note") }, t("step4.tool_note")),
      h("button", { type: "button", class: d.tool === "highlight" ? "on" : "",
        "aria-pressed": d.tool === "highlight" ? "true" : "false",
        onclick: () => setTool("highlight") }, t("step4.tool_highlight"))),
    swatches);
}

function viewer(c, d, item, student) {
  const q = item.q;
  const value = valueOf(student.id, q.id, item.r?.id);
  const index = papers(c, q.id).indexOf(student);
  const stamp = encodeURIComponent(c.sliced_at || "");
  const badge = badgeText(c, q, student.id);

  const prevId = nextStudentId(c, d, -1);
  const nextId = nextStudentId(c, d, 1);
  const head = h("div", { class: "viewer-head" },
    h("div", { class: "row" },
      h("span", { class: "question-name" }, itemLabel(item)),
      button(["◀ ", t("step4.prev_paper")], () => moveTo({ sid: prevId }), "small", { disabled: !prevId }),
      h("strong", {}, t("step4.paper_of", { n: index + 1, total: c.students.length })),
      nameOrReveal(d, student),
      wholeSubmission() && isLate(student.id) ? h("span", { class: "badge warn-badge" }, t("step4.late_badge")) : null,
      button([t("step4.next_paper"), " ▶"], () => moveTo({ sid: nextId }), "small", { disabled: !nextId })),
    h("div", { class: "row" },
      d.wholePage && !wholeSubmission() ? null : [
        toolBar(d),
        button("−", () => zoom(d, -1), "small", { "aria-label": t("step4.zoom_out"), title: t("step4.zoom_out") }),
        button(t("step4.fit"), () => { d.zoom = 1; render(); }, "small"),
        button("+", () => zoom(d, 1), "small", { "aria-label": t("step4.zoom_in"), title: t("step4.zoom_in") })],
      wholeSubmission() ? null : button(t("step4.adjust_box"), async () => {
        if (commentRefused() || !(await flushStep4())) return;
        goTo(2, { draft: { sub: "boxes", adjust: { qid: q.id, rid: item.r?.id || null, sid: student.id } } });
      }, "small ghost", { title: t("step4.adjust_box_hint") }),
      wholeSubmission() ? null : d.wholePage
        ? button(t("step4.back_to_answer"), () => { d.wholePage = false; render(); }, "small on")
        : button(["🔍 ", t("grade.see_whole_page")], () => {
          d.wholePage = true;
          d.pendingNote = null;
          d.pickedKeyword = null;
          d.page = firstPage(q.id);
          render();
        }, "small")));

  let body;
  let pageNav = null;
  let toolHint = null;
  if (d.wholePage && !wholeSubmission()) {
    const pages = student.pages || 1;
    const boxes = encodeURIComponent(q.boxes.join(","));
    pageNav = h("div", { class: "page-nav" },
      h("p", { class: "whole-page-grading center" }, t("step4.whole_page_grading", { label: itemLabel(item) })),
      h("div", { class: "row center" },
        button("‹", () => { if (d.page > 1) { d.page--; render(); } }, "small", { disabled: d.page <= 1, "aria-label": t("common.prev_page") }),
        h("span", {}, t("common.page_of", { page: d.page, pages })),
        button("›", () => { if (d.page < pages) { d.page++; render(); } }, "small", { disabled: d.page >= pages, "aria-label": t("common.next_page") })),
      h("p", { class: "muted small center" }, t("step4.whole_page_hint")));
    body = h("div", { class: "whole-page" },
      h("img", { src: `/api/page/${student.id}/${d.page}?w=1400&boxes=${boxes}&v=${stamp}`, alt: t("common.page_of", { page: d.page, pages }) }));
  } else {
    if (d.pickedKeyword) toolHint = h("p", { class: "tool-hint accent" }, t("step4.keywords_selected", { label: d.pickedKeyword.label }));
    else if (d.tool === "note") toolHint = h("p", { class: "tool-hint muted small" }, t("step4.note_click_hint"));
    else if (d.tool === "highlight") toolHint = h("p", { class: "tool-hint muted small" }, t("step4.hl_remove_hint"));

    const img = h("img", {
      src: wholeSubmission() ? `/api/page/${student.id}/${d.page}?w=1400&v=${stamp}` : `/api/crop/${q.id}/${student.id}?v=${stamp}`,
      alt: t("step4.answer_alt", { label: q.label,
        name: hideNames() ? t("step4.paper_of", { n: index + 1, total: c.students.length }) : student.display_name }),
      draggable: "false",
    });
    const layer = h("div", { class: `annot-layer tool-${d.tool} ${d.pickedKeyword ? "placing-kw" : ""}` });
    const stage = h("div", { class: "answer-stage", style: { width: `${d.zoom * 100}%` } }, img, layer);
    const scroller = h("div", { class: `answer-scroll tool-${d.tool}` }, stage);

    const geomNow = cachedGeometry(c, q.id, student.id);
    if (geomNow) {
      populateOverlay(layer, stage, geomNow, c, d, q, student);
    } else {
      loadGeometry(c, q.id, student.id, (geom) => {
        if (d.qid === q.id && d.sid === student.id && (!d.wholePage || wholeSubmission()) && layer.isConnected) {
          populateOverlay(layer, stage, geom, c, d, q, student);
        }
      });
    }
    attachStageInteractions(scroller, stage, layer, c, d, q, student);
    body = scroller;
    if (wholeSubmission()) {
      const changePage = async (page) => {
        if (commentRefused() || !(await flushStep4())) return;
        d.page = page; d.pendingNote = null; render();
      };
      pageNav = h("div", { class: "row center" },
        button("‹", () => changePage(d.page - 1), "small", { disabled: d.page <= 1 }),
        h("span", {}, t("common.page_of", { page: d.page, pages: student.pages })),
        button("›", () => changePage(d.page + 1), "small", { disabled: d.page >= student.pages }));
    }
    if (nextId && !wholeSubmission()) {
      new Image().src = `/api/crop/${q.id}/${nextId}?v=${stamp}`;
      loadGeometry(c, q.id, nextId);
    }
  }

  const viewerDone = isDraft() ? isSeen(student.id) : value !== null;
  return h("section", { class: `viewer ${viewerDone ? "graded" : ""}` }, head, toolHint, pageNav,
    h("div", { class: "viewer-frame" }, body,
      badge ? h("div", { class: `grade-badge ${badge === t("step4.badge_na") ? "na" : ""} ${badge.includes("\n") ? "multi" : ""}`,
        role: "status" }, badge) : null));
}

function populateOverlay(layer, stage, geom, c, d, q, student) {
  const e = entry(student.id, q.id);
  const projNotes = projectAnnotations(geom, e?.annotations).filter((a) => !geom.whole_page || geom.parts.some((p) => p.page === a.page));
  const projHls = projectHighlights(geom, e?.highlights);

  const children = [];
  for (const hl of projHls) {
    for (const piece of hl.pieces) {
      children.push(h("div", {
        class: `hl-rect hl-${hl.colour || "yellow"}`,
        dataset: { hlId: hl.id },
        style: { left: `${piece.nx * 100}%`, top: `${piece.ny * 100}%`,
          width: `${piece.nw * 100}%`, height: `${piece.nh * 100}%` },
        title: d.tool === "highlight" ? t("step4.remove_highlight") : null,
      }));
    }
  }

  for (const ann of projNotes) {
    const typeCls = ann.type === "strength" ? "strength" : ann.type === "growth" ? "growth" : "plain";
    const stampBtn = h("button", {
      type: "button",
      class: `note-stamp ${typeCls} ${ann.outOfCrop ? "check-pos" : ""}`,
      dataset: { noteId: ann.id },
      style: { left: `${ann.nx * 100}%`, top: `${ann.ny * 100}%` },
      title: ann.outOfCrop ? `${t("step4.note_check_pos")} — ${ann.text}` : ann.text,
      "aria-label": `${ann.num}: ${ann.text}`,
    }, String(ann.num));
    attachStampDrag(stampBtn, stage, geom, c, d, q, student, ann);
    children.push(stampBtn);
  }

  if (d.pendingNote) {
    children.push(notePopover(stage, d, q, student));
  }
  layer.replaceChildren(...children);
  if (d.pendingNote) {
    setTimeout(() => layer.querySelector(".note-popover textarea")?.focus(), 0);
  }
}

function notePopover(stage, d, q, student) {
  const pn = d.pendingNote;
  const noteLimit = app.session.comment_limits?.note || 120;
  let noteType = null;
  let composing = false;
  const counter = h("span", { class: "small muted" }, "");
  const textarea = h("textarea", {
    rows: "2",
    placeholder: t("step4.note_placeholder"),
    "aria-label": t("step4.note_place_here"),
    oncompositionstart: () => { composing = true; },
    oncompositionend: () => { composing = false; updateCount(); },
    oninput: () => { if (!composing) updateCount(); },
    onkeydown: (e) => {
      if (e.key === "Enter" && !e.shiftKey && !composing) {
        e.preventDefault();
        submit();
      } else if (e.key === "Escape") {
        d.pendingNote = null;
        render();
      }
    },
  });
  const updateCount = () => {
    const n = [...textarea.value].length;
    const over = n > noteLimit;
    textarea.classList.toggle("too-long", over);
    counter.className = over ? "small warn-text" : "small muted";
    counter.textContent = over ? t("comment.too_long", { count: n, limit: noteLimit })
      : n >= noteLimit * 0.8 ? `${n} / ${noteLimit}` : "";
    return over;
  };
  const submit = async () => {
    if (updateCount()) return;
    const text = textarea.value.trim();
    if (!text) {
      toast(t("error.note_text_required"), "error");
      textarea.focus();
      return;
    }
    if (commentRefused() || !(await flushStep4())) return;
    const limit = app.session.comment_limits?.notes_per_page || 8;
    if (countNotesOnPage(student.id, q.id, pn.page) >= limit) {
      toast(t("error.too_many_notes_on_page", { page: pn.page, limit }), "error");
      return;
    }
    const scrollTop = document.querySelector(".grade-card-col")?.scrollTop || 0;
    const data = await act(post("/api/annotations", {
      action: "add_note", student_id: student.id, question_id: q.id,
      page: pn.page, x: pn.x, y: pn.y, text, type: noteType,
    }), { rerender: false });
    if (data) {
      d.pendingNote = null;
      render();
      const panel = document.querySelector(".grade-card-col");
      if (panel) panel.scrollTop = scrollTop;
    }
  };
  const typeBtns = h("div", { class: "seg small-seg" },
    [
      [null, t("step4.note_type_plain")],
      ["strength", t("step4.note_type_strength")],
      ["growth", t("step4.note_type_growth")],
    ].map(([val, label]) => {
      const btn = h("button", {
        type: "button",
        class: noteType === val ? "on" : "",
        onclick: () => {
          noteType = val;
          [...typeBtns.children].forEach((b, i) => b.classList.toggle("on", [null, "strength", "growth"][i] === val));
        },
      }, label);
      return btn;
    }));
  const leftSide = pn.nx > 0.6;
  const topSide = pn.ny > 0.7;
  return h("div", {
    class: `note-popover ${leftSide ? "flip-x" : ""} ${topSide ? "flip-y" : ""}`,
    style: { left: `${pn.nx * 100}%`, top: `${pn.ny * 100}%` },
    onpointerdown: (e) => e.stopPropagation(),
  },
  h("div", { class: "row spread" }, h("strong", { class: "small" }, t("step4.note_place_here")),
    button("✕", () => { d.pendingNote = null; render(); }, "icon-btn", { "aria-label": t("common.cancel") })),
  typeBtns,
  textarea,
  h("div", { class: "row spread" }, counter, button(t("step4.note_add"), submit, "primary small")));
}

function stageCoords(stage, geom, clientX, clientY) {
  const rect = stage.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;
  const cx = ((clientX - rect.left) / rect.width) * geom.width;
  const cy = ((clientY - rect.top) / rect.height) * geom.height;
  return { cx, cy, nx: (clientX - rect.left) / rect.width, ny: (clientY - rect.top) / rect.height };
}

function attachStampDrag(stampBtn, stage, geom, c, d, q, student, ann) {
  stampBtn.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    const startX = e.clientX, startY = e.clientY;
    let moved = false;
    let lastPt = null;
    stampBtn.setPointerCapture(e.pointerId);
    stampBtn.classList.add("dragging");

    const onMove = (ev) => {
      if (!moved && Math.hypot(ev.clientX - startX, ev.clientY - startY) < 4) return;
      moved = true;
      const sc = stageCoords(stage, geom, ev.clientX, ev.clientY);
      if (!sc) return;
      const nx = Math.min(Math.max(sc.nx, 0), 1);
      const ny = Math.min(Math.max(sc.ny, 0), 1);
      stampBtn.style.left = `${nx * 100}%`;
      stampBtn.style.top = `${ny * 100}%`;
      lastPt = cropPointToPage(geom, sc.cx, sc.cy);
    };
    const cleanup = () => {
      stampBtn.classList.remove("dragging");
      stampBtn.removeEventListener("pointermove", onMove);
      stampBtn.removeEventListener("pointerup", onUp);
      stampBtn.removeEventListener("pointercancel", onCancel);
    };
    const onCancel = () => {
      cleanup();
      stampBtn.style.left = `${ann.nx * 100}%`;
      stampBtn.style.top = `${ann.ny * 100}%`;
    };
    const onUp = async () => {
      cleanup();
      if (!moved) {
        document.getElementById(`note-text-${ann.id}`)?.focus();
        return;
      }
      if (!lastPt) {
        stampBtn.style.left = `${ann.nx * 100}%`;
        stampBtn.style.top = `${ann.ny * 100}%`;
        toast(t("step4.note_drop_invalid"), "error");
        return;
      }
      const res = await annotate({
        action: "move_note", student_id: student.id, question_id: q.id,
        id: ann.id, page: lastPt.page, x: lastPt.x, y: lastPt.y,
      });
      if (!res) {
        stampBtn.style.left = `${ann.nx * 100}%`;
        stampBtn.style.top = `${ann.ny * 100}%`;
      }
    };
    stampBtn.addEventListener("pointermove", onMove);
    stampBtn.addEventListener("pointerup", onUp);
    stampBtn.addEventListener("pointercancel", onCancel);
  });
}

function attachStageInteractions(scroller, stage, layer, c, d, q, student) {
  scroller.addEventListener("wheel", (e) => {
    e.preventDefault();
    const next = Math.min(Math.max(d.zoom * (e.deltaY < 0 ? 1.15 : 1 / 1.15), ZOOMS[0]), ZOOMS[ZOOMS.length - 1]);
    d.zoom = Math.round(next * 100) / 100;
    stage.style.width = `${d.zoom * 100}%`;
  }, { passive: false });

  let panStart = null;
  let hlDrag = null;

  scroller.addEventListener("pointerdown", async (e) => {
    if (e.button !== 0) return;
    if (e.target.closest(".note-stamp") || e.target.closest(".note-popover")) return;

    const geom = cachedGeometry(c, q.id, student.id);

    // Click-to-place a selected quick comment works in any tool.
    if (d.pickedKeyword) {
      if (!geom) return;
      const sc = stageCoords(stage, geom, e.clientX, e.clientY);
      const pt = sc && cropPointToPage(geom, sc.cx, sc.cy);
      if (!pt) { toast(t("step4.note_drop_invalid"), "error"); return; }
      const kw = d.pickedKeyword;
      const res = await addNote(student.id, q.id, pt.page, pt.x, pt.y, kw.label, kw.type);
      if (res) { d.pickedKeyword = null; render(); }
      return;
    }

    if (d.tool === "note") {
      if (!geom) return;
      const sc = stageCoords(stage, geom, e.clientX, e.clientY);
      const pt = sc && cropPointToPage(geom, sc.cx, sc.cy);
      if (!pt) { toast(t("step4.note_drop_invalid"), "error"); return; }
      const limit = app.session.comment_limits?.notes_per_page || 8;
      if (countNotesOnPage(student.id, q.id, pt.page) >= limit) {
        toast(t("error.too_many_notes_on_page", { page: pt.page, limit }), "error");
        return;
      }
      d.pendingNote = {
        page: pt.page, x: pt.x, y: pt.y, cx: sc.cx, cy: sc.cy,
        nx: sc.cx / geom.width, ny: sc.cy / geom.height,
      };
      populateOverlay(layer, stage, geom, c, d, q, student);
      return;
    }

    if (d.tool === "highlight") {
      if (!geom) return;
      const sc = stageCoords(stage, geom, e.clientX, e.clientY);
      if (!sc) return;
      const hitHl = e.target.closest(".hl-rect")?.dataset?.hlId || null;
      const preview = h("div", { class: `hl-rect hl-${d.hlColour} preview`, hidden: true });
      layer.append(preview);
      hlDrag = {
        startX: e.clientX, startY: e.clientY,
        cx0: sc.cx, cy0: sc.cy, moved: false, hitHl, preview,
      };
      scroller.setPointerCapture(e.pointerId);
      return;
    }

    panStart = { x: e.clientX, y: e.clientY, left: scroller.scrollLeft, top: scroller.scrollTop };
    scroller.setPointerCapture(e.pointerId);
    scroller.classList.add("panning");
  });

  scroller.addEventListener("pointermove", (e) => {
    if (hlDrag) {
      const geom = cachedGeometry(c, q.id, student.id);
      if (!geom) return;
      if (!hlDrag.moved && Math.hypot(e.clientX - hlDrag.startX, e.clientY - hlDrag.startY) >= 4) {
        hlDrag.moved = true;
      }
      if (!hlDrag.moved) return;
      const sc = stageCoords(stage, geom, e.clientX, e.clientY);
      if (!sc) return;
      const snapped = snapHighlightFromCrop(geom, hlDrag.cx0, hlDrag.cy0, sc.cx, sc.cy);
      if (!snapped) { hlDrag.preview.hidden = true; return; }
      const pieces = projectHighlights(geom, [{ ...snapped, colour: d.hlColour }])[0]?.pieces || [];
      if (!pieces.length) { hlDrag.preview.hidden = true; return; }
      const piece = pieces[0];
      hlDrag.preview.hidden = false;
      Object.assign(hlDrag.preview.style, {
        left: `${piece.nx * 100}%`, top: `${piece.ny * 100}%`,
        width: `${piece.nw * 100}%`, height: `${piece.nh * 100}%`,
      });
      return;
    }
    if (!panStart) return;
    scroller.scrollLeft = panStart.left - (e.clientX - panStart.x);
    scroller.scrollTop = panStart.top - (e.clientY - panStart.y);
  });

  const stop = async (e) => {
    if (hlDrag) {
      const drag = hlDrag;
      hlDrag = null;
      drag.preview.remove();
      const geom = cachedGeometry(c, q.id, student.id);
      if (!drag.moved) {
        if (drag.hitHl) {
          await annotate({
            action: "delete_highlight", student_id: student.id, question_id: q.id, id: drag.hitHl,
          });
        }
        return;
      }
      if (!geom) return;
      const sc = stageCoords(stage, geom, e.clientX, e.clientY);
      const snapped = sc && snapHighlightFromCrop(geom, drag.cx0, drag.cy0, sc.cx, sc.cy);
      if (!snapped) {
        toast(t("step4.note_drop_invalid"), "error");
        return;
      }
      await annotate({
        action: "add_highlight", student_id: student.id, question_id: q.id,
        ...snapped, colour: d.hlColour,
      });
      return;
    }
    panStart = null;
    scroller.classList.remove("panning");
  };
  scroller.addEventListener("pointerup", stop);
  scroller.addEventListener("pointercancel", () => {
    if (hlDrag) { hlDrag.preview.remove(); hlDrag = null; }
    panStart = null;
    scroller.classList.remove("panning");
  });
}

function zoom(d, dir) {
  const i = ZOOMS.findIndex((z) => z >= d.zoom);
  d.zoom = ZOOMS[Math.min(Math.max((i < 0 ? ZOOMS.length - 1 : i) + dir, 0), ZOOMS.length - 1)];
  render();
}

// --- Right: the grading card ----------------------------------------------------------------

function typeTag(type) {
  if (type === "strength") return h("span", { class: "type-tag strength" }, t("step4.note_type_strength"));
  if (type === "growth") return h("span", { class: "type-tag growth" }, t("step4.note_type_growth"));
  return null;
}

function attachQuickCommentDrag(pill, kw, c, d, q, student) {
  pill.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    const startX = e.clientX, startY = e.clientY;
    let dragging = false;
    let ghost = null;
    pill.setPointerCapture(e.pointerId);

    const onMove = (ev) => {
      if (!dragging && Math.hypot(ev.clientX - startX, ev.clientY - startY) < 6) return;
      if (!dragging) {
        dragging = true;
        ghost = h("div", { class: `kw-drag-ghost ${kw.type || "plain"}` }, kw.label);
        document.body.append(ghost);
      }
      ghost.style.left = `${ev.clientX + 10}px`;
      ghost.style.top = `${ev.clientY + 10}px`;
    };
    const cleanup = () => {
      if (ghost) ghost.remove();
      pill.removeEventListener("pointermove", onMove);
      pill.removeEventListener("pointerup", onUp);
      pill.removeEventListener("pointercancel", cleanup);
    };
    const onUp = async (ev) => {
      cleanup();
      if (!dragging) {
        const same = d.pickedKeyword && d.pickedKeyword.label === kw.label && d.pickedKeyword.type === kw.type;
        d.pickedKeyword = same ? null : { label: kw.label, type: kw.type };
        if (d.pickedKeyword && d.wholePage && !wholeSubmission()) d.wholePage = false;
        render();
        return;
      }
      if (d.wholePage && !wholeSubmission()) return;
      const stage = document.querySelector(".answer-stage");
      const geom = cachedGeometry(c, q.id, student.id);
      if (!stage || !geom) return;
      const rect = stage.getBoundingClientRect();
      if (ev.clientX < rect.left || ev.clientX > rect.right || ev.clientY < rect.top || ev.clientY > rect.bottom) {
        return;
      }
      const sc = stageCoords(stage, geom, ev.clientX, ev.clientY);
      const pt = sc && cropPointToPage(geom, sc.cx, sc.cy);
      if (!pt) {
        toast(t("step4.note_drop_invalid"), "error");
        return;
      }
      await addNote(student.id, q.id, pt.page, pt.x, pt.y, kw.label, kw.type);
    };
    pill.addEventListener("pointermove", onMove);
    pill.addEventListener("pointerup", onUp);
    pill.addEventListener("pointercancel", cleanup);
  });
}

function notesSection(c, d, q, student) {
  const e = entry(student.id, q.id);
  const anns = e?.annotations || [];
  const hls = e?.highlights || [];
  const geom = wholeSubmission() ? null : cachedGeometry(c, q.id, student.id);
  const projNotes = geom ? projectAnnotations(geom, anns)
    : anns.map((a, i) => ({ ...a, num: i + 1, outOfCrop: false }));
  const excludedHls = geom ? projectHighlights(geom, hls).filter((x) => x.excluded) : [];
  const noteLimit = app.session.comment_limits?.note || 120;
  const pageLimit = app.session.comment_limits?.notes_per_page || 8;

  const pageCounts = new Map();
  for (const a of anns) {
    const p = Number(a.page || 1);
    pageCounts.set(p, (pageCounts.get(p) || 0) + 1);
  }
  const nearLimitPages = [...pageCounts.entries()].filter(([, n]) => n >= pageLimit - 1)
    .map(([p, n]) => t("step4.notes_page_count", { page: p, count: n, limit: pageLimit }));

  const noteItems = projNotes.map((ann) => {
    const saver = noteSaver(student.id, q.id, ann.id);
    const [box, noteCounter] = commentField({
      key: `note/${student.id}/${q.id}/${ann.id}`,
      limit: noteLimit,
      saved: () => (entry(student.id, q.id)?.annotations || []).find((x) => x.id === ann.id)?.text || "",
      save: (text) => saver(text),
      flush: () => saver.flush(),
      attrs: { id: `note-text-${ann.id}`, rows: "2", class: "note-textarea",
        "aria-label": `${ann.num}` },
    });
    const typeCls = ann.type === "strength" ? "strength" : ann.type === "growth" ? "growth" : "plain";
    return h("li", { class: `note-item ${ann.outOfCrop ? "check-pos" : ""}` },
      h("div", { class: "row spread note-item-head" },
        h("div", { class: "row" },
          h("span", { class: `note-num ${typeCls}` }, String(ann.num)),
          h("select", {
            class: "note-type-select",
            "aria-label": t("step4.note_type"),
            onchange: (ev) => annotate({
              action: "update_note", student_id: student.id, question_id: q.id,
              id: ann.id, type: ev.target.value || null,
            }),
          },
          h("option", { value: "", selected: !ann.type ? "selected" : null }, t("step4.note_type_plain")),
          h("option", { value: "strength", selected: ann.type === "strength" ? "selected" : null }, t("step4.note_type_strength")),
          h("option", { value: "growth", selected: ann.type === "growth" ? "selected" : null }, t("step4.note_type_growth"))),
          typeTag(ann.type)),
        button("✕", () => annotate({
          action: "delete_note", student_id: student.id, question_id: q.id, id: ann.id,
        }), "icon-btn", { title: t("step4.note_delete"), "aria-label": t("step4.note_delete") })),
      ann.outOfCrop ? h("div", { class: "row spread check-pos-bar" },
        h("span", { class: "warn-text small" }, "⚠ ", t("step4.note_check_pos")),
        button(t("step4.note_confirm_pos"), () => annotate({
          action: "move_note", student_id: student.id, question_id: q.id,
          id: ann.id, page: ann.confirmedPage, x: ann.confirmedX, y: ann.confirmedY,
        }), "small")) : null,
      box,
      noteCounter);
  });

  const excludedBox = excludedHls.length
    ? h("div", { class: "excluded-highlights" },
      h("p", { class: "label small warn-text" }, t("step4.excluded_highlights")),
      excludedHls.map((hl) => h("div", { class: "row spread excluded-hl-row" },
        h("span", { class: "small" }, h("span", { class: `hl-dot hl-${hl.colour || "yellow"}` }),
          t("step4.excluded_hl_item", { page: hl.page, colour: colourName(hl.colour) })),
        button(t("step4.remove_highlight"), () => annotate({
          action: "delete_highlight", student_id: student.id, question_id: q.id, id: hl.id,
        }), "small ghost"))))
    : null;

  return h("div", { class: "notes-section" },
    h("div", { class: "row spread" },
      h("span", { class: "label" }, t("step4.notes_title")),
      nearLimitPages.length ? h("span", { class: "muted small" }, nearLimitPages.join(" · ")) : null),
    noteItems.length
      ? h("ol", { class: "notes-list" }, noteItems)
      : h("p", { class: "muted small" }, t("step4.notes_none")),
    excludedBox);
}

function gradeCard(c, d, item, student) {
  const q = item.q;
  const r = item.r;
  const value = valueOf(student.id, q.id, r?.id);
  const choose = (v) => setGrade(student.id, q.id, v, r?.id);
  const notAnswered = () => setGrade(student.id, q.id, NA);
  const clear = () => setGrade(student.id, q.id, null, value === NA ? null : r?.id);

  let grading;
  if (wholeSubmission() && !r) {
    grading = null;
  } else if (r) {
    const crit = criteriaOf(c, q);
    const cap = q.level_caps?.[r.id] ?? null;
    const capBand = cap !== null ? r.bands.find((b) => Number(b.max) === Number(cap)) : null;
    const capNote = cap !== null ? h("p", { class: "muted small cap-hint" },
      t("step4.up_to", { levels: capBand ? capBand.levels : cap })) : null;
    grading = h("div", { class: "bands-grade" },
      crit.length > 1 ? criterionTabs(crit, q, student, r) : h("p", { class: "muted small" }, r.name),
      capNote,
      r.bands.filter((band) => cap === null || band.min <= cap).map((band) => {
        const hi = cap === null ? band.max : Math.min(band.max, cap);
        const inBand = typeof value === "number" && band.min <= value && value <= hi;
        const levels = [];
        for (let l = band.min; l <= hi; l++) levels.push(l);
        return h("div", { class: `band-card ${inBand ? "on" : ""}` },
          h("div", { class: "band-head" }, h("strong", {}, band.levels),
            h("div", { class: "row" }, levels.map((l) => h("button", {
              type: "button", class: `level-btn ${value === l ? "on" : ""}`, "aria-pressed": value === l ? "true" : "false",
              onclick: () => choose(l) }, String(l))))),
          band.descriptor ? h("p", { class: "descriptor" }, band.descriptor) : null);
      }));
  } else if (q.max <= MAX_BUTTONS) {
    const marks = [];
    for (let m = 0; m <= q.max; m++) marks.push(m);
    grading = h("div", { class: "mark-buttons" }, marks.map((m) => h("button", {
      type: "button", class: `mark-btn ${value === m ? "on" : ""}`, "aria-pressed": value === m ? "true" : "false",
      onclick: () => choose(m) }, String(m))));
  } else {
    const current = typeof value === "number" ? value : "";
    const input = h("input", { type: "number", id: "mark-input", class: "num big-num", min: "0", max: String(q.max),
      value: current, "aria-label": t("step4.marks_out_of", { max: q.max }),
      onchange: (e) => { if (e.target.value !== "") choose(parseInt(e.target.value, 10)); } });
    const bump = (by) => {
      const now = typeof value === "number" ? value : 0;
      choose(Math.min(Math.max(now + by, 0), q.max));
    };
    grading = h("div", { class: "row mark-input" },
      button("−", () => bump(-1), "big", { "aria-label": t("step4.one_less") }), input,
      button("+", () => bump(1), "big", { "aria-label": t("step4.one_more") }),
      h("span", { class: "muted" }, `/ ${q.max}`));
  }

  const pills = h("div", { class: "keyword-pills" },
    h("div", { class: "row spread" }, h("span", { class: "label" }, t("step4.keywords")),
      button(t("step4.keywords_edit"), () => editKeywords(c), "small ghost")),
    h("p", { class: "muted small kw-hint" }, t("step4.keywords_drag_hint")),
    h("div", { class: "kw-list" }, (c.keywords || []).map((k) => {
      const selected = d.pickedKeyword && d.pickedKeyword.label === k.label && d.pickedKeyword.type === k.type;
      const pill = h("button", {
        type: "button",
        class: `kw-pill ${k.type || "plain"} ${selected ? "selected" : ""}`,
        "aria-pressed": selected ? "true" : "false",
      }, h("span", { class: "kw-pill-text" }, k.label), typeTag(k.type));
      attachQuickCommentDrag(pill, k, c, d, q, student);
      return pill;
    })));

  const qLimit = wholeSubmission() ? app.session.comment_limits.overall : app.session.comment_limits?.per_question?.[q.id] ?? app.session.comment_limits.question;
  const commentBox = commentField({
    key: `${student.id}/${q.id}`,
    limit: qLimit,
    saved: () => wholeSubmission() ? app.session.grades.overall?.[student.id]?.comment || "" : entry(student.id, q.id)?.comment || "",
    save: (text) => saveComment(student.id, q.id, text),
    flush: saveComment.flush,
    attrs: { id: "comment-box", rows: "3",
      placeholder: t(wholeSubmission() ? "report.overall_comment" : "grade.comment_placeholder"),
      "aria-label": t(wholeSubmission() ? "report.overall_comment" : "grade.comment_placeholder") },
  });

  const nextId = nextStudentId(c, d, 1);
  const outOf = r || wholeSubmission() ? "" : t("step4.out_of", { max: q.max });
  const cardDone = isDraft() ? isSeen(student.id) : value !== null;
  let metaBox = null;
  if (wholeSubmission()) {
    const late = isLate(student.id);
    const pInfo = partnerInfo(c, student.id);
    const pLabel = !pInfo
      ? null
      : (hideNames() && d.revealed !== student.id)
        ? t("partners.group_anon", { n: pInfo.num, count: pInfo.members.length })
        : t("partners.group_with", { n: pInfo.num, names: pInfo.others.map((m) => m.display_name).join(", ") });
    metaBox = h("div", { class: "submission-meta" },
      h("label", { class: "check late-check" },
        h("input", {
          type: "checkbox", id: "late-check", checked: late,
          onchange: async (ev) => {
            const want = ev.target.checked;
            if (commentRefused() || !(await flushStep4())) { ev.target.checked = late; return; }
            await actKeepingScroll(post("/api/overall", { student_id: student.id, late: want }));
          },
        }),
        t("step4.late_label")),
      h("div", { class: "row partner-meta" },
        pLabel ? h("span", { class: "badge partner-badge" }, pLabel) : null,
        button(pInfo ? t("partners.manage") : t("partners.link_action"),
          () => openPartnerModal(student.id), "small ghost", { id: "partner-btn" })));
  }
  return h("section", { class: `card grade-card ${cardDone ? "graded" : ""}` },
    h("h2", {}, h("span", { class: "question-name" }, itemLabel(item)), outOf ? h("span", { class: "muted" }, " · ", outOf) : null),
    hideNames() && d.revealed !== student.id ? null : h("p", { class: "muted small" }, student.display_name),
    metaBox,
    grading,
    wholeSubmission() && !r ? null : h("div", { class: "row" },
      button(t("grade.not_answered"), notAnswered, value === NA ? "small on" : "small", { "aria-pressed": value === NA ? "true" : "false" }),
      value !== null ? button(t("step4.clear"), clear, "small ghost") : null),
    pills,
    notesSection(c, d, q, student),
    h("label", { class: "comment" }, h("span", { class: "label" }, t(wholeSubmission() ? "report.overall_comment" : "step4.comment")), commentBox),
    nextId
      ? button(t("step4.next_paper_button"), () => moveTo({ sid: nextId }), "primary big", { id: "next-paper" })
      : lastPaperActions(c, d, item));
}

// The exam's quick comments: up to 8 items (or keeping/shortening a longer
// existing list), up to 120 characters each, with optional Strength / Area to develop.
function editKeywords(c) {
  const maxItems = app.session.comment_limits?.keywords_max || 8;
  const maxLabel = app.session.comment_limits?.note || 120;
  const rows = (c.keywords || []).map((k) => ({ label: k.label, type: k.type || "" }));
  const oldLengths = new Map((c.keywords || []).map((k) => [k.label.toLowerCase(), [...k.label].length]));
  const listEl = h("div", { class: "stack kw-edit-list" });
  const addBtn = button(t("step4.keywords_add"), () => {
    rows.push({ label: "", type: "" });
    drawRows();
    listEl.lastElementChild?.querySelector("input")?.focus();
  }, "small");

  const drawRows = () => {
    addBtn.disabled = rows.length >= maxItems;
    listEl.replaceChildren(...rows.map((row, idx) => {
      const countEl = h("span", { class: "small muted" }, "");
      const updateCount = () => {
        const len = [...row.label.trim()].length;
        const allowed = Math.max(maxLabel, oldLengths.get(row.label.trim().toLowerCase()) || 0);
        const over = len > allowed;
        input.classList.toggle("too-long", over);
        countEl.className = over ? "small warn-text" : "small muted";
        countEl.textContent = len >= maxLabel * 0.8 ? `${len} / ${maxLabel}` : "";
      };
      const input = h("input", {
        type: "text", value: row.label, placeholder: t("step4.keywords_label_placeholder"),
        oninput: (ev) => { row.label = ev.target.value; updateCount(); },
      });
      const sel = h("select", {
        "aria-label": t("step4.note_type"),
        onchange: (ev) => { row.type = ev.target.value; },
      },
      h("option", { value: "", selected: !row.type ? "selected" : null }, t("step4.note_type_plain")),
      h("option", { value: "strength", selected: row.type === "strength" ? "selected" : null }, t("step4.note_type_strength")),
      h("option", { value: "growth", selected: row.type === "growth" ? "selected" : null }, t("step4.note_type_growth")));
      updateCount();
      return h("div", { class: "kw-edit-row" },
        input, sel, countEl,
        button("✕", () => { rows.splice(idx, 1); drawRows(); }, "icon-btn", {
          title: t("step4.keywords_remove"), "aria-label": t("step4.keywords_remove"),
        }));
    }));
  };
  drawRows();

  modal({
    title: t("step4.keywords_title"),
    body: h("div", { class: "stack" },
      h("p", { class: "muted small" }, t("step4.keywords_hint")),
      listEl,
      h("div", { class: "row" }, addBtn)),
    actions: [
      { label: t("common.cancel") },
      { label: t("common.save"), kind: "primary", keepOpen: true, onClick: async (close) => {
        const payload = rows
          .map((r) => ({ label: r.label.trim(), type: r.type || null }))
          .filter((r) => r.label);
        const data = await act(post("/api/setup/keywords", { keywords: payload }));
        if (data) close();
      } },
    ],
  });
}

function criterionTabs(crit, q, student, current) {
  return h("div", { class: "seg criterion-tabs", role: "tablist", "aria-label": t("step4.criteria") },
    crit.map((x) => {
      const v = valueOf(student.id, q.id, x.id);
      const shown = v === null ? "—" : v === NA ? t("step5.na_short") : String(v);
      return h("button", { type: "button", role: "tab", class: x.id === current.id ? "on" : "",
        "aria-selected": x.id === current.id ? "true" : "false",
        onclick: () => moveTo({ rid: x.id }) },
      x.name, h("span", { class: `tab-level ${v === null ? "muted" : ""}` }, shown));
    }));
}

function lastPaperActions(c, d, item) {
  const list = items(c);
  const next = list[list.findIndex((x) => x.q === item.q && x.r === item.r) + 1];
  return [h("p", { class: "last-paper" }, t("step4.last_paper", { label: itemLabel(item) })),
    next
      ? button(t("step4.go_to_question", { label: itemLabel(next) }), () => {
        moveTo({ qid: next.q.id, rid: next.r?.id || null, sid: firstFor(c, d, next), arrived: true });
      }, "next-question big", { id: "next-paper" })
      : button(t("step4.to_review"), () => goTo(5, { next: true }), "primary big", { id: "next-paper" })];
}

function doneCard(c, item) {
  if (isDraft()) {
    return h("section", { class: "card grade-card graded" },
      h("h2", {}, "✓ ", t("step4.all_seen")),
      h("p", {}, t("step4.everything_seen")),
      button(t("step4.to_review"), () => goTo(5, { next: true }), "primary big", { id: "next-paper" }),
      h("p", { class: "muted small" }, t("step4.show_all_seen_hint")));
  }
  const remaining = items(c).find((x) => c.students.some((s) => !isItemDone(s.id, x.q.id, x.r?.id)));
  return h("section", { class: "card grade-card graded" },
    h("h2", {}, "✓ ", t("step4.all_done", { label: itemLabel(item) })),
    remaining
      ? [h("p", {}, t("step4.next_question_hint", { label: itemLabel(remaining) })),
        button(t("step4.go_to_question", { label: itemLabel(remaining) }), () => moveTo({ qid: remaining.q.id,
          rid: remaining.r?.id || null,
          sid: firstFor(c, { ungradedOnly: true }, remaining), arrived: true }),
        "next-question big", { id: "next-paper" })]
      : [h("p", {}, t("step4.everything_done")),
        button(t("step4.to_review"), () => goTo(5, { next: true }), "primary big", { id: "next-paper" })],
    h("p", { class: "muted small" }, t("step4.show_all_hint")));
}

// --- Class grid (F11) ----------------------------------------------------------------------

function gridGradeBadge(q, r, value, student) {
  if (isDraft()) {
    return isSeen(student.id)
      ? h("span", { class: "grid-grade graded" }, t("step4.grid_seen"))
      : h("span", { class: "grid-grade ungraded" }, t("step4.grid_unseen"));
  }
  if (value === null) {
    return h("span", { class: "grid-grade ungraded" }, t("step4.grid_ungraded"));
  }
  if (value === NA) {
    return h("span", { class: "grid-grade na" }, t("step5.na_short"));
  }
  const max = r ? Math.max(...r.bands.map((b) => b.max)) : q.max;
  return h("span", { class: "grid-grade graded" }, `${value} / ${max}`);
}

function gridStudents(c, d, q, rid) {
  const rows = papers(c, q.id).map((student, idx) => ({
    student,
    paperNum: idx + 1,
    value: valueOf(student.id, q.id, rid),
  }));
  const filtered = rows.filter((row) => {
    if (d.gridFilter === "unseen") return !isSeen(row.student.id);
    if (d.gridFilter === "seen") return isSeen(row.student.id);
    if (d.gridFilter === "late") return isLate(row.student.id);
    if (d.gridFilter === "ungraded") return row.value === null;
    if (d.gridFilter === "graded") return typeof row.value === "number";
    if (d.gridFilter === "na") return row.value === NA;
    if (d.gridFilter === "noted") return hasAnnotationOrComment(row.student.id, q.id);
    return true;
  });
  if (d.gridView !== "question" || d.gridSort === "order") return filtered;

  const bucket = (v) => (typeof v === "number" ? 0 : v === NA ? 1 : 2);
  const desc = d.gridSort === "grade_desc";
  return [...filtered].sort((a, b) => {
    const ba = bucket(a.value), bb = bucket(b.value);
    if (ba !== bb) return ba - bb;
    if (ba === 0 && a.value !== b.value) return desc ? b.value - a.value : a.value - b.value;
    return a.paperNum - b.paperNum;
  });
}

function renderCardOverlay(overlay, geom, c, q, sid) {
  const e = entry(sid, q.id);
  const projNotes = projectAnnotations(geom, e?.annotations).filter((a) => !geom.whole_page || geom.parts.some((p) => p.page === a.page));
  const projHls = projectHighlights(geom, e?.highlights);
  const children = [];
  for (const hl of projHls) {
    for (const piece of hl.pieces) {
      children.push(h("div", {
        class: `hl-rect hl-${hl.colour || "yellow"}`,
        style: { left: `${piece.nx * 100}%`, top: `${piece.ny * 100}%`,
          width: `${piece.nw * 100}%`, height: `${piece.nh * 100}%` },
      }));
    }
  }
  for (const ann of projNotes) {
    const typeCls = ann.type === "strength" ? "strength" : ann.type === "growth" ? "growth" : "plain";
    children.push(h("span", {
      class: `note-stamp mini ${typeCls} ${ann.outOfCrop ? "check-pos" : ""}`,
      style: { left: `${ann.nx * 100}%`, top: `${ann.ny * 100}%` },
    }, String(ann.num)));
  }
  overlay.replaceChildren(...children);
}

function observeGridCards(thumbBoxes, c, q) {
  const loadBox = (box) => {
    const img = box.querySelector("img.grid-thumb-img");
    const want = box.dataset.thumbSrc;
    if (img && want && img.getAttribute("src") !== want) {
      img.src = want;
    }
    if (box.dataset.hasMarks === "1" && !box.dataset.overlayDone) {
      box.dataset.overlayDone = "1";
      const sid = box.dataset.sid;
      const overlay = box.querySelector(".grid-annot-layer");
      if (sid && overlay) {
        const cached = cachedGeometry(c, q.id, sid);
        if (cached) {
          renderCardOverlay(overlay, cached, c, q, sid);
        } else {
          loadGeometry(c, q.id, sid, (geom) => {
            if (overlay.isConnected) renderCardOverlay(overlay, geom, c, q, sid);
          });
        }
      }
    }
  };

  if (typeof IntersectionObserver === "undefined") {
    thumbBoxes.forEach(loadBox);
    return;
  }

  gridObserver = new IntersectionObserver((entries) => {
    for (const ev of entries) {
      const box = ev.target;
      if (ev.isIntersecting) {
        loadBox(box);
      } else {
        const img = box.querySelector("img.grid-thumb-img");
        if (img && img.hasAttribute("src")) {
          if (box.clientHeight > 0) box.style.minHeight = `${box.clientHeight}px`;
          if (img.naturalWidth > 0 && img.naturalHeight > 0) {
            const stage = box.querySelector(".grid-stage");
            if (stage) stage.style.aspectRatio = `${img.naturalWidth} / ${img.naturalHeight}`;
          }
          img.removeAttribute("src");
        }
      }
    }
  }, { root: null, rootMargin: "350px 0px", threshold: 0 });

  for (const box of thumbBoxes) gridObserver.observe(box);
}

function classGridSection(c, d, item) {
  const q = item.q;
  const r = item.r;
  const rid = r?.id || null;
  const cols = gridColumns();
  const stamp = encodeURIComponent(c.sliced_at || "");
  const totalCount = c.students.length;
  const draftTask = isDraft();
  const whole = wholeSubmission();
  const filterOptions = draftTask
    ? [
      ["all", t("step4.grid_filter_all")],
      ["unseen", t("step4.grid_filter_unseen")],
      ["seen", t("step4.grid_filter_seen")],
      ["late", t("step4.grid_filter_late")],
    ]
    : [
      ["all", t("step4.grid_filter_all")],
      ["ungraded", t("step4.grid_filter_ungraded")],
      ["graded", t("step4.grid_filter_graded")],
      ["na", t("step4.grid_filter_na")],
      ["noted", t("step4.grid_filter_noted")],
      ...(whole ? [["late", t("step4.grid_filter_late")]] : []),
    ];
  if (!filterOptions.some(([val]) => val === d.gridFilter)) d.gridFilter = "all";
  const rows = gridStudents(c, d, q, rid);
  const filtered = rows.length !== totalCount;
  const boxesParam = encodeURIComponent((q.boxes || []).join(","));
  const partCount = (q.boxes || []).length;

  const toolbar = h("div", { class: "grid-toolbar" },
    h("div", { class: "row" },
      whole ? null : h("div", { class: "seg", role: "group", "aria-label": t("step4.grid_view") },
        h("button", { type: "button", class: d.gridView === "question" ? "on" : "",
          "aria-pressed": d.gridView === "question" ? "true" : "false",
          onclick: () => { d.gridView = "question"; d.gridScroll = 0; render(); } }, t("step4.grid_view_question")),
        h("button", { type: "button", class: d.gridView === "papers" ? "on" : "",
          "aria-pressed": d.gridView === "papers" ? "true" : "false",
          onclick: () => { d.gridView = "papers"; d.gridScroll = 0; render(); } }, t("step4.grid_view_papers"))),
      h("div", { class: "row grid-cols-pick", role: "group", "aria-label": t("step4.grid_columns") },
        h("span", { class: "label small" }, t("step4.grid_columns")),
        h("div", { class: "seg small-seg" }, [2, 3, 4, 5].map((n) => h("button", {
          type: "button", class: cols === n ? "on" : "",
          "aria-pressed": cols === n ? "true" : "false",
          onclick: () => setPref("grid_columns", n),
        }, String(n)))))),
    h("div", { class: "row" },
      d.gridView === "question"
        ? h("label", { class: "inline" }, h("span", { class: "label small" }, t("step4.grid_sort")),
          h("select", { id: "grid-sort", onchange: (ev) => { d.gridSort = ev.target.value; render(); } },
            h("option", { value: "order", selected: d.gridSort === "order" ? "selected" : null },
              shufflePapers() ? t("step4.grid_sort_shuffled") : t("step4.grid_sort_order")),
            h("option", { value: "grade_desc", selected: d.gridSort === "grade_desc" ? "selected" : null },
              t("step4.grid_sort_high")),
            h("option", { value: "grade_asc", selected: d.gridSort === "grade_asc" ? "selected" : null },
              t("step4.grid_sort_low"))))
        : null,
      h("label", { class: "inline" }, h("span", { class: "label small" }, t("step4.grid_filter")),
        h("select", { id: "grid-filter", onchange: (ev) => { d.gridFilter = ev.target.value; render(); } },
          filterOptions.map(([val, label]) => h("option", { value: val, selected: d.gridFilter === val ? "selected" : null }, label)))),
      h("span", { class: `grid-count small ${filtered ? "filtered" : "muted"}`, role: "status" },
        filtered ? t("step4.grid_showing", { shown: rows.length, total: totalCount })
          : t("step4.grid_showing_all", { total: totalCount })),
      filtered ? button(t("step4.grid_show_all"), () => { d.gridFilter = "all"; render(); }, "small ghost") : null));

  if (!rows.length) {
    return [toolbar, h("section", { class: "card center grid-empty" },
      h("p", { class: "muted" }, t("step4.grid_empty")),
      button(t("step4.grid_show_all"), () => { d.gridFilter = "all"; render(); }, "primary small"))];
  }

  const thumbBoxes = [];
  const cards = rows.map(({ student, paperNum, value }) => {
    const labelName = hideNames() ? t("step4.grid_paper_num", { n: paperNum }) : student.display_name;
    const headTitle = hideNames() ? labelName : `#${paperNum} ${student.display_name}`;
    const e = entry(student.id, q.id);
    const noteCount = (e?.annotations || []).length;
    const hlCount = (e?.highlights || []).length;
    const hasComment = !!((whole && app.session?.grades?.overall?.[student.id]?.comment?.trim()) || (e?.comment || "").trim());
    const cardDone = draftTask ? isSeen(student.id) : value !== null;
    const cardBadges = [];
    if (whole) {
      if (isLate(student.id)) cardBadges.push(h("span", { class: "badge warn-badge" }, t("step4.late_badge")));
      const pi = partnerInfo(c, student.id);
      if (pi) cardBadges.push(h("span", { class: "badge partner-badge" }, t("partners.group_n", { n: pi.num })));
      if (noteCount > 0) {
        cardBadges.push(h("span", { class: "badge" }, noteCount === 1
          ? t("step4.grid_notes_one") : t("step4.grid_notes_many", { n: noteCount })));
      }
      if (hasComment) cardBadges.push(h("span", { class: "badge" }, t("step4.grid_comment")));
    }

    let preview;
    let footer = null;
    if (d.gridView === "papers") {
      const pages = student.pages || 1;
      let cardPage = Math.min(Math.max(Number(d.gridPages[student.id] || 1), 1), pages);
      const pageUrl = (pg) => `/api/page/${encodeURIComponent(student.id)}/${pg}?w=${GRID_THUMB_WIDTH}&boxes=${boxesParam}&v=${stamp}`;
      const img = h("img", { class: "grid-thumb-img", alt: labelName, decoding: "async" });
      const thumbBox = h("div", {
        class: "grid-thumb-viewport whole",
        dataset: { sid: student.id, thumbSrc: pageUrl(cardPage) },
      }, img);
      img.onload = () => {
        if (thumbBox.clientHeight > 0) thumbBox.style.minHeight = `${thumbBox.clientHeight}px`;
      };
      thumbBoxes.push(thumbBox);
      preview = thumbBox;

      const pageSpan = h("span", { class: "small muted" }, t("common.page_of", { page: cardPage, pages }));
      const prevBtn = button("‹", (ev) => {
        ev.stopPropagation();
        if (cardPage <= 1) return;
        cardPage -= 1;
        d.gridPages[student.id] = cardPage;
        const url = pageUrl(cardPage);
        thumbBox.dataset.thumbSrc = url;
        img.src = url;
        pageSpan.textContent = t("common.page_of", { page: cardPage, pages });
        prevBtn.disabled = cardPage <= 1;
        nextBtn.disabled = cardPage >= pages;
      }, "small", { disabled: cardPage <= 1, "aria-label": t("common.prev_page") });
      const nextBtn = button("›", (ev) => {
        ev.stopPropagation();
        if (cardPage >= pages) return;
        cardPage += 1;
        d.gridPages[student.id] = cardPage;
        const url = pageUrl(cardPage);
        thumbBox.dataset.thumbSrc = url;
        img.src = url;
        pageSpan.textContent = t("common.page_of", { page: cardPage, pages });
        prevBtn.disabled = cardPage <= 1;
        nextBtn.disabled = cardPage >= pages;
      }, "small", { disabled: cardPage >= pages, "aria-label": t("common.next_page") });

      footer = h("div", { class: "row spread grid-card-foot grid-card-pager" },
        prevBtn, pageSpan, nextBtn);
    } else {
      const thumbUrl = `/api/crop/${encodeURIComponent(q.id)}/${encodeURIComponent(student.id)}?w=${GRID_THUMB_WIDTH}&v=${stamp}`;
      const img = h("img", { class: "grid-thumb-img", alt: labelName, decoding: "async" });
      const overlay = h("div", { class: "annot-layer grid-annot-layer" });
      const stage = h("div", { class: "grid-stage" }, img, overlay);
      const cached = cachedGeometry(c, q.id, student.id);
      if (cached?.width && cached?.height) {
        stage.style.aspectRatio = `${cached.width} / ${cached.height}`;
      }
      const thumbBox = h("div", {
        class: "grid-thumb-viewport",
        dataset: { sid: student.id, thumbSrc: thumbUrl, hasMarks: (noteCount || hlCount) ? "1" : "0" },
      }, stage);
      img.onload = () => {
        if (img.naturalWidth > 0 && img.naturalHeight > 0) {
          stage.style.aspectRatio = `${img.naturalWidth} / ${img.naturalHeight}`;
        }
        if (thumbBox.clientHeight > 0) thumbBox.style.minHeight = `${thumbBox.clientHeight}px`;
      };
      thumbBoxes.push(thumbBox);
      preview = thumbBox;

      const meta = [];
      if (partCount > 1) meta.push(h("span", { class: "badge" }, t("step4.grid_parts", { n: partCount })));
      if (noteCount > 0) {
        meta.push(h("span", { class: "badge" }, noteCount === 1
          ? t("step4.grid_notes_one") : t("step4.grid_notes_many", { n: noteCount })));
      }
      if (hasComment) meta.push(h("span", { class: "badge" }, t("step4.grid_comment")));
      if (meta.length) footer = h("div", { class: "row grid-card-foot" }, meta);
    }

    const openTarget = () => (d.gridView === "papers"
      ? openCard(student.id, { wholePage: true, page: Math.min(Math.max(Number(d.gridPages[student.id] || 1), 1), student.pages || 1) })
      : openCard(student.id, { wholePage: false }));

    return h("article", {
      class: `grid-card ${cardDone ? "graded" : ""} ${student.id === d.sid ? "current" : ""}`,
      role: "button",
      tabindex: "0",
      dataset: { studentId: student.id },
      "aria-label": t("step4.grid_open_paper", { name: labelName }),
      onclick: openTarget,
      onkeydown: (ev) => {
        if (ev.target !== ev.currentTarget) return;
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          openTarget();
        }
      },
    },
    h("div", { class: "row spread grid-card-head" },
      h("strong", { class: "grid-card-name" }, headTitle),
      gridGradeBadge(q, r, value, student)),
    cardBadges.length ? h("div", { class: "row grid-card-badges" }, cardBadges) : null,
    preview,
    footer);
  });

  const gridEl = h("div", { class: `class-grid cols-${cols}` }, cards);
  requestAnimationFrame(() => observeGridCards(thumbBoxes, c, q));
  return [toolbar, gridEl];
}
