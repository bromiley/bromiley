#!/usr/bin/env python3
"""Refresh the latest-episodes block in README.md from the podcast RSS feed.

Picks the newest "Intel Chat" episodes of The Cybersecurity Defenders Podcast
and rewrites the Markdown between the PODCAST markers. Standard library only.
"""
import html
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

FEED_URL = "https://feeds.transistor.fm/the-cybersecurity-defenders-podcast"
TITLE_FILTER = "intel chat"
MAX_EPISODES = 4
START = "<!-- PODCAST:START -->"
END = "<!-- PODCAST:END -->"


def fetch_feed(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "bromiley-profile-readme/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def episodes(feed_xml: bytes):
    channel = ET.fromstring(feed_xml).find("channel")
    for item in channel.findall("item"):
        title = html.unescape((item.findtext("title") or "").strip())
        if TITLE_FILTER not in title.lower():
            continue
        link = (item.findtext("link") or "").strip()
        pub = item.findtext("pubDate") or ""
        try:
            date = parsedate_to_datetime(pub)
        except (TypeError, ValueError):
            continue
        if not link:
            continue
        number = None
        m = re.search(r"\[#?(\d+)\]\s*$", title)
        if m:
            number = m.group(1)
            title = title[: m.start()].rstrip()
        yield date, number, title, link


def md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("[", "\\[").replace("]", "\\]")


def render(eps) -> str:
    rows = ["| Date | Episode |", "|---|---|"]
    for date, number, title, link in eps:
        label = md_escape(title)
        if number:
            label = f"{label} (#{number})"
        rows.append(f"| {date.strftime('%b %-d, %Y')} | [{label}]({link}) |")
    return "\n".join(rows)


def main(readme_path: str) -> int:
    eps = sorted(episodes(fetch_feed(FEED_URL)), key=lambda e: e[0], reverse=True)[:MAX_EPISODES]
    if not eps:
        print("No matching episodes found; leaving README unchanged.", file=sys.stderr)
        return 1
    with open(readme_path, encoding="utf-8") as f:
        readme = f.read()
    if START not in readme or END not in readme:
        print("README is missing the PODCAST markers.", file=sys.stderr)
        return 1
    before, rest = readme.split(START, 1)
    _, after = rest.split(END, 1)
    updated = f"{before}{START}\n{render(eps)}\n{END}{after}"
    if updated == readme:
        print("Episodes block already up to date.")
        return 0
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(updated)
    print(f"Updated episodes block with {len(eps)} episodes (newest: {eps[0][0].date()}).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "README.md"))
