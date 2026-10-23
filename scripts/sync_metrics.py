#!/usr/bin/env python3
"""Fetch citation metrics automatically from OpenAlex (open scholarly database)
using the ORCID iD in data/profile.yaml, and save them to data/metrics_auto.yaml.

Google Scholar offers no public data feed and does not allow automated access, so
OpenAlex is used for the automatic numbers. If Google Scholar numbers are typed in
the admin editor (Profile & menu -> Google Scholar numbers), those are shown instead.

Needs a free OpenAlex API key in the GitHub secret OPENALEX_API_KEY. If the key is
missing or OpenAlex is unreachable, the previous numbers are kept.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "metrics_auto.yaml"


def main() -> int:
    profile = yaml.safe_load((ROOT / "data" / "profile.yaml").read_text(encoding="utf-8")) or {}
    orcid = str(profile.get("orcid_id") or "").strip()
    if not orcid:
        print("No ORCID iD — skipping metrics.")
        return 0
    key = os.environ.get("OPENALEX_API_KEY", "").strip()
    url = "https://api.openalex.org/authors/" + urllib.parse.quote(f"https://orcid.org/{orcid}", safe=":/")
    if key:
        url += "?api_key=" + urllib.parse.quote(key)
    else:
        print("note: OPENALEX_API_KEY secret not set; trying without a key.")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "personal-website-metrics"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            a = json.load(resp)
    except Exception as exc:
        print(f"warning: OpenAlex unavailable ({str(exc).replace(key, '***') if key else exc}); keeping previous metrics.")
        return 0
    stats = a.get("summary_stats") or {}
    data = {
        "source": "OpenAlex",
        "citations": int(a.get("cited_by_count") or 0),
        "h_index": int(stats.get("h_index") or 0),
        "i10_index": int(stats.get("i10_index") or 0),
        "works": int(a.get("works_count") or 0),
        "updated": date.today().strftime("%b %Y"),
    }
    OUT.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    print("Metrics:", data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
