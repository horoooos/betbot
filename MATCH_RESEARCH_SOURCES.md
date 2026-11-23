# Match research sources

This is a source inventory, not a promise of universal coverage or profitable forecasts.
Only public pages are requested. Source robots rules are checked; HTTP challenges,
redirects, unknown market units and missing timestamps fail closed. No accounts,
proxies, payment services or access-control bypasses are used.

## Active collection

| Source | Structured input | Boundaries |
|---|---|---|
| Stavka TV | Existing dated author opinions; fresh same-book complete winner headers | Recorded author odds never become current executable prices |
| Legalbet /tips/ | Author, publication time, explicit market and historical price | Exact fixture, date and orientation required; unsupported handicaps stored as observations |
| LiveSport /tips/ | JSON-LD event/publication time, author, explicit pick/price, numeric tables | Only complete explicit market labels; no inferred picks from prose |
| Metaratings /prognozy/ | JSON-LD event/author/time, dedicated bet blocks | No guessing named-team inflections or market periods |
| Bookmaker Ratings /forecast_homepage/ | Individual article metadata and explicit final forecast | Event summary cards are not individual author forecasts; coverage can be zero |
| VseProSport /news/statistics | Linked dated match articles and numeric tables where present | A live bookmaker selector is not the author's recorded price; unbound quotes are excluded |
| ESPN existing summary | Standings, recent games, H2H, confirmed lineups, injuries, leaders, venue if returned | Six due matches per pass; 15-minute factual cache; absent information stays absent |

External article pages rotate, at most six per provider every thirty minutes.
All football, hockey, basketball, tennis, CS2 and Dota events can be matched,
subject to what the sources actually publish. Same teams, sport when specified,
kickoff (within five minutes) or explicit match day and unambiguous orientation
are required. Syndicated named authors share an identity across new providers.
Only structured metadata, short market labels and bounded numeric tables are
stored; article bodies and publisher images are not copied.

## Learning and provenance

Storage is nested at `data/stavka_learning.json.external_sources` so the existing
bot loop preserves it without a workflow restart. Providers have independent
health reports. Article context, unsupported markets, usable opinions, and factual
dossiers are distinct. Published forecasts retain a `research` provenance record.

The external pool has separate football and per-sport models. Football handles 1X2, totals 1.5/2.5/3.5/4.5 and both-teams-to-score as explicit market families; unsupported units remain observations. It starts with
weight zero. Existing chronological train/validation checks and minimum sample
requirements apply, and only outcomes observed before validation can train a model.
If a new model is validated it replaces the old external signal for that forecast;
the signals are never blindly added together. Unvalidated sources do not change
probabilities, real bookmaker quotes or historical bank calculations.

## Investigated but not enabled

- Sports.ru: public predictions list accessible, no validated article adapter in this change.
- TotalCorner: public page accessible, robots endpoint returned 403 from the local probe; not enabled.
- Vprognoze: direct page returned 403; not enabled.
- Forebet and Betimate: challenge pages; not enabled.
- OpenDota proMatches: public endpoint responded, but map results require correct series aggregation before use in a series-winner model; no model integration claimed here.
- Flashscore, Sofascore and paid odds feeds: no newly validated unrestricted free integration in this change.

Live results depend on location, markup and the current fixture list. See the
source-proof QA artifact for a dated coverage report, never a marketing coverage claim.
