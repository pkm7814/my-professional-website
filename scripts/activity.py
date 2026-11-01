"""Build the "What's new" feed for the Home page from the website's own change history.

Each saved change (from the admin editor or from Claude) is a git commit. For the
most recent commits we compare the data before and after and describe what
changed, e.g. "5 photos added to Osaka" with a link to that album. Owner-written
announcements from data/announcements.yaml are merged in.

Never fails the build: if git history is unavailable, the feed is simply empty.
"""
from __future__ import annotations

import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

IST = timezone(timedelta(hours=5, minutes=30))
WATCHED = ["data/gallery.yaml", "data/publications_manual.yaml", "content"]
PAGE_NAMES = {"home": "Home", "about": "About", "research": "Research", "publications": "Publications",
              "conferences": "Conferences", "contact": "Contact", "gallery": "Gallery"}


def _slug(v: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(v).lower()).strip("-")


def _git(root: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=30)
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


def _yaml_at(root: Path, rev: str, path: str):
    out = _git(root, "show", f"{rev}:{path}")
    if out is None:
        return None
    try:
        return yaml.safe_load(out)
    except Exception:
        return None


def _albums(data) -> dict:
    """{album_id: {"name", "where", "photos": set}} using the same ids as the Gallery pages."""
    res = {}
    if not isinstance(data, dict):
        return res
    for alb in data.get("academic") or []:
        if isinstance(alb, dict) and alb.get("name") and not alb.get("hidden"):
            res[f"academic-{_slug(alb['name'])}"] = {"name": alb["name"], "where": data.get("academic_heading") or "Academic Journey",
                                                     "photos": _photos(alb)}
    for key in ("international", "india"):
        for g in data.get(key) or []:
            if not isinstance(g, dict) or not g.get("name") or g.get("hidden"):
                continue
            for pl in g.get("places") or []:
                if isinstance(pl, dict) and pl.get("name") and not pl.get("hidden"):
                    res[f"{key}-{_slug(g['name'])}-{_slug(pl['name'])}"] = {"name": pl["name"], "where": g["name"],
                                                                           "photos": _photos(pl)}
    return res


def _photos(pl) -> set:
    out = set()
    for ph in pl.get("photos") or []:
        ref = ph.get("image") if isinstance(ph, dict) else ph
        if ref:
            out.add(str(ref).split("/")[-1])
    return out


def _gallery_changes(old, new) -> list[dict]:
    if old is None or new is None:
        return []
    a, b = _albums(old), _albums(new)
    old_names = {v["name"] for v in a.values()}
    old_photos = set().union(*[v["photos"] for v in a.values()]) if a else set()
    items, added_total, touched = [], 0, []
    for aid, alb in b.items():
        new_ph = alb["photos"] - old_photos
        if alb["name"] not in old_names:
            text = f"New album: {alb['name']} ({alb['where']})"
            if new_ph:
                text += f" — {len(new_ph)} photo{'s' if len(new_ph) != 1 else ''}"
            items.append({"text": text, "link": f"/gallery/{aid}/", "kind": "gallery", "album": alb["name"]})
        elif new_ph:
            touched.append((aid, alb, len(new_ph)))
            added_total += len(new_ph)
    if len(touched) > 3:
        items.append({"text": f"{added_total} new photos added to the Gallery", "link": "/gallery/", "kind": "gallery"})
    else:
        for aid, alb, n in touched:
            items.append({"text": f"{n} new photo{'s' if n != 1 else ''} in {alb['name']} ({alb['where']})",
                          "link": f"/gallery/{aid}/", "kind": "gallery", "album": alb["name"]})
    return items


def _pub_changes(old, new) -> list[dict]:
    if old is None or new is None:
        return []
    def titles(d):
        return {_slug(p.get("title", "")): p for p in (d or []) if isinstance(p, dict) and p.get("title") and not p.get("hidden")}
    o, n = titles(old), titles(new)
    return [{"text": f"New publication: {p['title']}", "link": "/publications/", "kind": "publication"}
            for k, p in n.items() if k not in o]


def _yaml_from_disk(root: Path):
    try:
        return yaml.safe_load((root / "data" / "gallery.yaml").read_text(encoding="utf-8"))
    except Exception:
        return None


def build_activity(root: Path, limit: int = 8, max_commits: int = 60) -> list[dict]:
    items: list[dict] = []
    log = _git(root, "log", f"-{max_commits}", "--format=%H|%cI|%P", "--", *WATCHED)
    if log:
        for line in log.strip().splitlines():
            sha, when, parents = (line.split("|") + ["", ""])[:3]
            parent = parents.split()[0] if parents.strip() else None
            try:
                dt = datetime.fromisoformat(when).astimezone(IST)
            except Exception:
                continue
            files = (_git(root, "show", "--name-only", "--format=", sha) or "").split()
            found = []
            if parent and "data/gallery.yaml" in files:
                found += _gallery_changes(_yaml_at(root, parent, "data/gallery.yaml"), _yaml_at(root, sha, "data/gallery.yaml"))
            if parent and "data/publications_manual.yaml" in files:
                found += _pub_changes(_yaml_at(root, parent, "data/publications_manual.yaml"),
                                      _yaml_at(root, sha, "data/publications_manual.yaml"))
            for it in found:
                it["dt"] = dt
            items += found

    # owner-written announcements
    ann = []
    try:
        ann = yaml.safe_load((root / "data" / "announcements.yaml").read_text(encoding="utf-8")) or []
    except Exception:
        pass
    for a in ann:
        if not isinstance(a, dict) or not a.get("text") or a.get("hidden"):
            continue
        try:
            dt = datetime.fromisoformat(str(a.get("date"))).replace(tzinfo=IST)
        except Exception:
            dt = datetime.now(IST)
        items.append({"text": str(a["text"]), "link": str(a.get("link") or ""), "kind": "news", "dt": dt})

    # point gallery entries at where each album is *now* (albums can be moved or renamed later)
    current = _albums(_yaml_from_disk(root))
    by_name = {v["name"]: (aid, v) for aid, v in current.items()}
    fixed = []
    for it in items:
        m = re.match(r"/gallery/([\w-]+)/$", it.get("link", ""))
        if it["kind"] == "gallery" and m:
            aid = m.group(1)
            name = it.pop("album", None)
            if aid not in current:
                hit = by_name.get(name or "")
                if not hit:
                    continue  # album no longer exists
                aid = hit[0]
            alb = current[aid]
            it["link"] = f"/gallery/{aid}/"
            it["text"] = re.sub(r"\([^()]*\)", f"({alb['where']})", it["text"], count=1)
        fixed.append(it)
    items = fixed

    # newest first; one entry per text per day; page edits only once per page
    items.sort(key=lambda x: x["dt"], reverse=True)
    out, seen = [], set()
    for it in items:
        key = (it["text"], it["dt"].date()) if it["kind"] != "page" else (it["text"],)
        if key in seen:
            continue
        seen.add(key)
        it["date"] = f"{it['dt'].day} {it['dt']:%b %Y}"
        out.append(it)
        if len(out) >= limit:
            break
    return out


if __name__ == "__main__":
    for it in build_activity(Path(__file__).resolve().parent.parent):
        print(it["date"], "|", it["text"], "|", it["link"])
