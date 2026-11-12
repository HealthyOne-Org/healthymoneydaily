# Healthy Money Daily blog pipeline

Two posts a week (Tue + Thu, 8:31 AM ET) are written and published by the scheduled writer described in
`scripts/PUBLISHER_PROMPT.md`. This file is the operator's manual; the writer follows it. It mirrors the
Healthy Faith Daily pipeline (HealthyOne-Org/healthyfaithdaily).

## What the blog is for
healthymoneydaily.com turns money-news and budgeting searches into installs of **Budget Shield** (iOS,
App Store id 6766591206). Every post answers something a real person types ("what does a fed rate hike mean
for me", "how to budget for christmas", "how to catch up on past due bills") and ends by showing how a 30-day
bills-and-paychecks forecast helps with exactly that. Never a hard sell. Rules: `scripts/CONTENT_GUIDELINES.md`.

## Lanes (rotate; at most 1 news explainer a week)
1. **news** (Money news, explained): within ~24 h of a real event day (Fed decision, CPI or jobs surprise, a
   new tariff): what it means for bills, card, loans, groceries + "Three things to do this week".
2. **howto** (Budgeting how-to): paycheck-to-paycheck budget, bills calendar, past-due catch-up, first $500
   cushion, holiday budget, 50/30/20 → each ties to one Budget Shield feature.
3. **prices** (Prices & household): grocery/gas/heating prices from official data, cheaper swaps, subscriptions.
4. **check** (Monday Money Check): what changed last week for a household. Published on the Tuesday run.

## Topic queue
`blog/_content/topics.json`. Each run takes the first entry without `done` whose `target_date` (if any) is
not more than ~3 days away; seasonal entries come first. Fields: slug, lane, keyword, title (working),
angle (the Budget Shield tie), sources_hint (where the numbers come from; verify), art (legacy, ignored; pick
an `image` instead), target_date,
event (news entries tied to a scheduled release, e.g. `fed:2026-12-09`), done. When fewer than 5 are left,
append 10 in the same shape across the lanes.

## News bridge (read-only)
`~/.hermes/state/money_news_latest.json`, written hourly by `~/.hermes/scripts/money_news_export.py`
(hermes-skills repo). Keys: `event_days` (headline event days by kind), `scheduled_recent` /
`scheduled_upcoming` (CPI, jobs, Fed dates), `odds` (Polymarket macro odds with 24 h moves),
`household_items` (market-wide headlines a household feels), `official_tariff_notices` (Federal Register),
`earnings_upcoming`, `errors`. It is for choosing topics and dates only: confirm every fact at an official
source. It never touches trading, and nothing in a post may come from the trading bots.

## Files
- `blog/_content/<slug>.json`: the post (schema at the top of `scripts/blog_publish.py`)
- `blog/_content/_template.html`: layout ("quiet wealth" editorial: Bodoni Moda + Hanken Grotesk, ivory/forest/brass,
  nav, header, full-width photo, `as_of` note, Budget Shield card at `<!--MID-->`, bottom line, FAQ + FAQPage JSON-LD,
  sources, CTA panel, disclaimer, sticky bar, PostHog). Site-wide styles: `assets/site.css`.
- `scripts/blog_publish.py`: gates + renders the HTML, OG image, blog index card, homepage "Latest" (3 newest),
  sitemap, llms.txt, topics.json
- `blog/_content/photos.json`: the **photo library**. Each key is a photo at `assets/photos/<key>-1600.webp` and
  `<key>-800.webp`, with alt text, credit, crop focus (`pos`), mood and the lanes it fits.
- `blog/images/<slug>-og.jpg`: 1200x630 social card, cropped from the post's photo by the script.

## Photos (every post has one)
The post JSON's `"image"` names a library key: `"image": "colonnade"`, or with alt text written for this post:
`"image": {"key": "colonnade", "alt": "Morning light along a colonnade of pale stone columns"}`.
No `image` -> the lane's photo (news `coffee-paper`, howto `planner-pen`, prices `kitchen-brass`,
check `vintage-desk`). The photo is the post's hero, its blog/home card and its social card.

Picking one:
1. Read `blog/_content/photos.json` and choose the photo whose `mood`/`fits` matches the post. Avoid the photo used
   by either of the 2 newest posts so the index doesn't repeat itself.
2. If nothing fits, add one. Art direction: warm natural light, refined calm interiors, hands with a notebook and
   coffee, linen, brass, stone, morning light, evening city; real-looking, diverse people when people appear.
   **No** logos, readable text, money piles, flashy luxury, stock-photo grins, or screens showing a UI.
   Source: Unsplash (Unsplash License: free for commercial use; never an "Unsplash+" photo) or an original image
   generated for us (Higgsfield). Never hotlink.
   ```bash
   python3 -I scripts/blog_publish.py <slug> --image-file ~/Downloads/photo.jpg \
     --image-alt "What the photo shows, plainly" --image-credit "Photographer name" \
     --image-credit-url https://unsplash.com/photos/<id>
   ```
   That writes `assets/photos/<slug>-1600.webp` + `-800.webp` (each under ~250 KB), adds `<slug>` to photos.json
   and sets the post's `image`. Then edit the new library entry's `pos` (e.g. `"40% 60%"`), `mood` and `fits`.
   For an original image use credit "Hardaway Labs" and leave the credit URL empty.
3. Alt text describes the photo, not the post ("Gifts wrapped in brown kraft paper under a Christmas tree").

## Publish by hand
```bash
cd ~/Code/healthymoneydaily && git pull
# write blog/_content/my-post.json
python3 -I scripts/blog_publish.py my-post --dry     # gates only
python3 -I scripts/blog_publish.py my-post
git add -A && git commit -m "Blog: my post" && git push origin main
curl -s -o /dev/null -w "%{http_code}" https://www.healthymoneydaily.com/blog/my-post   # expect 200
```
Vercel deploys `main` automatically (1-2 min). **Until Chris approves PUBLISH.md, there is no remote: commit
locally only.**

## Tracking
PostHog project **458884** (Budget Shield), public key in the page snippet (the same `phc_` key the iOS app
ships). Events: `$pageview` (automatic; every event carries `site: 'healthymoneydaily'`) and
`blog_download_cta_click {site, placement, store:'ios', app:'budget_shield', path}`. Placements and App Store
`ct` tokens (all with `pt=128318750` so they show in App Store Connect → App Analytics → Campaigns):

| placement | ct token |
|---|---|
| nav | hmd_nav |
| home_band | hmd_home_band |
| mid (article card) | hmd_mid |
| cta_box (end of post) | hmd_cta |
| sticky | hmd_sticky (`sticky_dismiss` = closed the bar) |
| footer | hmd_footer |
| about | hmd_about |
| /ios, /app, /budget-shield short links, llms.txt | hmd_short / hmd_blog |

PostHog doesn't initialise on localhost, so local previews never pollute the project.

## Editorial standard (summary; the full rules are CONTENT_GUIDELINES.md)
- Title = the search phrase, 55-80 chars. 1,200-1,600 words. 4 FAQ. 2+ sources, one official.
- `<!--MID-->` a third of the way down. One `.key` line, one `.todo` "Three things to do this week".
- One bridge paragraph naming Budget Shield's real feature for the topic. No App Store links in the body.
- News posts set `"as_of"` and say odds are odds.


## Styling changes reach phones
Browsers keep `/assets/*` for a week. Every page links `site.css`/`site.js` with `?v=<hash>`; `blog_publish.py` refreshes it after each publish. After editing `assets/site.css` or `site.js` by hand, run `python3 -I scripts/stamp_assets.py` before pushing, or phones that visited before see new pages with old styling.
