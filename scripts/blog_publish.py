#!/usr/bin/env python3
"""
blog_publish.py: build a Healthy Money Daily post from blog/_content/<slug>.json.

Idempotent and safe to re-run. It:
  1. Checks the post against the money-content gates (scripts/CONTENT_GUIDELINES.md): word count, official
     sources, FAQ, no stock picks or "guaranteed" language, no "free" next to the app, no trading-bot talk.
  2. Draws the header art blog/images/<slug>-hero.svg (calm SVG, no photos needed). With --pexels-key and
     "image_queries" in the JSON it downloads a 1200x675 Pexels photo to <slug>-hero.jpg and uses that instead.
     If Google Chrome is installed it also renders <slug>-og.png (1200x630) for social cards.
  3. Renders blog/<slug>.html from blog/_content/_template.html (Budget Shield card at <!--MID-->, sources,
     FAQ + FAQPage JSON-LD, the disclaimer, CTA box, sticky bar, PostHog).
  4. Adds a card to the top of blog/index.html and refreshes the 3 newest on the homepage.
  5. Adds the URL to sitemap.xml and llms.txt, and marks the slug done in blog/_content/topics.json.

Usage (repo root):
  python3 -I scripts/blog_publish.py <slug> [--date YYYY-MM-DD] [--pexels-key KEY] [--dry]

JSON schema (blog/_content/<slug>.json):
  slug, title, description, keywords[], lane, read_min, excerpt, body_html (with <!--MID-->),
  faq[{q,a}] (3+), bottom_line, sources[{name, url}] (2+, official first), cta_title, cta_text
  optional: deck (subtitle under the title), art ("gift" | "rates" | "calendar" | "cart" | "jar" | "shield" |
            "check"), as_of (for news posts: "November 11, 2026, 8:40 PM ET"), image_queries[], hero_credit
"""
from __future__ import annotations

import argparse
import datetime as dt
import html as htmllib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOG = ROOT / "blog"
CONTENT = BLOG / "_content"
IMAGES = BLOG / "images"
TEMPLATE = CONTENT / "_template.html"
INDEX = BLOG / "index.html"
HOME = ROOT / "index.html"
SITEMAP = ROOT / "sitemap.xml"
TOPICS = CONTENT / "topics.json"
LLMS = ROOT / "llms.txt"
SITE = "https://www.healthymoneydaily.com"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

REQUIRED = ["slug", "title", "description", "keywords", "lane", "read_min", "excerpt", "body_html", "faq",
            "bottom_line", "sources", "cta_title", "cta_text"]
LANES = {"news": "Money news, explained", "howto": "Budgeting how-to", "prices": "Prices & household",
         "check": "Monday Money Check"}
OFFICIAL = ("bls.gov", "federalreserve.gov", "federalregister.gov", "consumerfinance.gov", "fdic.gov", "treasury.gov",
            "irs.gov", "ftc.gov", "bea.gov", "census.gov", "usa.gov", "studentaid.gov", "ssa.gov", "eia.gov",
            "usda.gov", "hud.gov", "fred.stlouisfed.org", "newyorkfed.org", "consumer.ftc.gov", "annualcreditreport.com")

# Sentences that must never appear (CONTENT_GUIDELINES.md "Hard no"). Lower-case regexes.
BANNED = [
    (r"\bguarantee[ds]?\b", "no guarantees in money content"),
    (r"\b(buy|sell|short)\s+(shares|stock|calls|puts)\b", "no buy/sell calls"),
    (r"\bstock picks?\b(?![^.]*\b(we|never|don't|do not|no)\b)", "no stock picks"),
    (r"\b(our|my) (trading )?bots?\b", "never mention the trading bots"),
    (r"\bpaper trad", "never mention practice trading"),
    (r"\b(risk[- ]free|get rich|can't lose|sure thing)\b", "no hype"),
    (r"\bfree\b[^.]{0,40}\bbudget shield\b|\bbudget shield\b[^.]{0,40}\bfree\b", "no 'free' next to the app"),
    (r"in today's fast-paced world", "cliche"),
]


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def esc(s: str) -> str:
    return htmllib.escape(s, quote=True)


def plain(s: str) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def human_date(d: dt.date) -> str:
    return f"{d.strftime('%B')} {d.day}, {d.year}"


# ---------------------------------------------------------------- gates
def check(post: dict) -> list[str]:
    errs = []
    words = len(plain(post["body_html"]).split())
    if words < 1100:
        errs.append(f"body is {words} words; aim 1,200-1,600")
    if words > 1900:
        errs.append(f"body is {words} words; keep it under ~1,600 (1,900 hard cap)")
    if "<!--MID-->" not in post["body_html"]:
        errs.append("body_html needs a <!--MID--> marker about a third of the way down (Budget Shield card)")
    if len(post["faq"]) < 3:
        errs.append("need at least 3 FAQ entries")
    srcs = post["sources"]
    if len(srcs) < 2:
        errs.append("need at least 2 sources")
    if not any(any(o in s.get("url", "") for o in OFFICIAL) for s in srcs):
        errs.append("at least one source must be official (.gov / Federal Reserve / CFPB / BLS ...)")
    if post["lane"] not in LANES:
        errs.append(f"lane must be one of {sorted(LANES)}")
    hay = " ".join([post["title"], post["description"], post["body_html"], post["bottom_line"],
                    " ".join(f["q"] + " " + f["a"] for f in post["faq"]), post["cta_text"]])
    low = plain(hay).lower()
    for rx, why in BANNED:
        m = re.search(rx, low)
        if m:
            errs.append(f"banned phrase ({why}): ...{low[max(0, m.start() - 40):m.end() + 40]}...")
    if re.search(r"polymarket|betting odds|prediction market", low) and not re.search(r"not a prediction|not a forecast|odds are not", low):
        errs.append("market odds must be called odds, with 'not a prediction' said plainly")
    for a in re.findall(r'href="(https?://[^"]+)"', post["body_html"]):
        if "apps.apple.com" in a:
            errs.append("no App Store links in body_html; the template places them (tracked)")
    if not 45 <= len(post["title"]) <= 95:
        errs.append(f"title is {len(post['title'])} chars; aim 55-80")
    return errs


# ---------------------------------------------------------------- art
PAPER, GRID, INK, GREEN, GREEN2, SOFT, GOLD = "#F3EEE2", "#E4DCCB", "#14201A", "#1F5B41", "#2C7A55", "#DCE8DE", "#A8823A"


def _frame(inner: str, label: str) -> str:
    lines = "".join(f'<line x1="{x}" y1="0" x2="{x}" y2="630" />' for x in range(40, 1200, 40))
    lines += "".join(f'<line x1="0" y1="{y}" x2="1200" y2="{y}" />' for y in range(30, 630, 40))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630" width="1200" height="630" role="img" '
            f'aria-label="{esc(label)}"><rect width="1200" height="630" fill="{PAPER}"/>'
            f'<g stroke="{GRID}" stroke-width="1" opacity=".55">{lines}</g>{inner}</svg>\n')


def art_gift() -> str:  # a December calendar with paydays and a gift envelope
    cells = []
    for i in range(35):
        r, c = divmod(i, 7)
        x, y = 600 + c * 76, 120 + r * 76
        fill = SOFT
        if i in (4, 18):
            fill = GREEN
        if i in (23, 24):
            fill = GOLD
        cells.append(f'<rect x="{x}" y="{y}" width="64" height="64" rx="10" fill="{fill}"/>')
    env = (f'<g transform="translate(120 170) rotate(-6)"><rect width="360" height="240" rx="18" fill="{GREEN}"/>'
           f'<path d="M0 18 L180 140 L360 18" fill="none" stroke="{PAPER}" stroke-width="6"/>'
           f'<rect x="160" y="0" width="40" height="240" fill="{GOLD}" opacity=".9"/>'
           f'<circle cx="180" cy="120" r="34" fill="{PAPER}"/><text x="180" y="134" text-anchor="middle" '
           f'font-family="Georgia,serif" font-size="40" font-style="italic" fill="{GREEN}">$</text></g>')
    return env + "".join(cells) + f'<rect x="596" y="116" width="524" height="2" fill="{INK}" opacity=".7"/>'


def art_rates() -> str:  # a stepped rate line rising, with a dashed "what if" step
    pts = [(120, 470), (300, 470), (300, 430), (480, 430), (480, 400), (660, 400), (660, 380), (840, 380)]
    d = "M" + " L".join(f"{x} {y}" for x, y in pts)
    dots = "".join(f'<circle cx="{x}" cy="{y}" r="9" fill="{GREEN}"/>' for x, y in pts[1::2])
    proj = f'<path d="M840 380 L840 340 L1060 340" fill="none" stroke="{GOLD}" stroke-width="8" stroke-dasharray="18 14"/>'
    bars = "".join(f'<rect x="{150 + i * 120}" y="{520 - h}" width="64" height="{h}" rx="6" fill="{SOFT}"/>'
                   for i, h in enumerate((60, 80, 95, 110, 120, 128, 150, 170)))
    pct = (f'<text x="1010" y="250" text-anchor="middle" font-family="Georgia,serif" font-size="210" font-style="italic" '
           f'fill="{GREEN}" opacity=".9">%</text>')
    return (bars + f'<path d="{d}" fill="none" stroke="{GREEN}" stroke-width="10" stroke-linejoin="round"/>' + dots
            + proj + pct + f'<rect x="100" y="520" width="1000" height="3" fill="{INK}" opacity=".75"/>')


def art_calendar() -> str:
    rows = "".join(
        f'<rect x="150" y="{150 + i * 78}" width="900" height="58" rx="10" fill="{SOFT if i % 2 else PAPER}" stroke="{GRID}"/>'
        f'<rect x="170" y="{168 + i * 78}" width="{140 + (i * 53) % 220}" height="22" rx="6" fill="{GREEN if i != 2 else GOLD}"/>'
        f'<rect x="900" y="{168 + i * 78}" width="120" height="22" rx="6" fill="{INK}" opacity=".18"/>' for i in range(5))
    return rows + f'<rect x="150" y="120" width="900" height="3" fill="{INK}" opacity=".75"/>'


def art_cart() -> str:
    return (f'<g fill="none" stroke="{GREEN}" stroke-width="12" stroke-linecap="round" stroke-linejoin="round">'
            f'<path d="M260 180 L330 180 L390 420 L800 420 L860 240 L360 240"/></g>'
            f'<circle cx="430" cy="480" r="30" fill="{GREEN}"/><circle cx="760" cy="480" r="30" fill="{GREEN}"/>'
            f'<g transform="translate(860 120) rotate(14)"><path d="M0 0 L150 0 L190 50 L150 100 L0 100 Z" fill="{GOLD}"/>'
            f'<circle cx="150" cy="50" r="12" fill="{PAPER}"/></g>'
            + "".join(f'<rect x="{420 + i * 90}" y="{290 - (i % 2) * 30}" width="70" height="{120 + (i % 2) * 30}" rx="8" '
                      f'fill="{SOFT if i % 2 else GREEN2}"/>' for i in range(4)))


def art_jar() -> str:
    coins = "".join(f'<ellipse cx="{600 + ((i * 37) % 90) - 45}" cy="{470 - i * 26}" rx="70" ry="16" '
                    f'fill="{GOLD if i % 3 else GREEN2}" stroke="{PAPER}" stroke-width="3"/>' for i in range(8))
    return (f'<rect x="440" y="150" width="320" height="380" rx="60" fill="{SOFT}" stroke="{GREEN}" stroke-width="10"/>'
            f'<rect x="470" y="110" width="260" height="50" rx="14" fill="{GREEN}"/>' + coins
            + f'<rect x="120" y="530" width="960" height="3" fill="{INK}" opacity=".75"/>')


def art_shield() -> str:
    return (f'<path d="M600 90 L820 160 L820 330 C820 450 720 520 600 560 C480 520 380 450 380 330 L380 160 Z" '
            f'fill="{GREEN}"/><path d="M450 400 L540 330 L600 370 L720 250" fill="none" stroke="{PAPER}" stroke-width="16" '
            f'stroke-linecap="round" stroke-linejoin="round"/><path d="M690 245 L730 245 L730 285" fill="none" '
            f'stroke="{PAPER}" stroke-width="16" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<circle cx="1000" cy="160" r="60" fill="{GOLD}"/><circle cx="200" cy="470" r="40" fill="{SOFT}"/>')


def art_check() -> str:
    rows = ""
    for i in range(5):
        y = 150 + i * 80
        box = (f'<rect x="300" y="{y}" width="44" height="44" rx="8" fill="{GREEN if i < 3 else PAPER}" stroke="{GREEN}" stroke-width="4"/>'
               + (f'<path d="M310 {y + 22} L320 {y + 32} L336 {y + 12}" fill="none" stroke="{PAPER}" stroke-width="6"/>' if i < 3 else ""))
        rows += box + f'<rect x="370" y="{y + 12}" width="{300 + (i * 97) % 240}" height="20" rx="6" fill="{INK}" opacity=".16"/>'
    return rows + f'<circle cx="960" cy="200" r="80" fill="{GOLD}" opacity=".9"/>'


ARTS = {"gift": art_gift, "rates": art_rates, "calendar": art_calendar, "cart": art_cart, "jar": art_jar,
        "shield": art_shield, "check": art_check}
DEFAULT_ART = {"news": "rates", "howto": "calendar", "prices": "cart", "check": "check"}


def pexels_download(key: str, query: str, dest: Path) -> str | None:
    url = "https://api.pexels.com/v1/search?" + urllib.parse.urlencode(
        {"query": query, "per_page": 8, "orientation": "landscape", "size": "large"})
    req = urllib.request.Request(url, headers={"Authorization": key, "User-Agent": "healthymoneydaily-blog/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
    except Exception as e:  # noqa: BLE001
        print(f"  pexels search failed: {e}")
        return None
    for photo in data.get("photos", []):
        src = photo.get("src", {}).get("original")
        if not src:
            continue
        try:
            req2 = urllib.request.Request(f"{src}?auto=compress&cs=tinysrgb&fit=crop&w=1200&h=675",
                                          headers={"User-Agent": "healthymoneydaily-blog/1.0"})
            with urllib.request.urlopen(req2, timeout=60) as r, open(dest, "wb") as f:
                shutil.copyfileobj(r, f)
            if dest.stat().st_size > 20_000:
                return f"Photo by {photo.get('photographer', 'a Pexels photographer')} via Pexels"
        except Exception as e:  # noqa: BLE001
            print(f"  pexels download failed: {e}")
    return None


def render_og(svg: Path, png: Path) -> bool:
    """Screenshot the SVG with headless Chrome so social cards get a PNG. Optional."""
    if not CHROME.exists():
        return False
    with tempfile.TemporaryDirectory() as td:
        try:
            subprocess.run([str(CHROME), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                            f"--user-data-dir={td}/prof", "--window-size=1200,630", f"--screenshot={png}",
                            svg.resolve().as_uri()], capture_output=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            return False
    return png.exists() and png.stat().st_size > 5_000


def ensure_images(post: dict, pexels_key: str | None, dry: bool) -> tuple[str, str]:
    """Returns (hero <figure> html, og image url)."""
    slug, title = post["slug"], post["title"]
    IMAGES.mkdir(parents=True, exist_ok=True)
    jpg, svg, og = IMAGES / f"{slug}-hero.jpg", IMAGES / f"{slug}-hero.svg", IMAGES / f"{slug}-og.png"
    credit = post.get("hero_credit", "")
    if pexels_key and post.get("image_queries") and not jpg.exists() and not dry:
        credit = pexels_download(pexels_key, post["image_queries"][0], jpg) or ""
    if jpg.exists():
        fig = (f'<figure class="hero-fig"><img src="/blog/images/{slug}-hero.jpg" alt="{esc(title)}" width="1200" '
               f'height="675">' + (f'<figcaption>{esc(credit)}</figcaption>' if credit else "") + "</figure>")
        return fig, f"{SITE}/blog/images/{slug}-hero.jpg"
    art = post.get("art") or DEFAULT_ART[post["lane"]]
    if art not in ARTS:
        die(f"unknown art {art!r}; one of {sorted(ARTS)}")
    if not dry:
        svg.write_text(_frame(ARTS[art](), title))
        print(f"  art: {svg.name} ({art})")
        if render_og(svg, og):
            print(f"  og: {og.name}")
    fig = (f'<figure class="hero-fig"><img src="/blog/images/{slug}-hero.svg" alt="" width="1200" height="630">'
           "</figure>")
    og_url = f"{SITE}/blog/images/{slug}-og.png" if og.exists() else f"{SITE}/assets/og.png"
    return fig, og_url


# ---------------------------------------------------------------- render
MID_CARD = """<aside class="app-card" aria-label="Budget Shield">
          <img src="/assets/budget-shield.jpg" alt="" width="64" height="64">
          <div class="t-wrap"><p class="t">{title}</p><p class="d">{text}</p></div>
          <a class="btn btn-green" data-placement="mid" rel="noopener" href="https://apps.apple.com/app/id6766591206?pt=128318750&amp;ct=hmd_mid&amp;mt=8">See Budget Shield</a>
        </aside>"""
MID_DEFAULT = ("Budget Shield", "Lays out your next 30 days of bills and paychecks and warns you before a payment won't clear.")


def render(post: dict, date: dt.date, hero: str, og_url: str) -> str:
    tpl = TEMPLATE.read_text()
    slug, title = post["slug"], post["title"].strip()
    mt, md = post.get("mid_card", {}).get("title", MID_DEFAULT[0]), post.get("mid_card", {}).get("text", MID_DEFAULT[1])
    body = post["body_html"].strip().replace("<!--MID-->", MID_CARD.format(title=esc(mt), text=esc(md)), 1)
    faq_html = "\n".join(f"  <h3>{f['q'].strip()}</h3>\n  <p>{f['a'].strip()}</p>" for f in post["faq"])
    sources_html = "\n".join(
        f'      <li><a href="{esc(s["url"])}" rel="noopener">{esc(s["name"])}</a>'
        + (f' <span>{esc(s["note"])}</span>' if s.get("note") else "") + "</li>" for s in post["sources"])
    as_of = post.get("as_of")
    as_of_html = f'<p class="asof">Numbers as of {esc(as_of)}. We update this post when they change.</p>' if as_of else ""
    article_ld = json.dumps({
        "@context": "https://schema.org", "@type": "Article", "headline": title,
        "author": {"@type": "Person", "name": "Chris Hardaway", "url": f"{SITE}/about"},
        "publisher": {"@type": "Organization", "name": "Hardaway Labs LLC", "url": SITE},
        "datePublished": date.isoformat(), "dateModified": date.isoformat(),
        "description": post["description"].strip(), "image": og_url, "mainEntityOfPage": f"{SITE}/blog/{slug}",
        "citation": [s["url"] for s in post["sources"]],
    }, ensure_ascii=False)
    faq_ld = json.dumps({
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [{"@type": "Question", "name": plain(f["q"]),
                        "acceptedAnswer": {"@type": "Answer", "text": plain(f["a"])}} for f in post["faq"]],
    }, ensure_ascii=False)
    rep = {
        "{{ARTICLE_LD}}": article_ld, "{{FAQ_LD}}": faq_ld, "{{BODY}}": body, "{{FAQ_HTML}}": faq_html,
        "{{SOURCES_HTML}}": sources_html, "{{AS_OF}}": as_of_html, "{{HERO}}": hero,
        "{{BOTTOM_LINE}}": post["bottom_line"].strip(), "{{CTA_TITLE}}": esc(post["cta_title"].strip()),
        "{{CTA_TEXT}}": esc(post["cta_text"].strip()), "{{KEYWORDS}}": esc(", ".join(post["keywords"])),
        "{{DATE_HUMAN}}": human_date(date), "{{DATE_ISO}}": date.isoformat(), "{{READ_MIN}}": str(post["read_min"]),
        "{{DESCRIPTION}}": esc(post["description"].strip()), "{{DECK}}": esc(post.get("deck", post["description"]).strip()),
        "{{LANE}}": LANES[post["lane"]], "{{OG_IMAGE}}": og_url, "{{TITLE}}": esc(title), "{{SLUG}}": slug,
    }
    out = tpl
    for k, v in rep.items():
        out = out.replace(k, v)
    left = re.findall(r"\{\{[A-Z_]+\}\}", out)
    if left:
        die(f"unfilled placeholders: {left}")
    return out


def card(post: dict, date: dt.date, h: str = "h3") -> str:
    slug, title = post["slug"], esc(post["title"].strip())
    img = f"{slug}-hero.jpg" if (IMAGES / f"{slug}-hero.jpg").exists() else f"{slug}-hero.svg"
    return (f'<article class="post" data-slug="{slug}">\n'
            f'        <div>\n          <span class="tag">{LANES[post["lane"]]}</span>\n'
            f'          <{h}><a href="/blog/{slug}">{title}</a></{h}>\n'
            f'          <p>{esc(post["excerpt"].strip())}</p>\n'
            f'          <div class="meta">{human_date(date)} &middot; {post["read_min"]} min read</div>\n        </div>\n'
            f'        <a class="thumb" href="/blog/{slug}" tabindex="-1" aria-hidden="true"><img src="/blog/images/{img}" '
            f'alt="" loading="lazy" width="1200" height="630"></a>\n      </article>')


def splice(path: Path, start: str, end: str, new_card: str, slug: str, keep: int | None, dry: bool) -> None:
    html = path.read_text()
    i, j = html.find(start), html.find(end)
    if i < 0 or j < 0:
        die(f"{path.relative_to(ROOT)}: markers {start} / {end} not found")
    block = html[i + len(start):j]
    cards = re.findall(r'<article class="post" data-slug="[^"]+">.*?</article>', block, re.S)
    cards = [c for c in cards if f'data-slug="{slug}"' not in c]
    cards.insert(0, new_card)
    if keep:
        cards = cards[:keep]
    html = html[:i + len(start)] + "\n      " + "\n      ".join(cards) + "\n      " + html[j:]
    if not dry:
        path.write_text(html)
    print(f"  {path.relative_to(ROOT)}: {len(cards)} card(s)")


def update_sitemap(slug: str, date: dt.date, dry: bool) -> None:
    sm = SITEMAP.read_text()
    loc = f"{SITE}/blog/{slug}"
    sm = re.sub(rf"\s*<url><loc>{re.escape(loc)}</loc>.*?</url>", "", sm)
    sm = re.sub(r"(<loc>https://www\.healthymoneydaily\.com/(?:blog)?</loc><lastmod>)[0-9-]+", rf"\g<1>{date}", sm)
    sm = sm.replace("</urlset>", f"  <url><loc>{loc}</loc><lastmod>{date}</lastmod></url>\n</urlset>", 1)
    if not dry:
        SITEMAP.write_text(sm)
    print("  sitemap: entry set")


def update_llms(post: dict, dry: bool) -> None:
    if not LLMS.exists():
        return
    txt = LLMS.read_text()
    url = f"{SITE}/blog/{post['slug']}"
    if url + ")" in txt:
        print("  llms.txt: already listed")
        return
    line = f"- [{post['title'].strip()}]({url})\n"
    if "## Posts\n" not in txt:
        txt = txt.rstrip("\n") + "\n\n## Posts\n"
    txt = txt.replace("## Posts\n", "## Posts\n" + line, 1)
    if not dry:
        LLMS.write_text(txt)
    print("  llms.txt: post listed")


def mark_topic_done(slug: str, date: dt.date, dry: bool) -> None:
    if not TOPICS.exists():
        return
    topics = json.loads(TOPICS.read_text())
    hit = False
    for t in topics:
        if t.get("slug") == slug:
            t["done"] = date.isoformat()
            hit = True
    if hit and not dry:
        TOPICS.write_text(json.dumps(topics, indent=1, ensure_ascii=False) + "\n")
    print(f"  topics.json: {'marked done' if hit else 'slug not in queue (fine)'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--date", help="YYYY-MM-DD (default: today, America/New_York)")
    ap.add_argument("--pexels-key")
    ap.add_argument("--dry", action="store_true", help="check and render, write nothing")
    a = ap.parse_args()

    src = CONTENT / f"{a.slug}.json"
    if not src.exists():
        die(f"{src} not found")
    post = json.loads(src.read_text())
    missing = [k for k in REQUIRED if k not in post or post[k] in ("", [], None)]
    if missing:
        die(f"{src.name} missing fields: {missing}")
    if post["slug"] != a.slug:
        die("slug in JSON does not match argument")
    errs = check(post)
    if errs:
        die("content gates failed:\n  - " + "\n  - ".join(errs))

    if a.date:
        date = dt.date.fromisoformat(a.date)
    else:
        try:
            from zoneinfo import ZoneInfo
            date = dt.datetime.now(ZoneInfo("America/New_York")).date()
        except Exception:  # noqa: BLE001
            date = dt.date.today()

    words = len(plain(post["body_html"]).split())
    print(f"Publishing {a.slug} ({words} words, {len(post['faq'])} FAQ, {len(post['sources'])} sources) dated {date}")
    hero, og_url = ensure_images(post, a.pexels_key, a.dry)
    html = render(post, date, hero, og_url)
    out = BLOG / f"{a.slug}.html"
    if not a.dry:
        out.write_text(html)
    print(f"  wrote {out.relative_to(ROOT)} ({len(html):,} bytes)")
    splice(INDEX, "<!--POSTS:START-->", "<!--POSTS:END-->", card(post, date, "h2"), a.slug, None, a.dry)
    splice(HOME, "<!--LATEST:START-->", "<!--LATEST:END-->", card(post, date), a.slug, 3, a.dry)
    update_sitemap(a.slug, date, a.dry)
    update_llms(post, a.dry)
    mark_topic_done(a.slug, date, a.dry)
    print(f"Done. Live URL after deploy: {SITE}/blog/{a.slug}")


if __name__ == "__main__":
    main()
