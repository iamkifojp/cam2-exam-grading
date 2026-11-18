"""Local submissions: conservative identity matching and file/page ownership.

Only unique roster evidence joins files. The matching rules mirror CAM's
submission_identity.py; there is no Drive metadata or remote I/O here.
"""

import os
import re
import unicodedata

from . import model, pages, slicer, storage
from .errors import UserError

EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}


def natural_key(value):
    return [int(part) if part.isdigit() else part.casefold()
            for part in re.split(r"(\d+)", str(value))]


def normalize(value):
    value = unicodedata.normalize("NFKD", str(value or "")).casefold()
    value = "".join(c for c in value if not unicodedata.combining(c))
    return " ".join(re.findall(r"[^\W_]+", value, flags=re.UNICODE))


def contains(text, value):
    value = normalize(value)
    return bool(value) and f" {value} " in f" {normalize(text)} "


def match_file(name, folder, roster):
    """Return a roster ID only for unique full-name/ID evidence.

    An explicit ID disambiguates duplicate names, but never overrides a
    conflicting student's name in the filename or containing folder.
    """
    ids, names = set(), set()
    by_id = {r["id"]: r for r in roster}
    for r in roster:
        key = r.get("external_id") or ""
        full = normalize(r.get("name"))
        if normalize(key) != full or len(full.split()) >= 2:
            if any(contains(text, key) for text in (name, folder)):
                ids.add(r["id"])
        if len(full.split()) >= 2 and any(contains(text, full) for text in (name, folder)):
            names.add(r["id"])
    candidates = ids | names
    if len(ids) == 1:
        rid = next(iter(ids))
        if not names or (rid in names and all(
                normalize(by_id[k]["name"]) == normalize(by_id[rid]["name"]) for k in names)):
            candidates = {rid}
    return next(iter(candidates)) if len(candidates) == 1 else None


def inspect_folder(folder):
    if not folder or not os.path.isdir(folder):
        raise UserError("folder_unreadable", folder=folder or "")
    folder = os.path.abspath(folder)
    accepted, rejected = [], []
    for root, dirs, files in os.walk(folder):
        dirs.sort(key=natural_key)
        for name in sorted(files, key=natural_key):
            path = os.path.join(root, name)
            rel = os.path.relpath(path, folder).replace(os.sep, "/")
            if os.path.splitext(name)[1].lower() in EXTENSIONS:
                accepted.append(path)
            else:
                rejected.append({"name": rel, "reason": "submission_unsupported"})
    accepted.sort(key=lambda p: (natural_key(os.path.basename(p)), natural_key(os.path.relpath(p, folder)), p))
    return {"path": folder, "files": accepted, "count": len(accepted), "not_opened": rejected}


def plan(folder, roster):
    info = inspect_folder(folder)
    papers = []
    matched = {}
    for path in info["files"]:
        rel = os.path.relpath(path, info["path"]).replace(os.sep, "/")
        parent = os.path.dirname(rel)
        rid = match_file(os.path.basename(path), parent, roster)
        if rid is not None and rid in matched:
            paper = matched[rid]
        else:
            paper = {"roster_id": rid, "paths": [], "names": []}
            papers.append(paper)
            if rid is not None:
                matched[rid] = paper
        paper["paths"].append(path)
        paper["names"].append(rel)
    return papers, info["not_opened"]


def file_refs(paths, names):
    refs, files, owners = [], [], []
    for path, name in zip(paths, names):
        fid = "f" + model.new_session_id()
        part = pages.stream_refs([path])
        refs.extend(part)
        owners.extend([fid] * len(part))
        files.append({"id": fid, "name": name})
    return refs, files, owners


def write_revision(session, student, refs, nominal_photos=False):
    """Keep the previous scan usable by the saved config until this edit saves."""
    name = f"{student['id']}_{model.new_session_id()[:12]}.pdf"
    dest = session.path(f"{storage.SCANS_DIR}/{name}")
    tmp = dest + ".new"
    with pages.Sources(pages.PHOTO_MAX_PX, nominal_photos=nominal_photos) as sources:
        doc = pages.build_pages(sources, refs)
        try:
            pages.save(doc, tmp)
        finally:
            doc.close()
    os.replace(tmp, dest)
    student["file"] = name
