# India Stock Picks: recommendation aggregator

A dashboard that collects daily Indian stock recommendations (NSE) from financial news sites and
shows which stocks several **independent** analysts/brokerages are recommending, with targets,
stop-losses, horizons, a short reason per source and a link to every original article.

> Aggregated third-party opinions. Not investment advice.

- **Ranking:** stocks are ranked by distinct analysts/brokerages, then by number of websites. One
  analyst's call syndicated to three sites counts as **1 opinion, 3 websites**.
- **Conflicts are visible:** Buy/Accumulate, Sell/Reduce and Hold are kept apart, so a stock with 3 Buys
  and 1 Sell shows a `⚠ 1 Sell` warning.
- **Fast page loads:** scraping runs on a schedule (and on demand). A page load only reads the latest
  results.

## Quick start

Requires Python 3.11+ (tested on 3.14, Windows 11).

```bash
python -m venv .venv
# Windows:  .venv\Scripts\python -m pip install -r requirements.txt
# macOS/Linux: .venv/bin/python -m pip install -r requirements.txt
cp .env.example .env          # optional: add ANTHROPIC_API_KEY
python dev.py                 # http://127.0.0.1:8000  (server + scheduler; seeds the DB on first run)
```

| Command | What it does |
|---|---|
| `python dev.py` | Starts the local dashboard + scheduler (127.0.0.1 only). Runs a first scrape if the DB is empty. |
| `python dev.py seed [source ...]` | Runs one scrape now (all enabled sources, or only the named ones). |
| `python dev.py export` | Builds the public static site in `./site` and runs the safety check. |
| `python dev.py test` | Runs the unit tests. |

`make dev / seed / export / test` do the same thing if you have `make`.

### Environment variables (`.env`, git-ignored)

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | unset | Turns on LLM extraction. Without it the regex/heuristic extractor is used. |
| `ANTHROPIC_MODEL` | `claude-haiku-5-5` | Model used for extraction. |
| `CONTACT_URL` | unset | Public URL appended to the User-Agent (e.g. your repo). Don't use a personal email. |
| `FETCH_PRICES` | `1` | Fetch delayed prices from Yahoo Finance (`SYMBOL.NS`) to compute upside. `0` turns it off. |
| `PORT` | `8000` | Local port. |

**LLM cost:** one call per new reco-looking article (roughly 50–150 a day). Syndicated copies and
already-seen URLs are never sent twice. The output is constrained to a strict JSON schema and validated
again locally. If the API fails for an article, that article falls back to the heuristic extractor.

## Sources (verified 2026-11-23)

| Source | Method | Default | Notes |
|---|---|---|---|
| Economic Times | RSS (Expert View, Stocks, Recos) | on | The dedicated `/recos` feed is stale (last item May 2026). |
| Moneycontrol | HTML tag/listing pages | on | All MC RSS feeds have been frozen since Apr 2024. |
| Livemint | RSS + listing | on | |
| CNBC-TV18 | RSS | on | |
| Financial Express | Google-News sitemap | on | WordPress feeds are disabled (HTTP 410). |
| Goodreturns | RSS (filtered) | on | The "shares to buy" feed is stale; expect few hits. |
| Trendlyne | `/research-reports/buy` and `/sell` table | on | Structured rows with NSE symbol, so no LLM is needed. Honours the 10 s crawl-delay. |
| Business Standard | Topic pages + RSS | **off** | Returns HTTP 403 to self-identified bots, including for robots.txt. |
| NDTV Profit | RSS + research-reports | **off** | Same as Business Standard (CDN 403 for bot User-Agents). |
| Google News RSS | search feed | **off** | `news.google.com/robots.txt` disallows `/rss/` for all agents. |

Business Standard and NDTV Profit only work with `user_agent: browser` in `sources.yaml`, which means
fetching as a regular browser after the site has chosen to block bots. That's left as your decision.

**Etiquette built in:** robots.txt is checked for every URL (wildcard-aware; a robots.txt that returns
401/403 is treated as "disallow all"). Requests to each domain are spaced at least 3 s apart, or the
robots crawl-delay if longer. Responses are cached on disk, and retries use exponential backoff on
429/5xx. Every request has a timeout. A failing source is recorded in **Source health** and never stops
the others.

## How it works

```
sources/*.py ──► articles (title, url, date, body text in memory only)
                   │  syndicated copy (same text hash)? reuse earlier extraction
                   ▼
extract/  LLM (JSON schema) ─fallback─► heuristic regexes
                   ▼
symbols.py  alias table → exact symbol/name → unique prefix → fuzzy (rapidfuzz ≥ 90)
            drops indices, commodities, crypto, US stocks, anything not in NSE EQUITY_L.csv
                   ▼
SQLite (data/dashboard.db): sources · articles · recommendations · stocks
                   ▼
aggregate.py ─► data.json ─► web/app.js groups & ranks in the browser
```

- **Storage and copyright:** article text is used in memory for extraction and never stored. The
  DB keeps only metadata, the short reason and the link. Rows older than 14 days are pruned.
- **Opinion identity:** an opinion is `symbol | action | brokerage` (or the analyst if no brokerage, or
  the article hash if neither). If a site names only the analyst, the brokerage is filled in from earlier
  sightings of that analyst.
- **"Today"** means since the previous weekday's 15:30 IST close. Evening and weekend "stocks to buy
  tomorrow" articles therefore count towards the next session. Market holidays are not modelled.
- **Schedule (IST):** every 15 min from 07:00 to 09:15 on weekdays, hourly at :15 during market hours,
  and every 30 min from 16:00 to 21:00 daily. Defined in `app/scheduler.py` and mirrored in UTC in the
  workflow.

### Heuristic mode (no API key)

The regex extractor handles the common formats: "Buy X; target of Rs N: Broker", "SL @ … Target @ …",
"Name: Buy at ₹… | Target ₹… | Stop-loss ₹…", "Citi maintains sell on X", "X: PL Capital Retains
'Reduce'", and target tables. Its reasons are short **excerpts**, not paraphrases, and it misses
free-form interviews and sometimes misattributes calls in multi-broker round-ups. Set
`ANTHROPIC_API_KEY` for proper summaries and much better recall.

## Adding a source

1. **Config only** (RSS / listing page / news sitemap). Add this to `sources.yaml`:
   ```yaml
   my_site:
     module: generic
     label: My Site
     feeds: [https://example.com/markets/rss]
     listings: [{url: "https://example.com/stocks/", pattern: "/stocks/.+-\\d+\\.html$"}]
   ```
2. **Custom logic.** Create `app/sources/my_site.py`:
   ```python
   from .base import Source

   class MySite(Source):
       DEFAULT_OPTIONS = {"feeds": ["https://example.com/rss"]}
       # or override fetch_recent_articles(self, since, skip) -> list[Article]

   Plugin = MySite
   ```
   then add `my_site: {module: my_site, label: My Site}` to `sources.yaml`. Sources that already have
   structured picks can set `Article.prestructured` (see `trendlyne.py`) to skip extraction.

Missing a nickname? Add it to `app/aliases.yaml` (e.g. `"bob": BANKBARODA`).

## Sharing publicly (GitHub Pages) without leaking anything

The public site is a **static snapshot**: `index.html`, `app.js`, `styles.css`, `data.json`. Nothing
else is published.

| Thing | Where it lives | Published? |
|---|---|---|
| `ANTHROPIC_API_KEY` | `.env` locally (git-ignored) / repository **secret** in CI | Never. The safety check blocks the deploy if its value appears in the site. |
| SQLite DB, HTTP cache, NSE CSV | `data/` (git-ignored) / private Actions cache | Never |
| Logs, `.venv`, `.claude/`, editor files | git-ignored | Never |
| Git history | your repository | Not part of the Pages site, which serves only the build artifact |
| Scraped data | `data.json` | Yes, built from an explicit field allowlist (`app/aggregate.py`) |

`scripts/check_public.py` runs before every deploy. It fails if `site/` contains any file other than
those 5, an API-key/token pattern, the value of any `*KEY*`/`*TOKEN*`/`*SECRET*` environment variable,
a local filesystem path or an email address.

### Steps

1. Create a GitHub repo and push this folder. `.gitignore` already excludes secrets and local data.
   Check with `git status` before the first commit.
2. *(Recommended)* Commit under GitHub's private noreply address so your email isn't in the public history:
   `git config user.email "<id>+<username>@users.noreply.github.com"` (GitHub → Settings → Emails).
3. Repo → **Settings → Secrets and variables → Actions**: add the secret `ANTHROPIC_API_KEY` (optional).
   You can also add a variable `CONTACT_URL` set to the repo URL.
4. Repo → **Settings → Pages → Source: GitHub Actions**.
5. **Actions → Scrape and publish → Run workflow** for the first build. After that it runs on the schedule.

Notes:
- On a **public** repo, Actions logs are public too. The workflow never prints secrets, and GitHub masks
  them anyway.
- To keep the **code private**, GitHub Pages from a private repo needs a paid plan. Alternatively, run
  `python dev.py export` locally and upload `site/` to Cloudflare Pages or Netlify (drag-and-drop).
- Scheduled workflows on public repos are paused after 60 days without repository activity.
- Some news sites may block cloud/datacenter IPs. If a source shows as failing in Source health only on
  the published site, that's why. The local app still works.
- Republishing scraped headlines publicly carries more responsibility than private use. The site links
  to originals, shows only short summaries, credits every analyst and brokerage, and carries the
  disclaimer. Check the sources' terms (Trendlyne in particular) and SEBI's rules on distributing
  research before promoting the site widely.

## Tests

`python dev.py test` runs 54 tests: symbol mapping (aliases, prefixes, fuzzy, index/foreign rejection),
the heuristic extractor on sample articles in each site's format (`tests/fixtures/articles.json`, written
for the tests rather than copied), JSON schema validation, the LLM extractor with a mocked API,
de-duplication (same analyst across sites, syndicated copies, Buy vs Sell), Trendlyne table parsing, the
payload allowlist and the publish safety check.
