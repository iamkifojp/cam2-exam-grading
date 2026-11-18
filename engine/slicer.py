"""Scans, grid geometry and cropping.

Ported from CAM's ``cam_grading_workspace/exam_engine.py``. The grid is laid
over the physical page: columns are lettered left to right (A, B, … Z, AA …)
and rows numbered top to bottom, so a range such as ``page2!A4:J10`` names the
same piece of paper whatever resolution a student's paper was scanned at.

CAM2 uses one grid of ~5 mm cells. Teachers drag boxes and never need the
cell names, so a fine grid costs nothing and lets boxes follow the paper
closely. Sessions made before this keep CAM's "compact" (~1.4 cm, stored as
"normal") or "fine" (~1 cm) grid, because their saved ranges name those cells.

Geometry: CAM derived an effective DPI per axis from the paper's size in mm
and then a cell size in pixels. The millimetres cancel out, so one cell is
simply ``image_width / cols`` by ``image_height / rows`` pixels — which is what
:func:`range_to_bbox` computes. A slightly stretched scan still lands on the
right part of the page because each axis is scaled separately.
"""

from __future__ import annotations

import io
import math
import os
import re
import shutil
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Callable, Iterable, List, NamedTuple, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageOps

from .errors import UserError
from .model import NAME_BOX_ID

# --- Paper and grid ------------------------------------------------------------

SLIDE_16_9 = "Slide 16:9"
SLIDE_16_10 = "Slide 16:10"
SLIDE_4_3 = "Slide 4:3"

# Portrait (width, height) in millimetres. B5 here is ISO B5; the Japanese JIS
# B5 (182×257) is accepted by detection as "B5" too. Because geometry is
# proportional, the exact millimetres never affect where a crop lands.
PAPER_SIZES_MM = {
    "A4": (210.0, 297.0),
    "B5": (176.0, 250.0),
    "A3": (297.0, 420.0),
    SLIDE_16_9: (142.875, 254.0),   # 10 in wide, as Google Slides makes them
    SLIDE_4_3: (190.5, 254.0),
    SLIDE_16_10: (158.75, 254.0),
}
_DETECT_SIZES_MM = (
    ("A4", 210.0, 297.0),
    ("B5", 176.0, 250.0),   # ISO B5
    ("B5", 182.0, 257.0),   # JIS B5, the usual Japanese school size
    ("A3", 297.0, 420.0),
)
DETECT_TOLERANCE_MM = 4.0

# Decks come in many sizes but few shapes: PowerPoint's 16:9 is 13.333 x 7.5 in and
# Google's is 10 x 5.625 in. Close enough to tell 4:3 from US Letter (1.29).
_SLIDE_SHAPES = ((SLIDE_16_9, 16 / 9), (SLIDE_4_3, 4 / 3), (SLIDE_16_10, 16 / 10))
SLIDE_SHAPE_TOLERANCE = 0.01

# Portrait (cols, rows) per paper and density. "5mm" is the grid for new
# sessions; "normal" and "fine" (CAM's "compact" and "fine") are only read
# from older sessions.
GRIDS = {
    "A4": {"5mm": (42, 60), "normal": (15, 21), "fine": (21, 30)},
    "B5": {"5mm": (36, 51), "normal": (13, 18), "fine": (18, 25)},
    "A3": {"5mm": (60, 84), "normal": (21, 30), "fine": (30, 42)},
    SLIDE_16_9: {"5mm": (29, 51), "normal": (10, 18), "fine": (14, 25)},
    SLIDE_16_10: {"5mm": (32, 51), "normal": (11, 18), "fine": (16, 25)},
    SLIDE_4_3: {"5mm": (38, 51), "normal": (14, 18), "fine": (19, 25)},
}
PAPERS = tuple(GRIDS)
DENSITY = "5mm"
OLD_DENSITIES = ("normal", "fine")
DENSITIES = (DENSITY,) + OLD_DENSITIES

# Pages are rasterised at this DPI for cropping; crops of every student then
# come out the same pixel size.
RENDER_DPI = 200

# A whole slide of photographs is about 5 MB as a PNG and 0.6 MB as a JPEG, and a
# class's crops sit in a synced folder. Written pages stay PNG, for sharp handwriting.
SLIDE_CROP_QUALITY = 85

PDF_EXT = ".pdf"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


@dataclass(frozen=True)
class Layout:
    """Paper size, grid density and orientation of one exam."""

    paper: str = "A4"
    density: str = DENSITY
    landscape: bool = False

    def __post_init__(self):
        if self.paper not in GRIDS:
            raise UserError("unknown_paper", paper=self.paper)
        if self.density not in DENSITIES:
            raise UserError("unknown_density", density=self.density)

    @property
    def cols(self) -> int:
        c, r = GRIDS[self.paper][self.density]
        return r if self.landscape else c

    @property
    def rows(self) -> int:
        c, r = GRIDS[self.paper][self.density]
        return c if self.landscape else r

    @classmethod
    def from_config(cls, raw) -> "Layout":
        raw = raw or {}
        return cls(paper=str(raw.get("paper") or "A4"),
                   density=str(raw.get("density") or DENSITY),
                   landscape=bool(raw.get("landscape")))

    def to_config(self) -> dict:
        return {"paper": self.paper, "density": self.density,
                "landscape": self.landscape}


def detect_paper_mm(width_mm: float, height_mm: float, slides: bool = True
                    ) -> Optional[Tuple[str, bool]]:
    """Match a page size to (paper, landscape), or None if it is none of ours.

    Paper sizes are checked first, then the shape of a landscape slide. Pass
    ``slides=False`` for a page made from a picture: phone photos are 4:3 or 16:9
    too, and are papers, not slides.
    """
    short, long_ = sorted((float(width_mm), float(height_mm)))
    landscape = width_mm > height_mm
    for paper, w, h in _DETECT_SIZES_MM:
        if abs(short - w) <= DETECT_TOLERANCE_MM and abs(long_ - h) <= DETECT_TOLERANCE_MM:
            return paper, landscape
    if slides and landscape:
        for paper, shape in _SLIDE_SHAPES:
            if abs(long_ / short / shape - 1) <= SLIDE_SHAPE_TOLERANCE:
                return paper, True
    return None


# A PDF page with no text and one picture over nearly all of it is a photo saved
# as a PDF, as some phone apps and "Print to PDF" make, not an exported slide.
PHOTO_PAGE_COVER = 0.9


def is_photo_page(page) -> bool:
    """True for a PDF page that is only a photo (see PHOTO_PAGE_COVER)."""
    try:
        if page.get_text("text").strip():
            return False
        area = abs(page.rect)
        return area > 0 and any(abs(_fitz().Rect(info["bbox"]) & page.rect) >= PHOTO_PAGE_COVER * area
                                for info in page.get_image_info())
    except Exception:
        return False


def detect_pdf_page(page) -> Optional[Tuple[str, bool]]:
    """(paper, landscape) for one PDF page. A photo is a paper, never a slide."""
    rect = page.rect                    # points, rotation applied
    return detect_paper_mm(rect.width * 25.4 / 72, rect.height * 25.4 / 72,
                           slides=not is_photo_page(page))


def detect_paper(path: str) -> Optional[Tuple[str, bool]]:
    """Best guess of (paper, landscape) for a scan file, or None.

    PDFs report their page size directly. Images only know their size if the
    scanner recorded a DPI. The teacher always confirms the result.
    """
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == PDF_EXT:
            with _fitz().open(path) as doc:
                if doc.page_count < 1:
                    return None
                return detect_pdf_page(doc[0])
        if ext in IMAGE_EXTS:
            with Image.open(path) as im:
                im = ImageOps.exif_transpose(im)
                dpi = im.info.get("dpi")
                if not dpi or not dpi[0] or not dpi[1] or float(dpi[0]) < 50:
                    return None
                return detect_paper_mm(im.width / float(dpi[0]) * 25.4,
                                       im.height / float(dpi[1]) * 25.4, slides=False)
    except Exception:
        return None
    return None


# --- Ranges --------------------------------------------------------------------

class Box(NamedTuple):
    """One grid rectangle: 1-based page, 0-based inclusive columns/rows."""

    page: int
    c1: int
    r1: int
    c2: int
    r2: int


def col_name(index: int) -> str:
    """0-based column index -> letters (0 -> A, 25 -> Z, 26 -> AA)."""
    i = int(index)
    if i < 0:
        raise ValueError(f"Column index {index!r} must be >= 0.")
    name = ""
    while True:
        name = chr(ord("A") + i % 26) + name
        i = i // 26 - 1
        if i < 0:
            return name


def col_index(letters: str) -> int:
    """Column letters -> 0-based index (A -> 0, Z -> 25, AA -> 26)."""
    s = str(letters or "").strip().upper()
    if not s or not all("A" <= ch <= "Z" for ch in s):
        raise ValueError(f"Bad column letters {letters!r}.")
    idx = 0
    for ch in s:
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


# "page2!A4:J10", "A4:J10" (page 1) or a single cell "B7".
_RANGE_RE = re.compile(
    r"^\s*(?:page\s*(\d+)\s*!\s*)?"
    r"([A-Za-z]{1,2})\s*(\d{1,3})"
    r"(?:\s*:\s*([A-Za-z]{1,2})\s*(\d{1,3}))?\s*$"
)


def parse_range(raw: str, layout: Layout) -> Box:
    """Parse a range typed by the teacher (full-width characters accepted)."""
    text = unicodedata.normalize("NFKC", str(raw or ""))
    m = _RANGE_RE.match(text)
    if not m:
        raise UserError("bad_range", range=str(raw))
    page = int(m.group(1)) if m.group(1) else 1
    c1, r1 = col_index(m.group(2)), int(m.group(3)) - 1
    if m.group(4):
        c2, r2 = col_index(m.group(4)), int(m.group(5)) - 1
    else:
        c2, r2 = c1, r1
    last_col, last_row = col_name(layout.cols - 1), layout.rows
    if page < 1:
        raise UserError("bad_range", range=str(raw))
    if not (0 <= c1 < layout.cols and 0 <= c2 < layout.cols
            and 0 <= r1 < layout.rows and 0 <= r2 < layout.rows):
        raise UserError("range_off_grid", range=str(raw),
                        last=f"{last_col}{last_row}")
    return Box(page, min(c1, c2), min(r1, r2), max(c1, c2), max(r1, r2))


def format_range(box: Box) -> str:
    """Box -> 'page2!A4:J10' (always with the page, for clarity)."""
    return (f"page{box.page}!{col_name(box.c1)}{box.r1 + 1}:"
            f"{col_name(box.c2)}{box.r2 + 1}")


def snap_rect(page: int, x0: float, y0: float, x1: float, y1: float,
              layout: Layout) -> Box:
    """Snap a dragged rectangle (fractions 0–1 of the page) to whole cells.

    Every cell the rectangle touches is included, so the box never ends up
    smaller than what the teacher dragged.
    """
    def clamp(v):
        return min(max(float(v), 0.0), 1.0)

    x0, x1 = sorted((clamp(x0), clamp(x1)))
    y0, y1 = sorted((clamp(y0), clamp(y1)))
    eps = 1e-9
    c1 = min(int(x0 * layout.cols), layout.cols - 1)
    r1 = min(int(y0 * layout.rows), layout.rows - 1)
    c2 = min(max(int(x1 * layout.cols - eps), c1), layout.cols - 1)
    r2 = min(max(int(y1 * layout.rows - eps), r1), layout.rows - 1)
    return Box(int(page), c1, r1, c2, r2)


def range_to_bbox(img_w: int, img_h: int, box: Box, layout: Layout
                  ) -> Tuple[int, int, int, int]:
    """Pixel (left, top, right, bottom) of a grid box on one page image."""
    cell_w = img_w / layout.cols
    cell_h = img_h / layout.rows
    left = int(round(box.c1 * cell_w))
    top = int(round(box.r1 * cell_h))
    right = int(round((box.c2 + 1) * cell_w))
    bottom = int(round((box.r2 + 1) * cell_h))
    left = max(0, min(left, img_w - 1))
    top = max(0, min(top, img_h - 1))
    right = max(left + 1, min(right, img_w))
    bottom = max(top + 1, min(bottom, img_h))
    return left, top, right, bottom


# --- Reading scans ---------------------------------------------------------------

def _fitz():
    try:
        import pymupdf as fitz
    except ImportError as exc:      # only in a broken install
        raise RuntimeError("PyMuPDF is missing from this CAM2 package.") from exc
    return fitz


def is_scan_file(name: str) -> bool:
    # Skip hidden files, including the "._name.pdf" files macOS leaves on USB sticks.
    if name.startswith("."):
        return False
    ext = os.path.splitext(name)[1].lower()
    return ext == PDF_EXT or ext in IMAGE_EXTS


def list_scan_files(folder: str) -> List[str]:
    """Scan files directly inside ``folder``, sorted naturally (2 before 10)."""
    try:
        names = os.listdir(folder)
    except OSError as exc:
        raise UserError("folder_unreadable", folder=folder) from exc
    files = [n for n in names
             if is_scan_file(n) and os.path.isfile(os.path.join(folder, n))]
    files.sort(key=_natural_key)
    return [os.path.join(folder, n) for n in files]


def _natural_key(name: str):
    return [int(part) if part.isdigit() else part.casefold()
            for part in re.split(r"(\d+)", name)]


def page_count(path: str) -> int:
    if os.path.splitext(path)[1].lower() == PDF_EXT:
        with _fitz().open(path) as doc:
            return doc.page_count
    return 1


def page_count_warnings(counts: dict) -> List[dict]:
    """Students whose page count differs from the class majority.

    ``counts`` maps student id -> page count (None if unreadable). One student
    scanned with a page missing or extra would have every crop land on the
    wrong part of the paper without any error, so this is worth flagging.
    """
    known = [c for c in counts.values() if isinstance(c, int)]
    if len(known) < 2:
        return []
    freq = Counter(known)
    top = max(freq.values())
    majority = max(c for c, n in freq.items() if n == top)
    return [{"student": sid, "pages": c, "expected": majority}
            for sid, c in counts.items()
            if isinstance(c, int) and c != majority]


def load_page_image(path: str, page: int, dpi: int = RENDER_DPI) -> Image.Image:
    """One page of a scan as an RGB image (pages are 1-based)."""
    ext = os.path.splitext(path)[1].lower()
    if ext == PDF_EXT:
        with _fitz().open(path) as doc:
            if not 1 <= page <= doc.page_count:
                raise UserError("page_missing", file=os.path.basename(path),
                                page=page, pages=doc.page_count)
            pix = doc[page - 1].get_pixmap(dpi=dpi)
            return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    if page != 1:
        raise UserError("page_missing", file=os.path.basename(path), page=page, pages=1)
    with Image.open(path) as im:
        return ImageOps.exif_transpose(im).convert("RGB")


def page_image_sizes(path: str, pages: Iterable[int], dpi: int = RENDER_DPI) -> dict:
    """Pixel ``(width, height)`` per 1-based page at ``dpi``, without rasterising."""
    wanted = sorted({int(p) for p in pages})
    if not wanted:
        return {}
    ext = os.path.splitext(path)[1].lower()
    if ext == PDF_EXT:
        fitz = _fitz()
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        with fitz.open(path) as doc:
            out = {}
            for p in wanted:
                if not 1 <= p <= doc.page_count:
                    raise UserError("page_missing", file=os.path.basename(path),
                                    page=p, pages=doc.page_count)
                irect = (doc[p - 1].rect * mat).irect
                out[p] = (irect.width, irect.height)
            return out
    for p in wanted:
        if p != 1:
            raise UserError("page_missing", file=os.path.basename(path), page=p, pages=1)
    with Image.open(path) as im:
        orient = im.getexif().get(274, 1)
        size = (im.height, im.width) if orient in (5, 6, 7, 8) else (im.width, im.height)
    return {1: size}


def page_image_size(path: str, page: int, dpi: int = RENDER_DPI) -> Tuple[int, int]:
    """Pixel ``(width, height)`` of one scan page at ``dpi`` (pages are 1-based)."""
    return page_image_sizes(path, [page], dpi=dpi)[int(page)]


# --- Bringing scans into the session folder --------------------------------------

def check_split(total_pages: int, pages_per_student: int) -> Tuple[int, int]:
    """(number of students, leftover pages) for a combined PDF."""
    per = int(pages_per_student)
    if per < 1:
        raise UserError("pages_per_student_invalid")
    total = int(total_pages)
    return -(-total // per), total % per


def check_class_size(total_pages: int, pages_per_student: int, students) -> Optional[dict]:
    """Compare a combined PDF with the class size the teacher expects.

    Returns None when they agree or no class size was given; otherwise how many
    pages are missing (``diff`` < 0) or extra (``diff`` > 0). This catches what
    the leftover check cannot: two missing pages still divide evenly.
    """
    try:
        n = int(students or 0)
    except (TypeError, ValueError):
        return None
    if n < 1:
        return None
    expected = n * int(pages_per_student)
    if expected == int(total_pages):
        return None
    return {"students": n, "expected_pages": expected, "pages": int(total_pages),
            "diff": int(total_pages) - expected}


def split_combined_pdf(src: str, pages_per_student: int, dest_dir: str,
                       progress: Optional[Callable[[int, int], None]] = None) -> dict:
    """Split a photocopier PDF into one PDF per student.

    Files are named ``Student_001.pdf`` … in scan order. When the page count
    does not divide evenly, the last file is the short one and ``leftover``
    says how many pages it has, so the teacher can be warned.
    """
    fitz = _fitz()
    os.makedirs(dest_dir, exist_ok=True)
    out = []
    with fitz.open(src) as doc:
        total = doc.page_count
        if total < 1:
            raise UserError("pdf_empty", file=os.path.basename(src))
        n_students, leftover = check_split(total, pages_per_student)
        for i in range(n_students):
            first = i * pages_per_student
            last = min(first + pages_per_student, total) - 1
            name = f"Student_{i + 1:03d}.pdf"
            part = fitz.open()
            try:
                part.insert_pdf(doc, from_page=first, to_page=last)
                part.save(os.path.join(dest_dir, name), garbage=3, deflate=True)
            finally:
                part.close()
            out.append(os.path.join(dest_dir, name))
            if progress:
                progress(i + 1, n_students)
    return {"files": out, "total_pages": total, "leftover": leftover}


_UNSAFE_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL",
                   *(f"COM{i}" for i in range(1, 10)),
                   *(f"LPT{i}" for i in range(1, 10))}


def safe_filename(name: str, fallback: str = "Unnamed") -> str:
    """A file name that is valid on Windows and macOS. Japanese is kept."""
    text = unicodedata.normalize("NFC", str(name or ""))
    text = _UNSAFE_CHARS.sub("_", text).strip().rstrip(". ")
    if not text:
        text = fallback
    if text.split(".")[0].upper() in _RESERVED_NAMES:
        text = "_" + text
    return text[:120]


def unique_name(name: str, taken: set) -> str:
    """``name`` or ``name (2)``, ``name (3)`` … not already in ``taken``
    (compared case-insensitively, as Windows and macOS do). Adds the result."""
    stem, ext = os.path.splitext(name)
    candidate, n = name, 1
    while candidate.casefold() in taken:
        n += 1
        candidate = f"{stem} ({n}){ext}"
    taken.add(candidate.casefold())
    return candidate


def copy_scans(sources: Sequence[str], dest_dir: str,
               progress: Optional[Callable[[int, int], None]] = None) -> List[dict]:
    """Copy scan files into the session's ``scans`` folder.

    Returns one student entry per file, in order:
    ``{"id": "s001", "file": "<name in dest_dir>", "source": "<original name>"}``.
    """
    os.makedirs(dest_dir, exist_ok=True)
    taken = {n.casefold() for n in os.listdir(dest_dir)}
    students = []
    for i, src in enumerate(sources, 1):
        source_name = os.path.basename(src)
        stem, ext = os.path.splitext(source_name)
        name = unique_name(safe_filename(stem) + ext.lower(), taken)
        dest = os.path.join(dest_dir, name)
        if os.path.abspath(src) != os.path.abspath(dest):
            shutil.copy2(src, dest)
        students.append({"id": f"s{i:03d}", "file": name, "source": source_name})
        if progress:
            progress(i, len(sources))
    return students


# --- Cropping ---------------------------------------------------------------------

DIVIDER_PX = 6
DIVIDER_COLOR = (190, 190, 190)


def stitch_vertical(images: Sequence[Image.Image]) -> Image.Image:
    """Stack crops top to bottom on white, with a grey line between them."""
    if not images:
        raise ValueError("Nothing to stitch.")
    if len(images) == 1:
        return images[0]
    width = max(im.width for im in images)
    height = sum(im.height for im in images) + DIVIDER_PX * (len(images) - 1)
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    y = 0
    for i, im in enumerate(images):
        canvas.paste(im, (0, y))
        y += im.height
        if i < len(images) - 1:
            draw.rectangle([0, y, width, y + DIVIDER_PX - 1], fill=DIVIDER_COLOR)
            y += DIVIDER_PX
    return canvas


def crop_boxes(path: str, boxes: Iterable[Box], layout: Layout,
               page_cache: Optional[dict] = None) -> Image.Image:
    """Crop one or more boxes from one student's scan into a single image."""
    cache = page_cache if page_cache is not None else {}
    parts = []
    for box in boxes:
        if box.page not in cache:
            cache[box.page] = load_page_image(path, box.page)
        img = cache[box.page]
        parts.append(img.crop(range_to_bbox(img.width, img.height, box, layout)))
    out = stitch_vertical(parts)
    if len(parts) > 1:
        for im in parts:
            im.close()
    return out


def layout_5mm(layout: Optional[Layout] = None, page_w: int = 0, page_h: int = 0) -> Layout:
    """The 5 mm grid for highlights, even when an older exam uses a coarser box grid."""
    if layout is not None:
        return Layout(layout.paper, DENSITY, layout.landscape)
    landscape = page_w > page_h
    return Layout("A4", DENSITY, landscape)


def _highlight_grid(layout: Optional[Layout], page_w: int, page_h: int) -> Tuple[int, int]:
    if layout is not None:
        g5 = Layout(layout.paper, DENSITY, layout.landscape)
        return g5.cols, g5.rows
    # Nominal ~5 mm cells from an image/page shape when no paper size is set (Phase G).
    if page_w <= 0 or page_h <= 0:
        return GRIDS["A4"][DENSITY]
    long_cells = 60
    if page_h >= page_w:
        return max(1, round(long_cells * page_w / page_h)), long_cells
    return long_cells, max(1, round(long_cells * page_h / page_w))


def _build_geometry(specs: Sequence[Tuple[int, int, int, Tuple[int, int, int, int], float]],
                    divider_px: int = DIVIDER_PX) -> dict:
    """Composite geometry from ``[(page, page_w, page_h, bbox, scale)]``."""
    if not specs:
        return {"width": 0, "height": 0, "divider": divider_px, "parts": []}
    parts = []
    y = 0
    max_w = 0
    for i, (page, pw, ph, bbox, scale) in enumerate(specs):
        left, top, right, bottom = bbox
        part_w = max(1, int(round((right - left) * scale))) if scale != 1.0 else (right - left)
        part_h = max(1, int(round((bottom - top) * scale))) if scale != 1.0 else (bottom - top)
        parts.append({
            "index": i,
            "page": int(page),
            "page_width": int(pw),
            "page_height": int(ph),
            "bbox": [int(left), int(top), int(right), int(bottom)],
            "rect": {
                "x": left / pw,
                "y": top / ph,
                "w": (right - left) / pw,
                "h": (bottom - top) / ph,
            },
            "scale": float(scale),
            "crop_x": 0,
            "crop_y": y,
            "crop_w": part_w,
            "crop_h": part_h,
        })
        max_w = max(max_w, part_w)
        y += part_h
        if i < len(specs) - 1:
            y += divider_px
    return {"width": max_w, "height": y, "divider": divider_px, "parts": parts}


def answer_geometry(path: str, boxes: Sequence[Box], layout: Layout,
                    page_sizes: Optional[dict] = None, dpi: int = RENDER_DPI) -> dict:
    """Geometry of a cropped answer matching :func:`crop_boxes` and :func:`stitch_vertical`."""
    box_list = list(boxes)
    if not box_list:
        return _build_geometry([])
    sizes = dict(page_sizes or {})
    missing = [b.page for b in box_list if b.page not in sizes]
    if missing:
        sizes.update(page_image_sizes(path, missing, dpi=dpi))
    specs = []
    for box in box_list:
        pw, ph = sizes[box.page]
        specs.append((box.page, pw, ph, range_to_bbox(pw, ph, box, layout), 1.0))
    return _build_geometry(specs, divider_px=DIVIDER_PX)


def whole_page_geometry(path: str, page: int, target_width: Optional[int] = None,
                        dpi: int = RENDER_DPI) -> dict:
    """Geometry for a whole scanned page (one part covering ``[0, 1] x [0, 1]``)."""
    pw, ph = page_image_size(path, page, dpi=dpi)
    scale = (target_width / pw) if target_width else 1.0
    geom = _build_geometry([(int(page), pw, ph, (0, 0, pw, ph), scale)], divider_px=0)
    # PDF dimensions are physical points; converted images use their DPI or a
    # nominal physical size from pages._image_pdf.
    geom["parts"][0]["grid"] = {"cols": max(1, round(pw / dpi * 25.4 / 5)),
                                 "rows": max(1, round(ph / dpi * 25.4 / 5))}
    geom["whole_page"] = True
    return geom


def crop_point_to_page(geometry: dict, cx: float, cy: float) -> Optional[dict]:
    """Map composite-image pixel ``(cx, cy)`` to ``{page, x, y, part_index}``.

    Returns None when ``(cx, cy)`` lands on white padding or a divider gap.
    """
    for part in geometry.get("parts") or []:
        x0, y0 = part["crop_x"], part["crop_y"]
        w, h = part["crop_w"], part["crop_h"]
        if x0 <= cx <= x0 + w and y0 <= cy <= y0 + h:
            rx = (cx - x0) / w if w else 0.0
            ry = (cy - y0) / h if h else 0.0
            r = part["rect"]
            return {
                "page": part["page"],
                "x": min(max(r["x"] + rx * r["w"], 0.0), 1.0),
                "y": min(max(r["y"] + ry * r["h"], 0.0), 1.0),
                "part_index": part["index"],
            }
    return None


def snap_highlight_from_crop(geometry: dict, cx0: float, cy0: float, cx1: float, cy1: float,
                             layout: Optional[Layout] = None) -> Optional[dict]:
    """Snap a dragged composite rectangle to the 5 mm grid in page fractions.

    Uses the part where the drag started (or the first intersecting part) and
    clips the drag rectangle to that part so highlights never span padding or
    dividers.
    """
    parts = geometry.get("parts") or []
    start = crop_point_to_page(geometry, cx0, cy0)
    part = parts[start["part_index"]] if start is not None else None
    left, right = sorted((float(cx0), float(cx1)))
    top, bottom = sorted((float(cy0), float(cy1)))
    if part is None:
        for candidate in parts:
            x0, y0 = candidate["crop_x"], candidate["crop_y"]
            x1, y1 = x0 + candidate["crop_w"], y0 + candidate["crop_h"]
            if min(right, x1) > max(left, x0) and min(bottom, y1) > max(top, y0):
                part = candidate
                break
    if part is None:
        return None
    x0, y0 = part["crop_x"], part["crop_y"]
    w, h = part["crop_w"], part["crop_h"]
    ix0, iy0 = max(left, x0), max(top, y0)
    ix1, iy1 = min(right, x0 + w), min(bottom, y0 + h)
    if ix1 <= ix0 or iy1 <= iy0 or w <= 0 or h <= 0:
        return None
    r = part["rect"]
    px0 = r["x"] + ((ix0 - x0) / w) * r["w"]
    py0 = r["y"] + ((iy0 - y0) / h) * r["h"]
    px1 = r["x"] + ((ix1 - x0) / w) * r["w"]
    py1 = r["y"] + ((iy1 - y0) / h) * r["h"]
    if part.get("grid"):
        cols, rows = part["grid"]["cols"], part["grid"]["rows"]
    else:
        cols, rows = _highlight_grid(layout, part["page_width"], part["page_height"])

    def clamp(v):
        return min(max(float(v), 0.0), 1.0)

    sx0, sx1 = sorted((clamp(px0), clamp(px1)))
    sy0, sy1 = sorted((clamp(py0), clamp(py1)))
    eps = 1e-9
    c1 = min(int(sx0 * cols), cols - 1)
    r1 = min(int(sy0 * rows), rows - 1)
    c2 = min(max(int(sx1 * cols - eps), c1), cols - 1)
    r2 = min(max(int(sy1 * rows - eps), r1), rows - 1)
    return {
        "page": part["page"],
        "x": c1 / cols,
        "y": r1 / rows,
        "w": (c2 - c1 + 1) / cols,
        "h": (r2 - r1 + 1) / rows,
    }


def _part_crop_xy(part: dict, px: float, py: float, geom_w: float, geom_h: float) -> Tuple[float, float, float, float]:
    r = part["rect"]
    rx = ((px - r["x"]) / r["w"]) if r["w"] else 0.0
    ry = ((py - r["y"]) / r["h"]) if r["h"] else 0.0
    cx = part["crop_x"] + min(max(rx, 0.0), 1.0) * part["crop_w"]
    cy = part["crop_y"] + min(max(ry, 0.0), 1.0) * part["crop_h"]
    nx = (cx / geom_w) if geom_w else 0.0
    ny = (cy / geom_h) if geom_h else 0.0
    return cx, cy, nx, ny


def project_annotations(geometry: dict, annotations: Sequence[dict]) -> List[dict]:
    """Project stored page-fraction notes onto ``geometry``.

    Each entry keeps its stored ``page, x, y``; if a box adjustment moved it
    outside all parts, ``out_of_crop`` is True and ``cx, cy`` points to the
    nearest spot in a box on the same page, or the start of the answer.
    """
    parts = geometry.get("parts") or []
    gw, gh = geometry.get("width") or 0, geometry.get("height") or 0
    out = []
    for idx, ann in enumerate(annotations or [], 1):
        page = int(ann.get("page") or 1)
        px = float(ann.get("x") or 0.0)
        py = float(ann.get("y") or 0.0)
        if not parts:
            out.append({**ann, "num": idx, "out_of_crop": True, "part_index": None,
                        "cx": 0.0, "cy": 0.0, "nx": 0.0, "ny": 0.0,
                        "confirmed_page": page, "confirmed_x": px, "confirmed_y": py})
            continue
        inside = []
        for part in parts:
            if part["page"] != page:
                continue
            r = part["rect"]
            if r["x"] <= px <= r["x"] + r["w"] and r["y"] <= py <= r["y"] + r["h"]:
                margin = min(
                    (px - r["x"]) * part["page_width"],
                    (r["x"] + r["w"] - px) * part["page_width"],
                    (py - r["y"]) * part["page_height"],
                    (r["y"] + r["h"] - py) * part["page_height"],
                )
                inside.append((margin, -part["index"], part))
        if inside:
            inside.sort(reverse=True)
            part = inside[0][2]
            cx, cy, nx, ny = _part_crop_xy(part, px, py, gw, gh)
            out.append({**ann, "num": idx, "out_of_crop": False, "part_index": part["index"],
                        "cx": cx, "cy": cy, "nx": nx, "ny": ny,
                        "confirmed_page": page, "confirmed_x": px, "confirmed_y": py})
            continue
        same_page = [p for p in parts if p["page"] == page]
        if same_page:
            best = None
            for part in same_page:
                r = part["rect"]
                qx = min(max(px, r["x"]), r["x"] + r["w"])
                qy = min(max(py, r["y"]), r["y"] + r["h"])
                dist = math.hypot((px - qx) * part["page_width"], (py - qy) * part["page_height"])
                cand = (dist, part["index"], part, qx, qy)
                if best is None or cand < best:
                    best = cand
            _, _, part, qx, qy = best
        else:
            part = parts[0]
            qx, qy = part["rect"]["x"], part["rect"]["y"]
        cx, cy, nx, ny = _part_crop_xy(part, qx, qy, gw, gh)
        out.append({**ann, "num": idx, "out_of_crop": True, "part_index": part["index"],
                    "cx": cx, "cy": cy, "nx": nx, "ny": ny,
                    "confirmed_page": part["page"], "confirmed_x": qx, "confirmed_y": qy})
    return out


def project_highlights(geometry: dict, highlights: Sequence[dict]) -> List[dict]:
    """Clip stored page-fraction highlights to each overlapping part."""
    parts = geometry.get("parts") or []
    gw, gh = geometry.get("width") or 0, geometry.get("height") or 0
    out = []
    for hl in highlights or []:
        page = int(hl.get("page") or 1)
        hx0 = float(hl.get("x") or 0.0)
        hy0 = float(hl.get("y") or 0.0)
        hx1 = hx0 + float(hl.get("w") or 0.0)
        hy1 = hy0 + float(hl.get("h") or 0.0)
        pieces = []
        for part in parts:
            if part["page"] != page:
                continue
            r = part["rect"]
            ix0 = max(hx0, r["x"])
            iy0 = max(hy0, r["y"])
            ix1 = min(hx1, r["x"] + r["w"])
            iy1 = min(hy1, r["y"] + r["h"])
            if ix1 <= ix0 or iy1 <= iy0:
                continue
            cx0, cy0, nx0, ny0 = _part_crop_xy(part, ix0, iy0, gw, gh)
            cx1, cy1, nx1, ny1 = _part_crop_xy(part, ix1, iy1, gw, gh)
            pieces.append({
                "part_index": part["index"],
                "cx": cx0, "cy": cy0, "cw": cx1 - cx0, "ch": cy1 - cy0,
                "nx": nx0, "ny": ny0, "nw": nx1 - nx0, "nh": ny1 - ny0,
            })
        out.append({**hl, "pieces": pieces, "excluded": not pieces})
    return out


def parse_boxes(ranges: Iterable[str], layout: Layout) -> List[Box]:
    boxes = [parse_range(r, layout) for r in ranges]
    if not boxes:
        raise UserError("no_boxes")
    return boxes


def crop_file(region_id: str, student_id: str, layout: Layout) -> str:
    """Where a crop goes inside ``crops/``. The paper size decides the format,
    except that CAM reads name crops as PNG files, so those stay PNG."""
    jpeg = layout.paper in (SLIDE_16_9, SLIDE_4_3, SLIDE_16_10) and region_id != NAME_BOX_ID
    return f"{region_id}/{student_id}.{'jpg' if jpeg else 'png'}"


def student_crop_key(student: dict) -> str:
    """Use the scan version for joined papers so older saves keep their crops."""
    if "page_files" in student:
        return os.path.splitext(student["file"])[0]
    return student["id"]


def slice_all(scans: Sequence[Tuple[str, str]], regions: Sequence[Tuple[str, Sequence[Box]]],
              layout: Layout, crops_dir: str,
              progress: Optional[Callable[[int, int], None]] = None, *,
              crop_keys: Optional[dict] = None) -> dict:
    """Crop every region from every student's scan.

    ``scans`` is ``[(student_id, path)]`` and ``regions`` is
    ``[(region_id, [Box, ...])]`` (questions plus the name box). Crops land at
    ``crops_dir/<region_id>/<student_id>.png`` unless ``crop_keys`` supplies
    a scan revision name (see :func:`crop_file`). A failure
    on one student never stops the rest of the class; it is reported in ``errors``.
    """
    summary = {"students": len(scans), "regions": len(regions), "crops": 0, "errors": []}
    for region_id, _ in regions:
        os.makedirs(os.path.join(crops_dir, region_id), exist_ok=True)
    for done, (student_id, path) in enumerate(scans, 1):
        pages: dict = {}
        for region_id, boxes in regions:
            try:
                image = crop_boxes(path, boxes, layout, pages)
                name = crop_file(region_id, (crop_keys or {}).get(student_id, student_id), layout)
                if name.endswith(".jpg"):
                    image.save(os.path.join(crops_dir, name), "JPEG", quality=SLIDE_CROP_QUALITY)
                else:
                    image.save(os.path.join(crops_dir, name), "PNG")
                summary["crops"] += 1
            except Exception as exc:
                summary["errors"].append({"student": student_id, "region": region_id,
                                          "error": str(exc)})
        pages.clear()
        if progress:
            progress(done, len(scans))
    return summary


# --- Previews for the browser -----------------------------------------------------

def _to_bytes(img: Image.Image, fmt: str = "PNG", quality: int = 85) -> bytes:
    with io.BytesIO() as buf:
        if fmt == "JPEG":
            rgb = img.convert("RGB") if img.mode != "RGB" else img
            try:
                rgb.save(buf, "JPEG", quality=quality, optimize=True)
            finally:
                if rgb is not img:
                    rgb.close()
        else:
            img.save(buf, fmt)
        return buf.getvalue()


def _fit_width(img: Image.Image, max_width: int) -> Image.Image:
    if img.width <= max_width:
        return img
    ratio = max_width / img.width
    return img.resize((max_width, max(1, int(img.height * ratio))), Image.LANCZOS)


def make_thumbnail(path: str, dest: str, width: int = 240) -> str:
    """Small JPEG of page 1, used for the Step 1 scan check."""
    raw = load_page_image(path, 1, dpi=60)
    img = _fit_width(raw, width)
    try:
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(_to_bytes(img, "JPEG", 80))
    finally:
        if img is not raw:
            img.close()
        raw.close()
    return dest


def crop_thumbnail(path: str, max_width: int = 520, quality: int = 80) -> bytes:
    """Bounded JPEG thumbnail of a cropped answer, preserving aspect ratio."""
    with Image.open(path) as im:
        resized = _fit_width(im, max_width)
        try:
            return _to_bytes(resized, "JPEG", quality)
        finally:
            if resized is not im:
                resized.close()


def page_preview(path: str, page: int, layout: Optional[Layout] = None,
                 outline: Sequence[Box] = (), max_width: int = 1400) -> bytes:
    """A page as JPEG bytes, optionally with question boxes outlined in red.

    Used by Step 2's drawing canvas, Step 4's "See whole page" viewer, and the
    class grid's Whole papers cards.
    """
    dpi = 100 if max_width <= 700 else RENDER_DPI
    img = load_page_image(path, page, dpi=dpi)
    resized = None
    try:
        if outline and layout is not None:
            draw = ImageDraw.Draw(img)
            stroke = max(3, img.width // 300)
            for box in outline:
                if box.page == page:
                    draw.rectangle(range_to_bbox(img.width, img.height, box, layout),
                                   outline=(220, 30, 30), width=stroke)
        resized = _fit_width(img, max_width)
        return _to_bytes(resized, "JPEG", 85 if max_width > 700 else 80)
    finally:
        if resized is not None and resized is not img:
            resized.close()
        img.close()


def crop_preview(path: str, boxes: Sequence[Box], layout: Layout,
                 max_width: int = 700) -> bytes:
    """One student's crop for the "Check on other papers" strip."""
    raw = crop_boxes(path, boxes, layout)
    resized = _fit_width(raw, max_width)
    try:
        return _to_bytes(resized, "JPEG", 85)
    finally:
        if resized is not raw:
            resized.close()
        raw.close()
