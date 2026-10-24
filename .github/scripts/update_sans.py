#!/usr/bin/env python3
"""Refresh the SANS-derived blocks in README.md from the public SANS instructor profile.

Rewrites three marked blocks:
  SANS:TEACHING  - upcoming LDR553 course runs (event, location, start date)
  SANS:UPCOMING  - webcasts dated today or later
  SANS:RECENT    - newest white papers and most recent past webcasts

Everything rendered comes verbatim from the profile page. Standard library only.
If the page yields no cards at all, the script exits non-zero and leaves README untouched.
"""
import html
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta

PROFILE_URL = "https://www.sans.org/profiles/matt-bromiley"
BASE = "https://www.sans.org"
INSTRUCTOR = "Matt Bromiley"
MAX_RECENT_PAPERS = 5
MAX_RECENT_TALKS = 5
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 bromiley-profile-readme/1.0"
)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


def strip_tags(fragment: str) -> str:
    fragment = re.sub(r"<(script|style|svg|img)[^>]*>(.*?</\1>)?", "", fragment, flags=re.S)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", html.unescape(fragment)).strip()


def parse_date(text: str):
    m = re.search(r"(\d{1,2} [A-Z][a-z]{2} \d{4})", text)
    return datetime.strptime(m.group(1), "%d %b %Y").date() if m else None


def fmt(d: date) -> str:
    return d.strftime("%b %-d, %Y")


def md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("[", "\\[").replace("]", "\\]")


# ---------- parsers ----------

def course_runs(page: str):
    for card in re.findall(r'<article class="c-course-run-card">(.*?)</article>', page, flags=re.S):
        ev = re.search(r'href="(/cyber-security-training-events/[^"]+)">([^<]+)</a>', card)
        start = parse_date(strip_tags(card))
        days = re.search(r"(\d+) Days", card)
        if not (ev and start and days):
            continue
        name, _, city = (html.unescape(ev.group(2)).partition(" | "))
        formats = {html.unescape(f).strip() for f in re.findall(r'button__label">([^<]+)<', card)}
        virtual = any("Virtual" in f for f in formats)
        yield {
            "name": name.strip(),
            "url": BASE + ev.group(1),
            "location": city.strip() + (" + Virtual" if virtual and city.strip() else ""),
            "start": start,
            "end": start + timedelta(days=int(days.group(1)) - 1),
        }


def webcasts(page: str):
    pattern = r'<a class="c-podcast-card c-webinar-card[^"]*"[^>]*href="(/webcasts/[^"]+)"(.*?)</a>'
    for href, body in re.findall(pattern, page, flags=re.S):
        title = re.search(r'podcast-card__title">(.*?)</h2>', body, flags=re.S)
        details = re.findall(r'<li class="detail-list__list-item">(.*?)</li>', body, flags=re.S)
        details = [strip_tags(d) for d in details]
        when = next((parse_date(d) for d in details if parse_date(d)), None)
        if not (title and when):
            continue
        presenters = details[-1] if len(details) >= 3 else ""
        yield {"title": strip_tags(title.group(1)), "url": BASE + href, "date": when, "presenters": presenters}


def white_papers(page: str):
    pattern = r'<a class="[^"]*c-resource-card[^"]*"[^>]*href="(/white-papers/[^"]+)"(.*?)</a>'
    for href, body in re.findall(pattern, page, flags=re.S):
        title = re.search(r'resource-card__title">(.*?)</h3>', body, flags=re.S)
        when = parse_date(strip_tags(body))
        if title and when:
            yield {"title": strip_tags(title.group(1)), "url": BASE + href, "date": when}


def co_presenters(presenters: str) -> str:
    """Return ' (with A & B)' for named co-presenters, or '' if none or the list is truncated."""
    if not presenters or "more" in presenters:
        return ""
    names = [n.strip() for n in re.split(r",|&", presenters) if n.strip() and n.strip() != INSTRUCTOR]
    if not names:
        return ""
    return " (with " + (" & ".join(names) if len(names) <= 2 else ", ".join(names)) + ")"


# ---------- renderers ----------

def render_teaching(runs, today: date) -> str:
    rows = ["| Event | Location | Course start |", "|---|---|---|"]
    for r in sorted((r for r in runs if r["end"] >= today), key=lambda r: r["start"]):
        flag = " *(in progress)*" if r["start"] <= today <= r["end"] else ""
        rows.append(f"| [{md_escape(r['name'])}]({r['url']}) | {md_escape(r['location'])} | {fmt(r['start'])}{flag} |")
    if len(rows) == 2:
        return "No upcoming course runs are scheduled right now."
    return "\n".join(rows)


def render_upcoming(talks, today: date) -> str:
    rows = ["| Date | Talk |", "|---|---|"]
    for t in sorted((t for t in talks if t["date"] >= today), key=lambda t: t["date"]):
        rows.append(f"| {fmt(t['date'])} | [{md_escape(t['title'])}]({t['url']}){co_presenters(t['presenters'])} |")
    if len(rows) == 2:
        return "No upcoming talks are scheduled right now."
    return "\n".join(rows)


def render_recent(papers, talks, today: date) -> str:
    out = ["**SANS white papers**"]
    for p in sorted(papers, key=lambda p: p["date"], reverse=True)[:MAX_RECENT_PAPERS]:
        out.append(f"- [{md_escape(p['title'])}]({p['url']}) ({p['date'].strftime('%b %Y')})")
    out += ["", "**Recent talks**"]
    past = sorted((t for t in talks if t["date"] < today), key=lambda t: t["date"], reverse=True)
    for t in past[:MAX_RECENT_TALKS]:
        out.append(f"- [{md_escape(t['title'])}]({t['url']}){co_presenters(t['presenters'])} ({t['date'].strftime('%b %Y')})")
    return "\n".join(out)


def replace_block(readme: str, key: str, body: str) -> str:
    start, end = f"<!-- SANS:{key}:START -->", f"<!-- SANS:{key}:END -->"
    if start not in readme or end not in readme:
        raise SystemExit(f"README is missing the SANS:{key} markers.")
    before, rest = readme.split(start, 1)
    _, after = rest.split(end, 1)
    return f"{before}{start}\n{body}\n{end}{after}"


def main(readme_path: str) -> int:
    page = fetch(PROFILE_URL)
    runs, talks, papers = list(course_runs(page)), list(webcasts(page)), list(white_papers(page))
    if not (runs or talks or papers):
        print("Parsed nothing from the SANS profile page; leaving README unchanged.", file=sys.stderr)
        return 1
    today = date.today()
    with open(readme_path, encoding="utf-8") as f:
        readme = f.read()
    updated = replace_block(readme, "TEACHING", render_teaching(runs, today))
    updated = replace_block(updated, "UPCOMING", render_upcoming(talks, today))
    updated = replace_block(updated, "RECENT", render_recent(papers, talks, today))
    if updated == readme:
        print(f"SANS blocks already up to date ({len(runs)} course runs, {len(talks)} webcasts, {len(papers)} papers).")
        return 0
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(updated)
    print(f"Updated SANS blocks: {len(runs)} course runs, {len(talks)} webcasts, {len(papers)} papers parsed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "README.md"))
