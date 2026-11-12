# Publishing Healthy Money Daily: steps for Chris to approve

Everything so far is **local only** (`~/Code/healthymoneydaily`, git repo, no remote). Nothing below has been
run. Each step makes something public or costs money, so each needs your OK. Same setup as Healthy Faith
Daily (repo HealthyOne-Org/healthyfaithdaily → Vercel project `healthyfaithdaily` → Namecheap DNS).

## 0. Before you start
- [ ] healthymoneydaily.com bought at Namecheap (you're doing this now). Leave its nameservers on
      **Namecheap BasicDNS** (dns1/dns2.registrar-servers.com), like healthyfaithdaily.com.
- [ ] Read the two launch posts once. The Fed post quotes Polymarket odds from **Nov 11, 8:40 PM ET**
      (about 86% for a quarter-point hike). If you publish on a later day, refresh the number first
      (`cat ~/.hermes/state/money_news_latest.json`, the `odds` block) and update `as_of`, then re-run
      `python3 -I scripts/blog_publish.py december-fed-rate-hike-what-it-means`.
- [ ] Optional: change the posts' date to launch day: `python3 -I scripts/blog_publish.py <slug> --date YYYY-MM-DD`
      for each (it rewrites the page, index cards and sitemap).

## 1. GitHub repo (public, like healthyfaithdaily)
```bash
cd ~/Code/healthymoneydaily
gh repo create HealthyOne-Org/healthymoneydaily --public --source . --remote origin --push \
  --description "Healthy Money Daily: plain-English money news and budgeting (healthymoneydaily.com)"
```
Public is safe: the only key in the code is PostHog's public ingest key (`phc_…`, the same one the Budget
Shield iOS app ships). No secrets are in the repo.

## 2. Vercel project linked to the repo
Pattern from `vercel project inspect healthyfaithdaily`: team "Chris Hardaway's projects", Framework **Other**,
Root `.`, no build command, output `.` (static files). `vercel.json` already has clean URLs, the apex→www
redirect, the `/ios` short links and headers; `.vercelignore` keeps `scripts/` and `blog/_content/` off the site.
```bash
cd ~/Code/healthymoneydaily
vercel project add healthymoneydaily
vercel link --yes --project healthymoneydaily
vercel git connect https://github.com/HealthyOne-Org/healthymoneydaily   # pushes to main deploy production
vercel --prod                                                            # first deploy
```
Check: the `*.vercel.app` URL shows the home page, `/blog`, both posts, `/about`, `/privacy`, `/disclaimer`.

## 3. Domains on Vercel
```bash
vercel domains add www.healthymoneydaily.com healthymoneydaily
vercel domains add healthymoneydaily.com healthymoneydaily
```
In the dashboard (Project → Settings → Domains): make **www.healthymoneydaily.com** the primary domain and set
**healthymoneydaily.com → Redirect to www (308)**. The canonical URLs in every page use `https://www.`.
Vercel then shows the exact DNS values for each domain. Copy those; they win over the values below.

## 4. Namecheap DNS (Domain List → healthymoneydaily.com → Advanced DNS)
Delete Namecheap's parking records first (the `CNAME www → parkingpage.namecheap.com.` and the `URL Redirect @`).
Then add:

| Type | Host | Value | TTL |
|---|---|---|---|
| A Record | `@` | `216.198.79.1` | Automatic |
| CNAME Record | `www` | the value Vercel shows for www, e.g. `<hash>.vercel-dns-017.com.` (healthyfaithdaily.com uses `7c368fd982807df2.vercel-dns-017.com.`; the generic `cname.vercel-dns.com.` also works) | Automatic |
| TXT Record | `@` | `google-site-verification=…` (from step 5) | Automatic |

`216.198.79.1` is what healthyfaithdaily.com's apex resolves to today (checked 2026-11-11). Verify after
10-30 min:
```bash
dig +short healthymoneydaily.com A          # 216.198.79.1
dig +short www.healthymoneydaily.com CNAME  # the vercel-dns host
vercel domains inspect healthymoneydaily.com
curl -sI https://healthymoneydaily.com | grep -i location   # → https://www.healthymoneydaily.com/
curl -s -o /dev/null -w "%{http_code}\n" https://www.healthymoneydaily.com/blog/december-fed-rate-hike-what-it-means  # 200
```
No email records are needed (the site uses support@healthyonefinances.com).

## 5. Google Search Console (verify + sitemap)
1. search.google.com/search-console → Add property → **Domain** → `healthymoneydaily.com`.
2. Copy the `google-site-verification=…` TXT value into Namecheap (table above), wait a few minutes, Verify.
   (Healthy Faith used a URL-prefix property with an HTML file; the Domain property covers www + apex at once.)
3. Sitemaps → submit `https://www.healthymoneydaily.com/sitemap.xml`.
4. URL Inspection → request indexing for both launch posts.

## 6. Bing Webmaster Tools (Bing sends HealthyOne ~5× Google's traffic)
1. bing.com/webmasters → **Import from Google Search Console** (fastest; verifies and imports the sitemap).
   Or Add site → `https://www.healthymoneydaily.com` → verify with the DNS CNAME/TXT Bing gives you in Namecheap.
2. Sitemaps → submit `https://www.healthymoneydaily.com/sitemap.xml` if it wasn't imported.
3. URL Submission → submit both posts.

## 7. After it's live
- [ ] PostHog project 458884 → Activity: a `$pageview` with `site = healthymoneydaily` appears when you open
      the site (it doesn't track on localhost). Tap an App Store button: `blog_download_cta_click` with
      `placement`.
- [ ] App Store Connect → Budget Shield → App Analytics → Sources → Campaigns: `hmd_*` tokens show up after
      the first taps (Apple delays these a day or two).
- [ ] News export cron (read-only, user crontab):
      `23 * * * * /usr/bin/python3 /Users/chris/.hermes/scripts/money_news_export.py >> /tmp/money_news_export.log 2>&1`
- [ ] Publisher, Tue + Thu 8:31 AM ET: see "Publisher" below.
- [ ] Mission Control Growth tab: add Healthy Money Daily as the 3rd blog (site key `healthymoneydaily`).
- [ ] Instagram @healthymoneydaily (check the handle on the sign-up screen).

## Publisher: recommendation
**Use a Hermes cron that runs `claude -p`, not a Claude-app scheduled task.**
- Claude-app tasks only run while the Claude app is open. That's why Healthy Faith and HealthyOne missed
  Tuesday Nov 3 after the restart.
- The Hermes gateway is a launchd agent that's always up, and `claude -p`'s login (in the keychain) works
  under it. hermes_review.py already runs `claude -p` this way twice a day.
- Same pattern as hermes_review.py: a launcher that detaches a worker (Hermes kills `--no-agent` scripts at
  120 s). The worker runs
  `claude -p --model opus --permission-mode auto --output-format json --add-dir ~/.hermes` in
  `~/Code/healthymoneydaily` with `scripts/PUBLISHER_PROMPT.md` as the prompt, then sends the one-line
  report to Telegram. Decision-making jobs get the top model.
- Cron (after the launcher `hmd_publisher.py` is written; **not built yet**):
  `hermes cron create "31 8 * * 2,4" --name healthy-money-publisher --no-agent --script hmd_publisher.py --deliver local`
- If you'd rather match the other two blogs today: a Claude desktop scheduled task "Healthy Money blog
  publisher", `CRON_TZ=America/New_York 31 8 * * 2,4`, prompt = "Follow ~/Code/healthymoneydaily/scripts/PUBLISHER_PROMPT.md".
  It works only while the app is open.
