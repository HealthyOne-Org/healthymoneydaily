#!/usr/bin/env python3
"""
blog_publish.py: build a Healthy Money Daily post from blog/_content/<slug>.json.

Idempotent and safe to re-run. It:
  1. Checks the post against the money-content gates (scripts/CONTENT_GUIDELINES.md): word count, official
     sources, FAQ, no stock picks or "guaranteed" language, no "free" next to the app, no trading-bot talk.
  2. Picks the post's photo from the library (blog/_content/photos.json -> assets/photos/<key>-1600.webp and
     -800.webp), falling back to the lane's photo, and crops a 1200x630 blog/images/<slug>-og.jpg for social cards.
  3. Renders blog/<slug>.html from blog/_content/_template.html (Budget Shield card at <!--MID-->, sources,
     FAQ + FAQPage JSON-LD, the disclaimer, CTA box, sticky bar, PostHog).
  4. Adds a card to the top of blog/index.html and refreshes the 3 newest on the homepage.
  5. Adds the URL to sitemap.xml and llms.txt, and marks the slug done in blog/_content/topics.json.

Usage (repo root):
  python3 -I scripts/blog_publish.py <slug> [--date YYYY-MM-DD] [--dry]
  # add a new photo to the library and set it as this post's image (then run the publish above):
  python3 -I scripts/blog_publish.py <slug> --image-file PATH --image-alt "what the photo shows" \
      --image-credit "Photographer" --image-credit-url https://unsplash.com/photos/<id>

JSON schema (blog/_content/<slug>.json):
  slug, title, description, keywords[], lane, read_min, excerpt, body_html (with <!--MID-->),
  faq[{q,a}] (3+), bottom_line, sources[{name, url}] (2+, official first), cta_title, cta_text
  optional: deck (subtitle under the title), as_of (for news posts: "November 11, 2026, 8:40 PM ET"),
            mid_card {title, text},
            image: a key from blog/_content/photos.json (e.g. "colonnade"), or {"key": "...", "alt": "post-specific
                   alt text"}. Missing -> the lane photo (news coffee-paper, howto planner-pen, prices kitchen-brass,
                   check vintage-desk). "art" from older posts is ignored.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html as htmllib
import json
import re
import sys
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


# ---------------------------------------------------------------- photos
# Every post has a photo. post["image"] is a key in blog/_content/photos.json (the library); the files are
# assets/photos/<key>-1600.webp and <key>-800.webp. No image -> the lane's fallback below.
LANE_IMAGE = {"news": "coffee-paper", "howto": "planner-pen", "prices": "kitchen-brass", "check": "vintage-desk"}
PHOTOS_DIR = ROOT / "assets" / "photos"
LIBRARY = CONTENT / "photos.json"


def load_library() -> dict:
    if not LIBRARY.exists():
        die(f"{LIBRARY.relative_to(ROOT)} is missing")
    return {k: v for k, v in json.loads(LIBRARY.read_text()).items() if not k.startswith("_")}


def photo_for(post: dict, lib: dict) -> tuple[str, dict]:
    img = post.get("image")
    if isinstance(img, dict):  # {"key": "...", "alt": "optional override"}
        key, alt = img.get("key", ""), img.get("alt")
    else:
        key, alt = (img or LANE_IMAGE[post["lane"]]), None
    if key not in lib:
        die(f"image {key!r} is not in {LIBRARY.relative_to(ROOT)}; add it with --image-file")
    meta = dict(lib[key])
    if alt:
        meta["alt"] = alt
    for w in (1600, 800):
        if not (PHOTOS_DIR / f"{key}-{w}.webp").exists():
            die(f"assets/photos/{key}-{w}.webp is missing")
    return key, meta


def picture(key: str, meta: dict, sizes: str, alt: str | None = None, lazy: bool = True, style: bool = True) -> str:
    a = meta["alt"] if alt is None else alt
    pos = f' style="object-position:{meta["pos"]}"' if style and meta.get("pos") else ""
    return (f'<img src="/assets/photos/{key}-1600.webp" srcset="/assets/photos/{key}-800.webp 800w, '
            f'/assets/photos/{key}-1600.webp 1600w" sizes="{sizes}" alt="{esc(a)}" width="{meta.get("w", 1600)}" '
            f'height="{meta.get("h", 1066)}"' + (' loading="lazy" decoding="async"' if lazy else ' fetchpriority="high"')
            + pos + ">")


def add_image(src: Path, key: str, alt: str, credit: str, credit_url: str, dry: bool) -> None:
    """Optimise a new photo into the library: 1600px + 800px WebP, each under ~250 KB."""
    try:
        from PIL import Image
    except ImportError:
        die("--image-file needs Pillow (python3 -m pip install pillow)")
    if not src.exists():
        die(f"{src} not found")
    if not alt or not credit:
        die("--image-file needs --image-alt and --image-credit (photographer, or 'Hardaway Labs' for our own)")
    im = Image.open(src).convert("RGB")
    if im.width < 1600:
        print(f"  warning: {src.name} is only {im.width}px wide")
    size = None
    for w in (1600, 800):
        ww = min(w, im.width)
        r = im.resize((ww, round(im.height * ww / im.width)), Image.LANCZOS)
        if w == 1600:
            size = r.size
        out = PHOTOS_DIR / f"{key}-{w}.webp"
        if dry:
            continue
        PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
        q = 82
        while True:
            r.save(out, "WEBP", quality=q, method=6)
            if out.stat().st_size < 250_000 or q <= 50:
                break
            q -= 6
        print(f"  photo: {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)")
    lib = json.loads(LIBRARY.read_text())
    lib[key] = {"alt": alt, "credit": credit, "credit_url": credit_url, "w": size[0], "h": size[1], "pos": "50% 50%",
                "mood": "", "fits": []}
    if not dry:
        LIBRARY.write_text(json.dumps(lib, indent=1, ensure_ascii=False) + "\n")
    print(f"  photos.json: {key} added")


def render_og(key: str, slug: str, meta: dict, dry: bool) -> str:
    """1200x630 JPEG for social cards, cropped from the photo. Falls back to the WebP itself."""
    og = IMAGES / f"{slug}-og.jpg"
    try:
        from PIL import Image
        if not dry:
            IMAGES.mkdir(parents=True, exist_ok=True)
            im = Image.open(PHOTOS_DIR / f"{key}-1600.webp").convert("RGB")
            tw, th = 1200, 630
            scale = max(tw / im.width, th / im.height)
            im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
            px, py = (float(v.rstrip("%")) / 100 for v in (meta.get("pos") or "50% 50%").split()[:2])
            left, top = round((im.width - tw) * px), round((im.height - th) * py)
            im.crop((left, top, left + tw, top + th)).save(og, "JPEG", quality=84, optimize=True, progressive=True)
            print(f"  og: {og.relative_to(ROOT)} ({og.stat().st_size // 1024} KB)")
        return f"{SITE}/blog/images/{slug}-og.jpg"
    except ImportError:
        return f"{SITE}/assets/photos/{key}-1600.webp"


def ensure_images(post: dict, dry: bool) -> tuple[str, str]:
    """Returns (hero <figure> html, og image url)."""
    key, meta = photo_for(post, load_library())
    credit = ""
    if meta.get("credit"):
        who = esc(meta["credit"])
        if meta.get("credit_url"):
            who = f'<a href="{esc(meta["credit_url"])}" rel="noopener">{who}</a>'
        src = " / Unsplash" if "unsplash.com" in meta.get("credit_url", "") else ""
        credit = f"<figcaption>Photo: {who}{src}</figcaption>"
    fig = (f'<figure class="art-hero">{picture(key, meta, "(min-width: 1360px) 1360px, 100vw", lazy=False)}'
           f'{credit}</figure>')
    print(f"  photo: {key}" + ("" if post.get("image") else f" (lane fallback for {post['lane']})"))
    return fig, render_og(key, post["slug"], meta, dry)


# ---------------------------------------------------------------- render
MID_CARD = """<aside class="app-card" aria-label="Budget Shield">
          <img src="/assets/budget-shield.jpg" alt="" width="64" height="64">
          <div class="t-wrap"><p class="t">{title}</p><p class="d">{text}</p></div>
          <a class="btn btn-line" data-placement="mid" rel="noopener" href="https://apps.apple.com/app/id6766591206?pt=128318750&amp;ct=hmd_mid&amp;mt=8">See Budget Shield</a>
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
    key, meta = photo_for(post, load_library())
    img = picture(key, meta, "(min-width: 760px) 50vw, 100vw", alt="", style=False)
    return (f'<article class="post" data-slug="{slug}">\n'
            f'        <a class="thumb" href="/blog/{slug}" tabindex="-1" aria-hidden="true">{img}</a>\n'
            f'        <div class="post-text">\n          <p class="tag">{LANES[post["lane"]]}</p>\n'
            f'          <{h}><a href="/blog/{slug}">{title}</a></{h}>\n'
            f'          <p class="excerpt">{esc(post["excerpt"].strip())}</p>\n'
            f'          <p class="meta"><time datetime="{date.isoformat()}">{human_date(date)}</time>'
            f'<span>{post["read_min"]} min read</span></p>\n        </div>\n      </article>')


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
    ap.add_argument("--image-file", help="add this photo to the library as <slug> and set it as the post's image")
    ap.add_argument("--image-alt", default="")
    ap.add_argument("--image-credit", default="")
    ap.add_argument("--image-credit-url", default="")
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
    if a.image_file:
        add_image(Path(a.image_file).expanduser(), a.slug, a.image_alt.strip(), a.image_credit.strip(),
                  a.image_credit_url.strip(), a.dry)
        post["image"] = a.slug
        if not a.dry:
            src.write_text(json.dumps(post, indent=1, ensure_ascii=False) + "\n")
        print(f"  {src.name}: image set to {a.slug!r}. Now run: python3 -I scripts/blog_publish.py {a.slug} --dry")
        return

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
    hero, og_url = ensure_images(post, a.dry)
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
    if not a.dry:
        # Fresh ?v= on site.css/site.js links, so phones that cached older styling fetch the current one.
        # (Loaded by path: `python3 -I` leaves the script's folder off sys.path.)
        import importlib.util
        spec = importlib.util.spec_from_file_location("stamp_assets", Path(__file__).with_name("stamp_assets.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.stamp()
    print(f"Done. Live URL after deploy: {SITE}/blog/{a.slug}")


if __name__ == "__main__":
    main()
