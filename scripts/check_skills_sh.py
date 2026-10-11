#!/usr/bin/env python3
"""Check skills.sh listing status for dapetun/skills-organizer."""

from __future__ import annotations

import json
import re
import urllib.request

OWNER_REPO = "dapetun/skills-organizer"
SKILL = "skill-optimizer"
PAGE = f"https://www.skills.sh/{OWNER_REPO}/{SKILL}"
REPO_PAGE = f"https://www.skills.sh/{OWNER_REPO}"
SEARCH = "https://www.skills.sh/api/search?q=dapetun%2Fskills-organizer"
SEARCH2 = "https://www.skills.sh/api/search?q=skill-optimizer%20dapetun"


def fetch(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "skills-organizer-check/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def main() -> int:
    status, html = fetch(PAGE)
    title = re.search(r"<title>([^<]+)</title>", html)
    installs = re.findall(r"installs\\?\"\s*:\s*(\d+)", html, flags=re.I)
    installs += re.findall(r">(\d[\d,]*)\s*installs?<", html, flags=re.I)
    print(f"skill_page: {PAGE}")
    print(f"  http: {status}")
    print(f"  title: {title.group(1) if title else None}")
    print(f"  has_skill_body: {'Optimize coherence' in html or 'Skill Optimizer' in html}")
    print(f"  install_mentions: {installs[:10]}")
    print(f"  soft404: {'NEXT_HTTP_ERROR_FALLBACK;404' in html}")

    status2, html2 = fetch(REPO_PAGE)
    title2 = re.search(r"<title>([^<]+)</title>", html2)
    print(f"repo_page: {REPO_PAGE}")
    print(f"  http: {status2}")
    print(f"  title: {title2.group(1) if title2 else None}")
    print(f"  soft404: {'NEXT_HTTP_ERROR_FALLBACK;404' in html2}")

    for label, url in (("search_source", SEARCH), ("search_name", SEARCH2)):
        try:
            _, body = fetch(url)
            data = json.loads(body)
            hits = [
                s
                for s in data.get("skills", [])
                if "dapetun/skills-organizer" in str(s.get("id", ""))
                or s.get("source") == OWNER_REPO
            ]
            print(f"{label}: total={data.get('count')} ours={len(hits)}")
            for h in hits[:5]:
                print(f"  - {h.get('id')} installs={h.get('installs')}")
        except Exception as exc:
            print(f"{label}: error {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
