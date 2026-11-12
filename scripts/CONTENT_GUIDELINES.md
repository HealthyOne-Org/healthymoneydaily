# Healthy Money Daily: content guidelines (finance is "Your Money or Your Life")

Google holds money content to its highest bar (YMYL). One sloppy number or one "buy this stock" line can sink
the whole site's trust, and with it Budget Shield's best free traffic. These rules are not optional. The
publisher (`scripts/PUBLISHER_PROMPT.md`) reads this file every run, and `scripts/blog_publish.py` enforces
the mechanical parts (sources, banned phrases, word count, the disclaimer).

## 1. Education only
- Explain how money works and what a change means for a household. Never tell a reader what to invest in.
- **No personal investment advice. No stock, fund, crypto or option picks.** No "buy", "sell", "now is the time
  to invest", price targets, or "this stock could double". Naming a company is fine only as news context
  (e.g. "Nvidia reports earnings on November 17") and never as a recommendation.
- No tax or legal advice for a specific situation. Explain the rule, link the IRS/CFPB page, suggest a
  professional (nonprofit credit counselor, fee-only planner, tax preparer) for decisions.
- Never guarantee an outcome ("guaranteed", "risk-free", "can't lose", "get rich" are banned).

## 2. The trading engine is not a source of tips
- The News Desk export (`~/.hermes/state/money_news_latest.json`) is only for **choosing topics and dates**.
- **Never** use, quote or hint at the trading bots, their practice (paper) results, signals, backtests or
  holdings. Never write "our model thinks" or "our data shows the market will".
- A headline in the export is not a fact for the post. Confirm it at an official source or a named, reputable
  outlet before you write it, and link that source, not the feed.

## 3. Numbers: official, linked, never invented
- Every number in a post must trace to a source linked in `sources[]`. If you can't find it, leave it out.
- Prefer, in this order: **BLS** (CPI, jobs), **Federal Reserve** (FOMC statements, H.15 rates, G.19 consumer
  credit, SHED household survey), **CFPB**, **Federal Register** (tariffs, rules), FDIC, Treasury, IRS, EIA,
  USDA, Census/BEA. At least one official source per post (the publish script checks).
- Say the date of the number ("as of November 9", "third quarter of 2026"). News posts set `as_of`.
- Check the current figure on the day you write. Release pages called "current" change; name the release date.
- Worked examples use round, clearly made-up amounts ("a round, made-up example: $1,000 at 22.36 percent"), and
  the math must be right (compute it, don't estimate it).
- If an official series has a gap or caveat (e.g. BLS could not publish 12-month CPI changes for October 2026
  because October 2025 data was never collected), say so instead of filling it.

## 4. Market odds are odds
- Prediction-market or futures odds (Polymarket, CME FedWatch) may be mentioned as **what traders are betting at
  a moment in time**, with the time, and the words "odds, not a prediction". The publish script rejects a post
  that mentions them without "not a prediction" / "not a forecast".
- Never present odds as our forecast. Never write "the Fed will".

## 5. Our own words
- Summarize news in our own words. Never copy or lightly reword an article. At most one short quote (under
  ~25 words) from an official document, in quotation marks and attributed ("inflation remains elevated," the
  Fed said). Never quote paywalled reporting.
- Link to the official document over a news story whenever one exists.

## 6. Budget Shield, honestly
- Feature lines come only from what the app really does (verified in `~/Code/healthy-budget` on 2026-11-11):
  - a 30-day forecast of bills and paychecks on one timeline (a pre-paywall preview needs only a balance and a
    paycheck);
  - a warning before a payment won't clear (balance headed below zero before money comes in);
  - past-due bills tracked and counted until marked paid;
  - money moved to a vault or savings kept in the forecast so it doesn't look like spending.
- Don't invent features (no "AI advisor", no "credit score", no "automatic savings"). Don't promise outcomes
  ("never overdraft again"). Say "warns you", not "prevents".
- Don't use "free" next to Budget Shield or about its price (App Store wording rule). Don't name competitors.
- The template places the App Store links (tracked, with `ct` tokens). Don't put App Store links in `body_html`.
  One natural mention of the app in the body (the bridge paragraph) is enough; the mid card and CTA do the rest.
- Say it's ours: "Budget Shield, the iPhone app from the team behind this blog".

## 7. Voice and shape
- Calm, plain, warm, specific. A reader at the kitchen table, a little worried. No hype, no fear-mongering, no
  "in today's fast-paced world", no exclamation marks.
- 1,200-1,600 words of body. `<h2>` sections, a `.key` pull line, short lists, a `.table-scroll` table when it
  helps, and always a `.todo` box: **"Three things to do this week"**.
- 4 FAQ entries phrased the way people search. A one-paragraph bottom line.
- Title names the exact search phrase, 55-80 characters; the year only on guides and seasonal posts.
- Sensitive situations (debt collection, eviction, can't pay utilities): point to official help (CFPB, 211,
  LIHEAP via HHS, the utility's hardship program) and keep the tone kind.

## 8. The disclaimer
- Every post carries the disclaimer block (it's in the template; never remove it) and links `/disclaimer`.
- Later: a CFP/CPA reviewer badge (E-E-A-T), same idea as the HealthyOne advisors. Not live yet; never claim a
  review that didn't happen.

## Hard no (the publish script rejects these)
"guaranteed", buy/sell calls on shares/stock/calls/puts, stock picks, "our bots", paper trading, "risk-free",
"get rich", "free" next to Budget Shield, odds without "not a prediction", App Store links in the body, fewer
than 2 sources or no official source, a missing `<!--MID-->` marker.
