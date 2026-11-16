"""Quick comments: a per-exam list of notes the teacher places while grading.

Dragging a quick comment onto an answer stamps a numbered note at that spot
with its own copy of the text; changing the list later never alters notes
already placed. Strength and Area to develop are optional types.

``cam2_session.json`` holds the list as ``"keywords": [{"label", "type"}]``
with type ``"strength"``, ``"growth"`` or None. A session without the key
starts with four defaults in the app's language. Existing longer lists and
labels from earlier versions are kept and can be kept or shortened, not grown.
"""

from __future__ import annotations

from typing import List, Optional

from . import i18n
from .errors import UserError

STRENGTH = "strength"
GROWTH = "growth"
DEFAULT_COUNT = 4
DEFAULT_TYPES = (STRENGTH, GROWTH, GROWTH, GROWTH)
MAX_KEYWORDS = 8
MAX_LABEL = 120


def clean_type(raw) -> Optional[str]:
    if raw == STRENGTH:
        return STRENGTH
    if raw == GROWTH:
        return GROWTH
    return None


def normalize(raw) -> List[dict]:
    """A clean [{label, type}] list: no blanks, no case-insensitive repeats."""
    out, seen = [], set()
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        label = " ".join(str(item.get("label") or "").split())
        if not label or label.casefold() in seen:
            continue
        seen.add(label.casefold())
        out.append({"label": label, "type": clean_type(item.get("type"))})
    return out


def keyword_list(config: dict, language: str) -> List[dict]:
    if "keywords" in config:
        return normalize(config["keywords"])
    return [{"label": i18n.t(f"keywords.default_{n}", language), "type": kind}
            for n, kind in enumerate(DEFAULT_TYPES, 1)]


def set_list(config: dict, raw) -> dict:
    old = normalize(config["keywords"]) if "keywords" in config else []
    old_lengths = {item["label"].casefold(): len(item["label"]) for item in old}
    cleaned = normalize(raw)
    for item in cleaned:
        n = len(item["label"])
        if n > MAX_LABEL and n > old_lengths.get(item["label"].casefold(), 0):
            raise UserError("note_too_long", limit=MAX_LABEL)
    limit = max(MAX_KEYWORDS, len(old))
    if len(cleaned) > limit:
        raise UserError("too_many_keywords", limit=MAX_KEYWORDS)
    config["keywords"] = cleaned
    return config
