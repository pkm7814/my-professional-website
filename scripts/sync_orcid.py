#!/usr/bin/env python3
"""Pull public works from ORCID into data/publications_orcid.yaml.

Uses the official public ORCID API (no key needed, read-only). Runs before every
deploy and on a weekly schedule. If ORCID is unreachable the existing file is kept,
so a temporary outage never breaks the website.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "publications_orcid.yaml"
ORCID_RE = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")


def fetch_works(orcid_id: str) -> list[dict]:
    req = urllib.request.Request(f"https://pub.orcid.org/v3.0/{orcid_id}/works",
                                 headers={"Accept": "application/json", "User-Agent": "personal-website-sync"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)

    works = []
    for group in data.get("group", []):
        summary = (group.get("work-summary") or [{}])[0]  # ORCID's preferred version
        title = ((summary.get("title") or {}).get("title") or {}).get("value")
        if not title:
            continue
        year = (((summary.get("publication-date") or {}).get("year")) or {}).get("value")
        journal = (summary.get("journal-title") or {}).get("value")
        doi, url = None, (summary.get("url") or {}).get("value")
        for ext in (summary.get("external-ids") or {}).get("external-id", []):
            if ext.get("external-id-type") == "doi":
                doi = ext.get("external-id-value", "").lower().removeprefix("https://doi.org/")
                break
        works.append({"title": title.strip(), "year": int(year) if year else None, "journal": journal,
                      "type": (summary.get("type") or "").lower(), "doi": doi, "url": url, "source": "orcid"})
    works.sort(key=lambda w: (w["year"] or 0, w["title"]), reverse=True)
    return works


def main() -> int:
    site = yaml.safe_load((ROOT / "data" / "profile.yaml").read_text(encoding="utf-8")) or {}
    orcid_id = str(site.get("orcid_id") or "").strip()
    if not orcid_id:
        print("No orcid_id in data/profile.yaml — skipping ORCID sync.")
        return 0
    if not ORCID_RE.match(orcid_id):
        print(f"orcid_id '{orcid_id}' does not look like 0000-0000-0000-0000 — skipping.")
        return 0
    try:
        works = fetch_works(orcid_id)
    except Exception as exc:
        print(f"warning: ORCID unreachable ({exc}); keeping existing publications.")
        return 0
    OUT.write_text(yaml.safe_dump(works, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"Synced {len(works)} works from ORCID {orcid_id}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
